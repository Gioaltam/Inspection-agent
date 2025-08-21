# C:\inspection-agent\run_report.py
import os
import re
import zipfile
import argparse
import tempfile
import time
import concurrent.futures
import logging
import json
import uuid
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageOps

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, Frame, KeepInFrame, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor

from vision import describe_image

# ---------------- Env ----------------
load_dotenv(override=False)  # Don't override existing env vars

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ANALYSIS_CONCURRENCY = int(os.getenv("ANALYSIS_CONCURRENCY", "3"))

# Page geometry
PAGE_W, PAGE_H = LETTER
MARGIN = 0.5 * inch

# Photo-left / Notes-right geometry
IMG_MAX_W = 3.6 * inch
IMG_MAX_H = 8.0 * inch
NOTEBOX_X = MARGIN + IMG_MAX_W + 0.4 * inch
NOTEBOX_W = PAGE_W - NOTEBOX_X - MARGIN
NOTEBOX_BASE_H = IMG_MAX_H  # minimum height; can grow

# Branding / style knobs
BANNER_PATH       = os.getenv("BANNER_PATH", "assets/banner.png")
BRAND_PRIMARY     = os.getenv("BRAND_PRIMARY", "#0b1e2e")
BRAND_SECONDARY   = os.getenv("BRAND_SECONDARY", "#113a5c")
NOTES_FONT_PT     = float(os.getenv("NOTES_FONT_PT", "12.0"))
NOTES_LEADING_PT  = float(os.getenv("NOTES_LEADING_PT", "16.0"))
COVER_TITLE_SHIFT_LEFT_IN = float(os.getenv("COVER_TITLE_SHIFT_LEFT_IN", "0.60"))
RECOMMENDATIONS_EXTRA_GAP_PT = float(os.getenv("RECOMMENDATIONS_EXTRA_GAP_PT", "10"))

# Status icon sources (env overrides supported)
STATUS_CRITICAL_ICON  = os.getenv("STATUS_CRITICAL_ICON", "assets/critical.png")
STATUS_IMPORTANT_ICON = os.getenv("STATUS_IMPORTANT_ICON", "assets/important.png")
# Optional sprite with two icons side-by-side (left=critical, right=important)
STATUS_SPRITE         = os.getenv("STATUS_SPRITE", "assets/icons.png")
STATUS_ICON_PT        = float(os.getenv("STATUS_ICON_PT", "30"))
STATUS_ICON_LABEL_SIZE = float(os.getenv("STATUS_ICON_LABEL_SIZE", "11.5"))

# Optional, customizable repair/action keywords (comma-separated)
REPAIR_KEYWORDS = os.getenv(
    "REPAIR_KEYWORDS",
    "repair,replace,fix,seal,reseal,re-caulk,caulk,secure,anchor,tighten,patch,service,clean and,clean,paint,repaint"
).split(",")

# Cover page prepared-by info
BUSINESS_NAME  = os.getenv("BUSINESS_NAME", "")
BUSINESS_LINE1 = os.getenv("BUSINESS_LINE1", "")
BUSINESS_LINE2 = os.getenv("BUSINESS_LINE2", "")

# ---------------- Styles ----------------
_STYLES = getSampleStyleSheet()
NOTE_BODY = ParagraphStyle(
    "note-body",
    parent=_STYLES["Normal"],
    fontName="Helvetica",
    fontSize=NOTES_FONT_PT,
    leading=NOTES_LEADING_PT,
    textColor="#2b2b2b",
)
NOTE_BULLET = ParagraphStyle(
    "note-bullet",
    parent=NOTE_BODY,
    leftIndent=12,
    bulletIndent=0,
)
NOTE_SECTION = ParagraphStyle(
    "note-section",
    parent=_STYLES["Heading4"],
    fontName="Helvetica-Bold",
    fontSize=NOTES_FONT_PT + 0.5,
    leading=NOTES_LEADING_PT + 1,
    textColor=BRAND_SECONDARY,
    spaceBefore=2,
    spaceAfter=2,
)
NOTE_SECTION_RECS = ParagraphStyle(
    "note-section-recs",
    parent=NOTE_SECTION,
    spaceBefore=NOTE_SECTION.spaceBefore + RECOMMENDATIONS_EXTRA_GAP_PT,
)

# ---------------- Section helpers ----------------
ORDERED_SECTIONS = ["Location", "Materials/Description", "Observations", "Potential Issues", "Recommendations"]
_SECTION_RX = re.compile(r"(?im)^(Location|Materials(?:/Description)?|Description|Observations|Potential\s+Issues|Issues|Recommendations?):\s*$")

def _split_candidate_lines(text: str) -> list[str]:
    if not text: return []
    t = text.replace("—", ". ").replace("•", "\n").replace(";", ". ")
    lines = []
    for raw in t.splitlines():
        raw = raw.strip().strip("-*•").strip()
        if not raw: continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", raw)
        for p in parts:
            p = p.strip().strip("-*•").strip(": ").strip()
            if p: lines.append(p)
    return lines

def _route_line(line: str) -> tuple[str, str]:
    l = line.strip(); low = l.lower()
    if low.startswith(("location/material", "location & material")):
        return "Location", (l.split(":",1)[-1].strip() if ":" in l else l)
    if low.startswith("location:"): return "Location", l.split(":",1)[-1].strip()
    if low.startswith(("material:", "materials:", "materials/description:", "description:")):
        return "Materials/Description", l.split(":",1)[-1].strip()
    if low.startswith(("recommendation", "action ", "action:", "recommend ")):
        return "Recommendations", (l.split(":",1)[-1].strip() if ":" in l else l)
    if low.startswith(("issue","risk","hazard","safety","concern","defect","damage","deteriorat","leak","moisture","mold","rot","crack","corrosion","not in conduit","unsecured","trip hazard","minor condition","active leak","stain","missing","loose","unsafe","exposed")):
        return "Potential Issues", (l.split(":",1)[-1].strip() if ":" in l else l)
    if any(k in low for k in ["cmu block","drywall","lap siding","asphalt shingle","concrete","paver","brick","plaster","register","vent cover"]):
        return "Materials/Description", l
    if any(k in low for k in ["front exterior","interior","exterior wall","entry","porch","driveway","bathroom","kitchen","ceiling","wall "]):
        return "Location", l
    return "Observations", l

def _normalize_observation(note_text_or_dict):
    res = {k: [] for k in ORDERED_SECTIONS}
    if isinstance(note_text_or_dict, dict):
        aliases = {"Materials":"Materials/Description","Description":"Materials/Description","Issues":"Potential Issues","Recommendation":"Recommendations"}
        for k,v in note_text_or_dict.items():
            if not v: continue
            key = aliases.get(k,k);  key = key if key in res else "Observations"
            res[key].extend(_split_candidate_lines(str(v)))
        if not any(res.values()):
            joined = " ".join(str(v) for v in note_text_or_dict.values() if v)
            res["Observations"] = _split_candidate_lines(joined)
        return res
    text = str(note_text_or_dict or "").strip()
    if not text: return res
    parts,current,buf = {},None,[]
    has_headers = False
    for ln in text.splitlines():
        m = _SECTION_RX.match(ln.strip())
        if m:
            has_headers = True
            if current is not None:
                parts[current] = "\n".join(buf).strip(); buf=[]
            current = m.group(1)
            if current in ("Materials","Description"): current="Materials/Description"
            if current.startswith("Recommendation"): current="Recommendations"
            if current=="Issues": current="Potential Issues"
        else:
            buf.append(ln)
    if current is not None: parts[current]="\n".join(buf).strip()
    if has_headers:
        for k in ORDERED_SECTIONS:
            if k in parts and parts[k]:
                res[k].extend(_split_candidate_lines(parts[k]))
        return res
    for cand in _split_candidate_lines(text):
        sec, clean = _route_line(cand)
        if sec=="Location" and "location/material" in cand.lower():
            res["Location"].append(clean); res["Materials/Description"].append(clean); continue
        res[sec].append(clean)
    if not any(res.values()):
        res["Observations"] = ["No visible issues."]
    return res

# ---------- Status icon helpers ----------
def _sprite_split_if_needed() -> tuple[str|None, str|None]:
    crit, imp = STATUS_CRITICAL_ICON, STATUS_IMPORTANT_ICON
    if os.path.exists(crit) and os.path.exists(imp):
        return crit, imp
    if os.path.exists(STATUS_SPRITE):
        try:
            with Image.open(STATUS_SPRITE) as im:
                im = ImageOps.exif_transpose(im)
                w,h = im.size
                mid = w//2
                left = im.crop((0,0,mid,h))
                right = im.crop((mid,0,w,h))
                tmp = Path(tempfile.gettempdir())
                crit_path = str(tmp / "status_crit.png")
                imp_path  = str(tmp / "status_imp.png")
                left.save(crit_path); right.save(imp_path)
                return crit_path, imp_path
        except Exception:
            return None, None
    return (crit if os.path.exists(crit) else None,
            imp if os.path.exists(imp) else None)

class StatusIconsFlowable(Flowable):
    def __init__(self, width, critical: bool, important: bool):
        super().__init__()
        self.width = width
        self.critical = critical
        self.important = important
        self.height = STATUS_ICON_PT + 6
        self._crit_path, self._imp_path = _sprite_split_if_needed()

    def wrap(self, availWidth, availHeight):
        return (self.width, self.height)

    def _draw_one(self, c, x, icon_path, label):
        if icon_path and os.path.exists(icon_path):
            try:
                img = ImageReader(icon_path)
                c.drawImage(img, x, 0, width=STATUS_ICON_PT, height=STATUS_ICON_PT,
                            preserveAspectRatio=True, mask="auto")
                x += STATUS_ICON_PT + 6
            except Exception:
                pass
        c.setFont("Helvetica", STATUS_ICON_LABEL_SIZE)
        c.setFillColor(HexColor("#333333"))
        c.drawString(x, STATUS_ICON_PT * 0.28, label)
        return x + c.stringWidth(label, "Helvetica", STATUS_ICON_LABEL_SIZE) + 12

    def draw(self):
        c = self.canv
        x = 0
        if self.critical:
            x = self._draw_one(c, x, self._crit_path, "critical")
        if self.important:
            x = self._draw_one(c, x, self._imp_path, "important repair")

# --- NEW: Only show wrench when repair/action words appear ---
def _detect_status_flags(data_dict: dict) -> tuple[bool,bool]:
    # ignore placeholders
    issues = [t.lower() for t in data_dict.get("Potential Issues", [])
              if "no visible issues" not in t.lower()]
    if not issues:
        return False, False

    # critical only if the word appears
    crit = any("critical" in t for t in issues)

    # wrench only if a repair/action keyword appears (or explicit 'important')
    def matches_action(t: str) -> bool:
        if "important" in t:
            return True
        for raw in REPAIR_KEYWORDS:
            w = raw.strip().lower()
            if not w:
                continue
            # word-boundary-ish match (supports hyphenated like re-caulk)
            if re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", t):
                return True
        return False

    imp = any(matches_action(t) for t in issues)
    return crit, imp

def _build_note_paragraphs(note_text_or_dict):
    flows = []
    data = _normalize_observation(note_text_or_dict)
    for section in ORDERED_SECTIONS:
        style = NOTE_SECTION_RECS if section=="Recommendations" else NOTE_SECTION
        flows.append(Paragraph(f"<b>{section}</b>", style))
        if section=="Potential Issues":
            cflag, iflag = _detect_status_flags(data)
            if cflag or iflag:
                flows.append(StatusIconsFlowable(NOTEBOX_W - 24, cflag, iflag))
        bullets = data.get(section, [])
        if bullets:
            for b in bullets:
                flows.append(Paragraph(b, NOTE_BULLET, bulletText="•"))
        else:
            flows.append(Paragraph("None noted.", NOTE_BODY))
    return flows

def _measure_total_height(flows, avail_width) -> float:
    total = 0.0
    for f in flows:
        _, h = f.wrap(avail_width, 10000)
        total += h
    return total

# ---------------- Drawing helpers ----------------
def _brand_bar(c: canvas.Canvas):
    c.setFillColor(HexColor(BRAND_PRIMARY))
    c.rect(0, PAGE_H - 14, PAGE_W, 14, fill=1, stroke=0)
    c.setFillColor(HexColor("#000000"))

def _add_page_header(c: canvas.Canvas, address: str):
    _brand_bar(c)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, PAGE_H - MARGIN + 6, address)

def _draw_cover_page(c: canvas.Canvas, address: str):
    header_h = 1.15 * inch
    c.setFillColor(HexColor(BRAND_PRIMARY))
    c.rect(0, PAGE_H - header_h, PAGE_W, header_h, fill=1, stroke=0)

    pad_h = 0.20 * inch; pad_w = 0.35 * inch
    logo_max_h = header_h - 2*pad_h
    logo_max_w = (PAGE_W / 2.8)
    x_logo = MARGIN; y_logo = PAGE_H - header_h + pad_h

    if BANNER_PATH and os.path.exists(BANNER_PATH):
        try:
            img = ImageReader(BANNER_PATH)
            iw, ih = img.getSize()
            scale = min(logo_max_w/iw, logo_max_h/ih, 1.0)
            lw, lh = iw*scale, ih*scale
            c.drawImage(img, x_logo, y_logo, lw, lh, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFillColor(HexColor("#ffffff"))
    title = "Property Inspection Report"
    base_x = x_logo + logo_max_w + pad_w
    title_x = max(MARGIN + 0.20*inch, base_x - COVER_TITLE_SHIFT_LEFT_IN*inch)
    c.setFont("Helvetica-Bold", 26); c.drawString(title_x, PAGE_H - header_h/2 + 8, title)
    c.setFont("Helvetica-Bold", 13); c.drawString(title_x, PAGE_H - header_h/2 - 10, address)
    c.setFillColor(HexColor("#000000"))

    # Prepared-by box
    box_x = MARGIN; box_y = PAGE_H - header_h - 1.20*inch
    box_w = PAGE_W - 2*MARGIN; box_h = 0.95*inch
    c.setFillColor(HexColor("#f5f6fb")); c.roundRect(box_x, box_y, box_w, box_h, 12, fill=1, stroke=0)
    c.setFillColor(HexColor("#333333")); c.setFont("Helvetica-Bold", 14)
    c.drawString(box_x + 18, box_y + box_h - 24, "Prepared by:")

    c.setFont("Helvetica", 12.5)
    line_x = box_x + 135; line_y = box_y + box_h - 24
    if BUSINESS_NAME:  c.drawString(line_x, line_y, BUSINESS_NAME);  line_y -= 18
    if BUSINESS_LINE2: c.drawString(line_x, line_y, BUSINESS_LINE2); line_y -= 18
    if BUSINESS_LINE1: c.drawString(line_x, line_y, BUSINESS_LINE1); line_y -= 18

    import datetime as _dt
    c.setFont("Helvetica", 10); c.setFillColor(HexColor("#666666"))
    c.drawString(MARGIN, MARGIN + 0.5*inch, _dt.datetime.now().strftime("%B %d, %Y"))
    c.setFillColor(HexColor("#777777")); c.drawRightString(PAGE_W - MARGIN, MARGIN, "1")
    c.setFillColor(HexColor("#000000"))

def _draw_photo(c: canvas.Canvas, img_path: Path):
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im)
        w_px, h_px = im.size

        # upscale tiny images/icons so they’re visible
        min_display_w = 2.0 * inch
        min_display_h = 2.0 * inch

        scale_fit = min(IMG_MAX_W / w_px, IMG_MAX_H / h_px)
        disp_w, disp_h = w_px * scale_fit, h_px * scale_fit

        if disp_w < min_display_w or disp_h < min_display_h:
            up = min(min_display_w / max(1, disp_w), min_display_h / max(1, disp_h))
            disp_w, disp_h = disp_w * up, disp_h * up

        if disp_h > IMG_MAX_H:
            clamp = IMG_MAX_H / disp_h
            disp_w, disp_h = disp_w * clamp, disp_h * clamp

        y = PAGE_H - MARGIN - disp_h
        src = getattr(im, "filename", None) or im
        c.drawImage(ImageReader(src), MARGIN, y, width=disp_w, height=disp_h,
                    preserveAspectRatio=True, mask="auto")

def _draw_notes_panel(c: canvas.Canvas, note_text_or_dict):
    inset = 12
    content_w = NOTEBOX_W - 2*inset
    flows = _build_note_paragraphs(note_text_or_dict)
    needed_h = _measure_total_height(flows, content_w) + 2*inset
    panel_h = min(max(NOTEBOX_BASE_H, needed_h), PAGE_H - 2*MARGIN)

    c.setFillColor(HexColor("#f8f8f8"))
    c.roundRect(NOTEBOX_X, PAGE_H - MARGIN - panel_h, NOTEBOX_W, panel_h, 12, fill=1, stroke=0)
    c.setStrokeColor(HexColor("#d0d0d0")); c.setLineWidth(0.7)
    c.roundRect(NOTEBOX_X, PAGE_H - MARGIN - panel_h, NOTEBOX_W, panel_h, 12, fill=0, stroke=1)
    c.setStrokeColor(HexColor("#000000"))

    frame = Frame(NOTEBOX_X + inset, PAGE_H - MARGIN - panel_h + inset,
                  content_w, panel_h - 2*inset, showBoundary=0)
    kif = KeepInFrame(content_w, panel_h - 2*inset, flows, mode="shrink")
    frame.addFromList([kif], c)

# ---------------- ZIP handling ----------------
def collect_images_from_zip(zip_path: Path, workdir: Path) -> list[Path]:
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(workdir)
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    imgs = [p for p in Path(workdir).rglob("*") if p.suffix.lower() in exts]
    imgs.sort()
    return imgs

# ---------------- Analysis (parallel) ----------------
def _analyze_one(p: Path) -> tuple[Path, str, Exception | None]:
    """Analyze a single image with error handling."""
    try:
        notes = describe_image(p)
        return p, notes, None
    except Exception as e:
        logger.warning(f"Failed to analyze {p.name}: {e}")
        return p, "Analysis failed - using fallback.", e

# ---------------- JSON generation ----------------
def generate_json_report(report_id: str, address: str, images: list[Path], results: dict[Path, str]) -> dict:
    """Generate JSON report with normalized notes and flags."""
    photos = []
    critical_count = 0
    important_count = 0
    
    for img_path in images:
        note_text = results.get(img_path, "No visible issues.")
        normalized = _normalize_observation(note_text)
        critical, important = _detect_status_flags(normalized)
        
        if critical:
            critical_count += 1
        if important:
            important_count += 1
        
        photos.append({
            "file_name": img_path.name,
            "notes": normalized,
            "flags": {
                "critical": critical,
                "important": important
            }
        })
    
    return {
        "report_id": report_id,
        "address": address,
        "generated_at": datetime.now().isoformat(),
        "totals": {
            "photos": len(images),
            "critical_issues": critical_count,
            "important_issues": important_count
        },
        "photos": photos
    }

def update_reports_index(report_id: str, address: str, pdf_path: Path, json_path: Path, 
                        photo_count: int, critical_count: int, important_count: int):
    """Update the reports index file with new report record."""
    index_path = Path("output") / "reports_index.json"
    
    # Load existing index or create new
    if index_path.exists():
        with open(index_path, 'r') as f:
            index = json.load(f)
    else:
        index = {"reports": []}
    
    # Add new report record
    new_record = {
        "report_id": report_id,
        "address": address,
        "created_at": datetime.now().isoformat(),
        "pdf_path": str(pdf_path),
        "json_path": str(json_path),
        "photo_count": photo_count,
        "critical_count": critical_count,
        "important_count": important_count
    }
    
    # Upsert - remove old record if exists, add new
    index["reports"] = [r for r in index.get("reports", []) if r.get("report_id") != report_id]
    index["reports"].append(new_record)
    
    # Save updated index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)

# ---------------- Main PDF generator ----------------
def generate_pdf(address: str, images: list[Path], out_pdf: Path) -> dict[Path, str]:
    c = canvas.Canvas(str(out_pdf), pagesize=LETTER)

    # Cover page
    _draw_cover_page(c, address)
    c.showPage()
    _add_page_header(c, address)

    total = len(images)
    start = time.time()

    # Analyze images in parallel (frontend reads these progress lines)
    results: dict[Path, str] = {}
    errs: dict[Path, Exception] = {}
    done = 0

    print(f"Starting analysis of {total} images with {ANALYSIS_CONCURRENCY} workers...", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=ANALYSIS_CONCURRENCY) as ex:
        futs = {ex.submit(_analyze_one, p): p for p in images}
        for fut in concurrent.futures.as_completed(futs):
            p, notes, err = fut.result()
            results[p] = notes
            if err:
                errs[p] = err
            done += 1
            elapsed = time.time() - start
            avg = elapsed / max(1, done)
            eta = int(avg * (total - done))
            print(f"[{done}/{total}] {p.name}  | elapsed {int(elapsed)}s  ETA ~{eta}s", flush=True)

    # Assemble pages
    for p in images:
        _draw_photo(c, p)
        _draw_notes_panel(c, results.get(p, "No visible issues."))
        c.showPage()
        _add_page_header(c, address)

    c.save()

    if errs:
        logger.warning(f"Completed with {len(errs)} image(s) using fallback notes due to errors.")
        for path, error in errs.items():
            logger.debug(f"  {path.name}: {error}")
    
    return results

# ---------------- CLI ----------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, type=Path, help="Path to a .zip containing photos")
    parser.add_argument("--address", required=False, type=str, help="Report title/address (defaults to ZIP name)")
    parser.add_argument("--out", required=False, type=Path, help="Optional output PDF path")
    args = parser.parse_args()

    if not args.zip.exists():
        raise SystemExit(f"ZIP not found: {args.zip}")

    # Generate a unique report ID
    report_id = str(uuid.uuid4())
    
    address = args.address or args.zip.stem.replace("_", " ").replace("-", " ")
    out_pdf = args.out or Path("output") / f"{address}.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    
    # JSON output path based on report_id
    out_json = Path("output") / f"{report_id}.json"

    with tempfile.TemporaryDirectory() as td:
        imgs = collect_images_from_zip(args.zip, Path(td))
        if not imgs:
            raise SystemExit("No images found in ZIP.")
        
        # Generate PDF and get results
        results = generate_pdf(address, imgs, out_pdf)
        
        # Generate JSON report
        json_report = generate_json_report(report_id, address, imgs, results)
        
        # Save JSON file
        with open(out_json, 'w') as f:
            json.dump(json_report, f, indent=2)
        
        # Update reports index
        update_reports_index(
            report_id=report_id,
            address=address,
            pdf_path=out_pdf,
            json_path=out_json,
            photo_count=len(imgs),
            critical_count=json_report["totals"]["critical_issues"],
            important_count=json_report["totals"]["important_issues"]
        )

    print(f"Wrote: {out_pdf}")
    print(f"Wrote: {out_json}")
    print(f"REPORT_ID={report_id}")

if __name__ == "__main__":
    main()
