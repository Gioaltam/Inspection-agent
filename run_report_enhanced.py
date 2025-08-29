# Enhanced version of run_report.py that preserves photos
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
import shutil
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
load_dotenv(override=False)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ANALYSIS_CONCURRENCY = int(os.getenv("ANALYSIS_CONCURRENCY", "3"))

# Output directory for photos
PHOTOS_OUTPUT_DIR = Path("output/photos")
PHOTOS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Page geometry
PAGE_W, PAGE_H = LETTER
MARGIN = 0.5 * inch

# Photo-left / Notes-right geometry
IMG_MAX_W = 3.6 * inch
IMG_MAX_H = 8.0 * inch
NOTEBOX_X = MARGIN + IMG_MAX_W + 0.4 * inch
NOTEBOX_W = PAGE_W - NOTEBOX_X - MARGIN
NOTEBOX_BASE_H = IMG_MAX_H

# Branding / style knobs
BANNER_PATH       = os.getenv("BANNER_PATH", "assets/banner.png")
BRAND_PRIMARY     = os.getenv("BRAND_PRIMARY", "#0b1e2e")
BRAND_SECONDARY   = os.getenv("BRAND_SECONDARY", "#113a5c")
NOTES_FONT_PT     = float(os.getenv("NOTES_FONT_PT", "12.0"))
NOTES_LEADING_PT  = float(os.getenv("NOTES_LEADING_PT", "16.0"))
COVER_TITLE_SHIFT_LEFT_IN = float(os.getenv("COVER_TITLE_SHIFT_LEFT_IN", "0.60"))
RECOMMENDATIONS_EXTRA_GAP_PT = float(os.getenv("RECOMMENDATIONS_EXTRA_GAP_PT", "10"))

# Status icon sources
STATUS_CRITICAL_ICON  = os.getenv("STATUS_CRITICAL_ICON", "assets/critical.png")
STATUS_IMPORTANT_ICON = os.getenv("STATUS_IMPORTANT_ICON", "assets/important.png")
STATUS_SPRITE         = os.getenv("STATUS_SPRITE", "assets/icons.png")
STATUS_ICON_PT        = float(os.getenv("STATUS_ICON_PT", "30"))
STATUS_ICON_LABEL_SIZE = float(os.getenv("STATUS_ICON_LABEL_SIZE", "11.5"))

# Repair keywords
REPAIR_KEYWORDS = os.getenv(
    "REPAIR_KEYWORDS",
    "repair,replace,fix,seal,reseal,re-caulk,caulk,secure,anchor,tighten,patch,service,clean and,clean,paint,repaint"
).split(",")

# Cover page info
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
    if low.startswith(("issue","risk","hazard","safety","concern","defect","damage","deteriorat","leak","moisture","mold","rot","crack","corrosion")):
        return "Potential Issues", (l.split(":",1)[-1].strip() if ":" in l else l)
    if any(k in low for k in ["cmu block","drywall","lap siding","asphalt shingle","concrete","paver","brick","plaster"]):
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
            for line in _split_candidate_lines(joined):
                sect, val = _route_line(line)
                if val: res[sect].append(val)
    else:
        lines = _split_candidate_lines(str(note_text_or_dict))
        for line in lines:
            sect, val = _route_line(line)
            if val: res[sect].append(val)
    return res

def _detect_status_flags(data_dict: dict) -> tuple[bool,bool]:
    critical = important = False
    issues = data_dict.get("Potential Issues", [])
    recs = data_dict.get("Recommendations", [])
    all_text = " ".join(issues + recs).lower()
    
    critical_keywords = ["immediate","hazard","unsafe","danger","critical","emergency","structural failure","electrical hazard","gas leak","fire risk"]
    important_keywords = ["repair","replace","fix ","seal","reseal","should be","needs to be","recommend","moisture","leak","corrosion","damage"]
    
    if any(kw in all_text for kw in critical_keywords):
        critical = True
    if any(kw in all_text for kw in important_keywords):
        important = True
    
    return critical, important

def _sprite_split_if_needed() -> tuple[str|None, str|None]:
    if STATUS_SPRITE and os.path.exists(STATUS_SPRITE):
        try:
            img = Image.open(STATUS_SPRITE)
            w, h = img.size
            if w >= h * 1.5:
                midpoint = w // 2
                left_img = img.crop((0, 0, midpoint, h))
                right_img = img.crop((midpoint, 0, w, h))
                import io
                left_buf = io.BytesIO()
                right_buf = io.BytesIO()
                left_img.save(left_buf, format='PNG')
                right_img.save(right_buf, format='PNG')
                left_buf.seek(0)
                right_buf.seek(0)
                return left_buf, right_buf
        except Exception:
            pass
    return None, None

def _build_note_paragraphs(note_text_or_dict):
    normalized = _normalize_observation(note_text_or_dict)
    paras = []
    for sect_name in ORDERED_SECTIONS:
        items = normalized.get(sect_name, [])
        if not items:
            continue
        style = NOTE_SECTION_RECS if sect_name == "Recommendations" else NOTE_SECTION
        paras.append(Paragraph(f"<b>{sect_name}:</b>", style))
        for item in items:
            paras.append(Paragraph(f"• {item}", NOTE_BULLET))
    return paras, normalized

def _measure_total_height(flows, avail_width) -> float:
    total_h = 0
    for f in flows:
        w, h = f.wrapOn(None, avail_width, 1e6)
        total_h += h
    return total_h

def _brand_bar(c: canvas.Canvas):
    if os.path.exists(BANNER_PATH):
        c.drawImage(BANNER_PATH, MARGIN, PAGE_H - MARGIN - 0.75*inch, width=PAGE_W - 2*MARGIN, height=0.75*inch, preserveAspectRatio=True)

def _add_page_header(c: canvas.Canvas, address: str):
    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor(BRAND_PRIMARY))
    c.drawString(MARGIN, PAGE_H - MARGIN/2, f"Property Inspection: {address}")

def _draw_cover_page(c: canvas.Canvas, address: str):
    _brand_bar(c)
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(HexColor(BRAND_PRIMARY))
    c.drawString(PAGE_W/2 - COVER_TITLE_SHIFT_LEFT_IN * inch, PAGE_H/2, "Property Inspection Report")
    c.setFont("Helvetica", 18)
    c.drawString(PAGE_W/2 - COVER_TITLE_SHIFT_LEFT_IN * inch, PAGE_H/2 - 30, address)
    c.setFont("Helvetica", 12)
    c.drawString(PAGE_W/2 - COVER_TITLE_SHIFT_LEFT_IN * inch, PAGE_H/2 - 60, f"Date: {datetime.now().strftime('%B %d, %Y')}")
    
    if BUSINESS_NAME:
        c.setFont("Helvetica", 11)
        c.drawString(PAGE_W/2 - COVER_TITLE_SHIFT_LEFT_IN * inch, PAGE_H/2 - 120, "Prepared by:")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(PAGE_W/2 - COVER_TITLE_SHIFT_LEFT_IN * inch, PAGE_H/2 - 140, BUSINESS_NAME)
        if BUSINESS_LINE1:
            c.setFont("Helvetica", 11)
            c.drawString(PAGE_W/2 - COVER_TITLE_SHIFT_LEFT_IN * inch, PAGE_H/2 - 160, BUSINESS_LINE1)
        if BUSINESS_LINE2:
            c.drawString(PAGE_W/2 - COVER_TITLE_SHIFT_LEFT_IN * inch, PAGE_H/2 - 180, BUSINESS_LINE2)

def _draw_photo(c: canvas.Canvas, img_path: Path, compress_for_pdf=True):  # Default to True for print-optimized
    try:
        img = Image.open(img_path)
        img = ImageOps.exif_transpose(img)
        w, h = img.size
        
        # Always optimize for print (good quality but reasonable file size)
        if compress_for_pdf:
            # 1200px is good for print quality at 150-200 DPI
            max_dim = 1200
            if w > max_dim or h > max_dim:
                scale = min(max_dim / w, max_dim / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                w, h = new_w, new_h
            
            # Convert to RGB and compress as JPEG with good quality for print
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Use BytesIO to compress in memory - 80 quality is good for print
            import io
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=80, optimize=True)
            buffer.seek(0)
            img = Image.open(buffer)
        
        aspect = w / h
        if w > IMG_MAX_W * 72 / inch or h > IMG_MAX_H * 72 / inch:
            scale_w = (IMG_MAX_W * 72 / inch) / w
            scale_h = (IMG_MAX_H * 72 / inch) / h
            scale = min(scale_w, scale_h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        img_reader = ImageReader(img)
        c.drawImage(img_reader, MARGIN, PAGE_H - MARGIN - IMG_MAX_H, width=IMG_MAX_W, height=IMG_MAX_H, preserveAspectRatio=True, anchor='nw')
    except Exception as e:
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, PAGE_H - MARGIN - 20, f"[Image error: {e}]")

def _draw_notes_panel(c: canvas.Canvas, note_text_or_dict):
    paras, normalized = _build_note_paragraphs(note_text_or_dict)
    critical, important = _detect_status_flags(normalized)
    
    total_h = _measure_total_height(paras, NOTEBOX_W)
    box_h = max(NOTEBOX_BASE_H, total_h + 0.3 * inch)
    
    frame = Frame(NOTEBOX_X, PAGE_H - MARGIN - box_h, NOTEBOX_W, box_h, showBoundary=0, leftPadding=6, rightPadding=6, topPadding=6, bottomPadding=6)
    frame.addFromList(paras, c)
    
    return critical, important

def collect_images_from_zip(zip_path: Path, workdir: Path) -> list[Path]:
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(workdir)
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    imgs = [p for p in Path(workdir).rglob("*") if p.suffix.lower() in exts]
    imgs.sort()
    return imgs

def _analyze_one(p: Path) -> tuple[Path, str, Exception | None]:
    try:
        notes = describe_image(p)
        return p, notes, None
    except Exception as e:
        logger.warning(f"Failed to analyze {p.name}: {e}")
        return p, "", e

def preserve_photos(report_id: str, images: list[Path]) -> dict[Path, str]:
    """Copy photos to output directory and return mapping of original to web paths."""
    photo_dir = PHOTOS_OUTPUT_DIR / report_id
    photo_dir.mkdir(parents=True, exist_ok=True)
    
    photo_mapping = {}
    for idx, img_path in enumerate(images):
        # Create a clean filename
        ext = img_path.suffix.lower()
        new_filename = f"photo_{idx+1:03d}{ext}"
        dest_path = photo_dir / new_filename
        
        # Copy and optionally resize for web
        try:
            img = Image.open(img_path)
            img = ImageOps.exif_transpose(img)
            
            # Resize if too large (max 1920px wide for web)
            if img.width > 1920:
                ratio = 1920 / img.width
                new_size = (1920, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Save with optimization
            if ext in ['.jpg', '.jpeg']:
                img.save(dest_path, 'JPEG', quality=85, optimize=True)
            else:
                img.save(dest_path, 'PNG', optimize=True)
            
            # Store the web-relative path
            web_path = f"photos/{report_id}/{new_filename}"
            photo_mapping[img_path] = web_path
            
        except Exception as e:
            logger.warning(f"Failed to preserve photo {img_path.name}: {e}")
            photo_mapping[img_path] = None
    
    return photo_mapping

def generate_json_report_with_photos(report_id: str, address: str, images: list[Path], 
                                    results: dict[Path, str], photo_mapping: dict[Path, str]) -> dict:
    """Generate JSON report with photos and normalized notes."""
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
        
        photo_data = {
            "file_name": img_path.name,
            "image_path": photo_mapping.get(img_path),  # Add the web path to the photo
            "notes": normalized,
            "flags": {
                "critical": critical,
                "important": important
            }
        }
        photos.append(photo_data)
    
    report = {
        "report_id": report_id,
        "address": address,
        "generated_at": datetime.now().isoformat(),
        "totals": {
            "photos": len(photos),
            "critical_issues": critical_count,
            "important_issues": important_count
        },
        "photos": photos
    }
    
    return report

def generate_standalone_html(report_id: str, address: str, json_report: dict) -> Path:
    """Generate a standalone HTML file for the property with embedded data."""
    html_template_path = Path("output/interactive_gallery.html")
    
    # Read the template
    with open(html_template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Create embedded data script
    json_str = json.dumps(json_report, indent=2)
    
    # Find and replace the entire fetch block with embedded data
    # This pattern matches the fetch and its .then() chains
    fetch_pattern = r"// Load report data\s*\n\s*fetch\(`\$\{reportId\}\.json`\)"
    
    # Create the replacement with embedded data
    embedded_script = f"""// Load report data - EMBEDDED
        const embeddedReportData = {json_str};
        Promise.resolve(embeddedReportData)"""
    
    # Replace the fetch with embedded data
    html_content = html_content.replace("// Load report data\n        fetch(`${reportId}.json`)", embedded_script)
    
    # Also need to fix the .then() chain to handle direct data instead of fetch response
    # Replace the response handling
    response_pattern = r"\.then\(response => \{\s+if \(!response\.ok\) throw new Error\('Report not found'\);\s+return response\.json\(\);\s+\}\)"
    html_content = re.sub(response_pattern, "", html_content)
    
    # Also update the report ID since we're not using URL params
    url_param_pattern = r"const reportId = urlParams\.get\('id'\) \|\| '[^']+'"
    html_content = re.sub(url_param_pattern, f"const reportId = '{report_id}'", html_content)
    
    # Generate output filename based on address
    safe_address = re.sub(r'[^\w\s-]', '', address).strip().replace(' ', '_')
    output_filename = f"{safe_address}_{report_id[:8]}.html"
    output_path = Path("output") / output_filename
    
    # Save the standalone HTML
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"Generated standalone HTML: {output_path}")
    return output_path

def update_reports_index(report_id: str, address: str, pdf_path: Path, json_path: Path, 
                        html_path: Path = None):
    """Update the reports index file."""
    index_file = Path("output/reports_index.json")
    
    try:
        if index_file.exists():
            with open(index_file, 'r') as f:
                index = json.load(f)
        else:
            index = {"reports": []}
    except:
        index = {"reports": []}
    
    # Add new report
    report_entry = {
        "report_id": report_id,
        "address": address,
        "generated_at": datetime.now().isoformat(),
        "pdf_path": str(pdf_path.relative_to(Path("output"))),
        "json_path": str(json_path.relative_to(Path("output"))),
    }
    
    if html_path:
        report_entry["html_path"] = str(html_path.relative_to(Path("output")))
    
    # Remove duplicate if exists
    index["reports"] = [r for r in index["reports"] if r["report_id"] != report_id]
    index["reports"].insert(0, report_entry)
    
    # Save updated index
    with open(index_file, 'w') as f:
        json.dump(index, f, indent=2)

def analyze_images_concurrently(images: list[Path]) -> dict[Path, str]:
    """Analyze images without generating PDF."""
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=ANALYSIS_CONCURRENCY) as executor:
        future_to_img = {executor.submit(describe_image, img): img for img in images}
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_img), 1):
            img_path = future_to_img[future]
            try:
                result = future.result()
                results[img_path] = result
                print(f"  [{i}/{len(images)}] Analyzed: {img_path.name}")
            except Exception as e:
                logger.error(f"Error analyzing {img_path}: {e}")
                results[img_path] = f"Error analyzing image: {e}"
    
    return results

def generate_pdf_with_photos(address: str, images: list[Path], out_pdf: Path, full_resolution=False) -> dict[Path, str]:
    """Generate PDF report with photos. Default is print-optimized (compressed)."""
    c = canvas.Canvas(str(out_pdf), pagesize=LETTER)
    
    # Cover page
    _draw_cover_page(c, address)
    c.showPage()
    _add_page_header(c, address)
    
    total = len(images)
    start = time.time()
    
    # Analyze images in parallel
    results: dict[Path, str] = {}
    errs: dict[Path, Exception] = {}
    done = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=ANALYSIS_CONCURRENCY) as executor:
        futures = {executor.submit(_analyze_one, p): p for p in images}
        
        for future in concurrent.futures.as_completed(futures):
            done += 1
            p, notes, err = future.result()
            
            if err:
                errs[p] = err
                results[p] = "Analysis failed - no visible issues noted."
            else:
                results[p] = notes
            
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            
            print(f"[{done}/{total}] Analyzed: {p.name} | Rate: {rate:.1f}/s | ETA: {eta:.0f}s")
    
    # Draw photos and notes
    for i, img_path in enumerate(images):
        if i > 0:
            c.showPage()
            _add_page_header(c, address)
        
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(HexColor(BRAND_PRIMARY))
        c.drawString(MARGIN, PAGE_H - MARGIN + 10, f"Photo {i+1} of {total}: {img_path.name}")
        
        _draw_photo(c, img_path, compress_for_pdf=(not full_resolution))
        
        note_text = results.get(img_path, "No notes available.")
        critical, important = _draw_notes_panel(c, note_text)
        
        # Draw status icons if needed
        if critical or important:
            left_buf, right_buf = _sprite_split_if_needed()
            icon_y = PAGE_H - MARGIN - IMG_MAX_H - STATUS_ICON_PT - 10
            
            if critical:
                icon_src = left_buf if left_buf else STATUS_CRITICAL_ICON
                if icon_src:
                    try:
                        if isinstance(icon_src, str):
                            c.drawImage(icon_src, MARGIN, icon_y, width=STATUS_ICON_PT, height=STATUS_ICON_PT)
                        else:
                            c.drawImage(ImageReader(icon_src), MARGIN, icon_y, width=STATUS_ICON_PT, height=STATUS_ICON_PT)
                    except:
                        pass
                c.setFont("Helvetica-Bold", STATUS_ICON_LABEL_SIZE)
                c.setFillColor("#cc0000")
                c.drawString(MARGIN + STATUS_ICON_PT + 5, icon_y + 5, "CRITICAL")
            
            if important:
                x_offset = MARGIN + (STATUS_ICON_PT + 70 if critical else 0)
                icon_src = right_buf if right_buf else STATUS_IMPORTANT_ICON
                if icon_src:
                    try:
                        if isinstance(icon_src, str):
                            c.drawImage(icon_src, x_offset, icon_y, width=STATUS_ICON_PT, height=STATUS_ICON_PT)
                        else:
                            c.drawImage(ImageReader(icon_src), x_offset, icon_y, width=STATUS_ICON_PT, height=STATUS_ICON_PT)
                    except:
                        pass
                c.setFont("Helvetica-Bold", STATUS_ICON_LABEL_SIZE)
                c.setFillColor("#ff6600")
                c.drawString(x_offset + STATUS_ICON_PT + 5, icon_y + 5, "IMPORTANT")
    
    c.save()
    return results

def main():
    parser = argparse.ArgumentParser(description="Generate inspection report from photos")
    parser.add_argument("input", help="ZIP file or directory containing photos")
    parser.add_argument("-a", "--address", default="Property", help="Property address")
    parser.add_argument("-o", "--output", help="Output PDF filename")
    parser.add_argument("--preserve-photos", action="store_true", help="Preserve photos for web viewing")
    parser.add_argument("--full-res-pdf", action="store_true", help="Generate PDF with full resolution images (warning: large file size)")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation (HTML only)")
    args = parser.parse_args()
    
    # Generate report ID
    report_id = str(uuid.uuid4())
    
    # Set up paths
    input_path = Path(args.input)
    address = args.address
    output_filename = args.output or f"{address.replace(' ', '_')}.pdf"
    out_pdf = Path("output") / output_filename
    out_json = Path("output") / f"{report_id}.json"
    
    # Ensure output directory exists
    Path("output").mkdir(exist_ok=True)
    
    # Collect images
    if input_path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmpdir:
            images = collect_images_from_zip(input_path, Path(tmpdir))
            
            if args.preserve_photos:
                # Preserve photos for web viewing
                photo_mapping = preserve_photos(report_id, images)
            else:
                photo_mapping = {img: None for img in images}
            
            # Generate PDF if not skipped
            if not args.no_pdf:
                print(f"\nGenerating {'full resolution' if args.full_res_pdf else 'print-optimized'} PDF for {len(images)} images...")
                results = generate_pdf_with_photos(address, images, out_pdf, full_resolution=args.full_res_pdf)
            else:
                print(f"\nAnalyzing {len(images)} images (PDF generation skipped)...")
                results = analyze_images_concurrently(images)
            
            # Generate JSON with photo paths
            json_report = generate_json_report_with_photos(report_id, address, images, results, photo_mapping)
    else:
        images = list(input_path.glob("*"))
        images = [p for p in images if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
        images.sort()
        
        if args.preserve_photos:
            photo_mapping = preserve_photos(report_id, images)
        else:
            photo_mapping = {img: None for img in images}
        
        if not args.no_pdf:
            print(f"\n🔍 Generating {'full resolution' if args.full_res_pdf else 'print-optimized'} PDF for {len(images)} images...")
            results = generate_pdf_with_photos(address, images, out_pdf, full_resolution=args.full_res_pdf)
        else:
            print(f"\n🔍 Analyzing {len(images)} images (PDF generation skipped)...")
            results = analyze_images_concurrently(images)
        json_report = generate_json_report_with_photos(report_id, address, images, results, photo_mapping)
    
    # Save JSON report
    with open(out_json, 'w') as f:
        json.dump(json_report, f, indent=2)
    
    # Copy gallery template to create individual HTML file for this report
    template_path = OUTPUT_DIR / "gallery_template.html"
    safe_address = re.sub(r'[^\w\s-]', '', address).strip().replace(' ', '_').lower()
    out_html = OUTPUT_DIR / f"{safe_address}_{report_id[:8]}.html"
    
    if template_path.exists():
        # Read template and replace the default report ID
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Replace the default report ID with this specific report's ID
        template_content = template_content.replace(
            "const reportId = urlParams.get('id') || 'eab3af62-1ce6-4086-bcf3-8be09e930e61';",
            f"const reportId = urlParams.get('id') || '{report_id}';"
        )
        
        # Write the customized template
        with open(out_html, 'w', encoding='utf-8') as f:
            f.write(template_content)
    else:
        # Fallback to old method if template doesn't exist
        out_html = generate_standalone_html(report_id, address, json_report)
    
    # Update reports index
    update_reports_index(report_id, address, out_pdf, out_json, out_html)
    
    print(f"\nReport generated successfully!")
    if not args.no_pdf:
        print(f"PDF: {out_pdf} ({'full resolution - large file!' if args.full_res_pdf else 'print-optimized'})")
    print(f"JSON: {out_json}")
    print(f"HTML: {out_html} (best for interactive viewing)")
    if args.preserve_photos:
        print(f"Photos: output/photos/{report_id}/")
    print(f"\nView in browser: http://localhost:8080/interactive_gallery.html?id={report_id}")
    print(f"Or open standalone HTML: {out_html}")

if __name__ == "__main__":
    main()