# Bridge to run_report.generate_pdf
"""
Bridge adapter so the web backend can call your existing PDF generator.

Contract expected by backend:
    generate_pdf(photos_dir: str, vision_results: dict[str, str], output_path: str) -> None

We try to call your real run_report.generate_pdf if available.
Your current run_report.generate_pdf(address, images, out_pdf) signature is different,
so we adapt to it by assembling the image list from photos_dir and using the folder
name as the address/title. If import fails, we fall back to a minimal ReportLab PDF
that uses `vision_results` notes.
"""
from __future__ import annotations
from pathlib import Path

def _collect_images(photos_dir: str) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    imgs = [p for p in Path(photos_dir).rglob("*") if p.suffix.lower() in exts]
    imgs.sort()
    return imgs

def generate_pdf(photos_dir: str, vision_results: dict[str, str], output_path: str) -> None:
    # Try to use your real implementation (preferred)
    try:
        # If you kept run_report.py at project root
        import run_report as rr  # type: ignore
    except Exception:
        try:
            # If you moved it under scripts/
            from scripts import run_report as rr  # type: ignore
        except Exception:
            rr = None

    images = _collect_images(photos_dir)
    address = Path(photos_dir).resolve().name or "Property Report"

    if rr and hasattr(rr, "generate_pdf"):
        # Your run_report has signature: generate_pdf(address, images, out_pdf)
        rr.generate_pdf(address, images, Path(output_path))
        return

    # ---------- Fallback: simple ReportLab PDF using vision_results ----------
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import inch
    from PIL import Image as PILImage, ImageOps
    import tempfile
    import os

    c = canvas.Canvas(output_path, pagesize=letter)
    W, H = letter

    # Cover
    c.setFont("Helvetica-Bold", 24)
    c.drawString(72, H - 96, "Property Inspection Report")
    c.setFont("Helvetica", 12)
    c.drawString(72, H - 120, f"{address}")
    c.showPage()

    # Pages
    for p in images:
        try:
            # Auto-rotate image based on EXIF orientation before adding to PDF
            with PILImage.open(p) as pil_img:
                # Apply EXIF orientation
                try:
                    pil_img = ImageOps.exif_transpose(pil_img)
                except Exception:
                    pass  # If EXIF handling fails, use image as-is
                
                # Convert to RGB if necessary
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                
                # Save to temporary file with correct orientation
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    pil_img.save(tmp.name, 'JPEG', quality=85)
                    temp_path = tmp.name
            
            # Now use the corrected image in PDF
            img = ImageReader(temp_path)
            iw, ih = img.getSize()
            max_w, max_h = W - 120, H - 170
            scale = min(max_w / iw, max_h / ih)
            dw, dh = iw * scale, ih * scale
            x = (W - dw) / 2
            y = (H - dh) / 2 + 20
            c.drawImage(img, x, y, dw, dh, preserveAspectRatio=True, mask="auto")
            
            # Clean up temp file
            os.unlink(temp_path)

            # Notes (if provided)
            note = vision_results.get(str(p), "") or vision_results.get(p.name, "")
            if note:
                c.setFont("Helvetica", 10)
                c.drawString(72, 72, (note[:300] + ("…" if len(note) > 300 else "")))
            c.showPage()
        except Exception:
            continue

    c.save()
