# C:\inspection-agent\vision.py
import os, io, base64, mimetypes, hashlib, re, traceback
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps

# Load .env and sanitize the key for safety
load_dotenv(override=True)
if os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY").strip()

client = OpenAI()

# ---------------- Tunables (override via .env if desired) ----------------
# Stricter home‑inspection instructions. We still allow free text because run_report.py
# normalizes sections, but we strongly suggest section headers to the model.
SYSTEM = (
    "You are an expert home inspector. Analyze the photo and produce concise, factual notes "
    "with the following sections and only short bullet lines:\n"
    "Location:\n"
    "Observations: (materials/description go here; no actions)\n"
    "Potential Issues: (ONLY real defects/safety concerns. Be explicit.)\n"
    "Recommendations: (repairs, sealing, cleaning, evaluation, etc.)\n\n"
    "Explicitly check for and include in Potential Issues if present: dents, bends, warping, "
    "cracks, gaps/voids/separations, loose or missing parts/fasteners, misalignment, failed or "
    "missing sealant/caulk, substrate exposure, corrosion/rust, water intrusion/leaks/stains, "
    "mold/mildew/rot, improper wiring or missing conduit, blocked/unsafe conditions, trip/fall "
    "hazards, pest entry points. If nothing notable: 'No visible issues.'"
)

# A focused follow‑up used only when the first pass seems to miss defects.
SECOND_PASS_NUDGE = (
    "Re-check the SAME photo and list ALL visible defects in the 'Potential Issues' section if present. "
    "Focus on physical damage: dents/bends/warping, cracks, gaps/voids, loose or missing parts, failed/missing "
    "sealant, substrate exposure, corrosion/rust, water intrusion, mold/rot. Keep bullets short."
)

ANALYSIS_MAX_PX = int(os.getenv("ANALYSIS_MAX_PX", "1600"))  # downscale long side for analysis only
CACHE_DIR = Path(os.getenv("ANALYSIS_CACHE_DIR", ".cache"))
CACHE_DIR.mkdir(exist_ok=True)


# ---------------- Image helpers ----------------
def _mime_type(p: Path) -> str:
    mt, _ = mimetypes.guess_type(str(p))
    if mt:
        return mt
    return "image/jpeg" if p.suffix.lower() in {".jpg", ".jpeg"} else "image/png"


def _b64_bytes(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _data_url_from_bytes(b: bytes, mime: str) -> str:
    return f"data:{mime};base64,{_b64_bytes(b)}"


def _analysis_image_bytes(src: Path) -> tuple[bytes, str]:
    """
    Return (bytes, mime) for a downscaled copy used ONLY for model analysis.
    The PDF still embeds the original file at full quality elsewhere.
    """
    mime = _mime_type(src)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        w, h = im.size
        scale = 1.0
        if max(w, h) > ANALYSIS_MAX_PX:
            scale = ANALYSIS_MAX_PX / float(max(w, h))
        if scale < 1.0:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        if mime == "image/png":
            im.save(buf, format="PNG", optimize=True)
        else:
            im = im.convert("RGB")
            im.save(buf, format="JPEG", quality=88, optimize=True)
            mime = "image/jpeg"
        return buf.getvalue(), mime


# ---------------- Disk cache (speed up re-runs) ----------------
def _cache_key(image_path: Path) -> str:
    h = hashlib.sha1()
    try:
        h.update(image_path.read_bytes())
    except Exception:
        h.update(str(image_path).encode("utf-8"))
    h.update(SYSTEM.encode("utf-8"))
    h.update(os.getenv("VISION_MODEL", "gpt-5-nano").encode("utf-8"))
    h.update(str(ANALYSIS_MAX_PX).encode("utf-8"))
    return h.hexdigest()


def _cache_get(image_path: Path) -> str | None:
    f = CACHE_DIR / f"{_cache_key(image_path)}.txt"
    if f.exists():
        try:
            text = f.read_text(encoding="utf-8").strip()
            print(f"[vision] CACHE HIT for {image_path.name}", flush=True)
            return text
        except Exception:
            return None
    return None


def _cache_put(image_path: Path, text: str) -> None:
    (CACHE_DIR / f"{_cache_key(image_path)}.txt").write_text(text.strip(), encoding="utf-8")


# ---------------- Heuristics to detect a weak first pass ----------------
_DEFECT_WORDS_RE = re.compile(
    r"\b(issue|defect|damage|leak|intrusion|stain|crack|dent|bend|warp|gap|separation|"
    r"loose|missing|rot|mold|mildew|corrosion|rust|unsafe|hazard|trip|void|broken|"
    r"exposed|unsealed|failed|compromised)\b",
    re.I,
)

def _looks_empty_or_safe(text: str) -> bool:
    """Return True if the model output likely missed all problems."""
    if not text or not text.strip():
        return True
    s = text.lower()
    # No Potential Issues section AND no classic defect words anywhere
    if "potential issues" not in s and not _DEFECT_WORDS_RE.search(s):
        return True
    return False


# ---------------- Public API ----------------
def describe_image(image_path: Path) -> str:
    """
    Analyze one image with the model and return notes as text.
    Uses downscaled copy for speed but leaves PDF quality untouched.
    Caches results on disk for instant re-runs.

    Diagnostics: prints whether API or cache was used, and any API errors.
    """
    # Sanity: key present?
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing or empty in .env")

    cached = _cache_get(image_path)
    if cached:
        return cached

    model = os.getenv("VISION_MODEL", "gpt-5-nano")
    img_bytes, mime = _analysis_image_bytes(image_path)

    try:
        # ---------- First pass ----------
        print(f"[vision] Calling model={model} for {image_path.name}", flush=True)
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM}]},
                {"role": "user", "content": [
                    {"type": "input_text", "text": "Analyze this property photo and produce concise inspection notes."},
                    {"type": "input_image", "image_url": _data_url_from_bytes(img_bytes, mime)},
                ]},
            ],
        )
        out = (getattr(resp, "output_text", None) or "").strip()

        # ---------- Second pass (defect-focused) if needed ----------
        if _looks_empty_or_safe(out):
            print(f"[vision] Second pass nudge for {image_path.name}", flush=True)
            resp2 = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": SYSTEM}]},
                    {"role": "user", "content": [
                        {"type": "input_text", "text": SECOND_PASS_NUDGE},
                        {"type": "input_image", "image_url": _data_url_from_bytes(img_bytes, mime)},
                    ]},
                ],
            )
            out2 = (getattr(resp2, "output_text", None) or "").strip()
            if out2:
                out = out2

        if not out:
            print("[vision] WARNING: Model returned no output_text; not caching.", flush=True)
            return "No visible issues."

        _cache_put(image_path, out)
        return out

    except Exception as e:
        print("[vision] API ERROR:", repr(e), flush=True)
        traceback.print_exc()
        # Do not cache fallback; allow future retries
        return "No visible issues."
