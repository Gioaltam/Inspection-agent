# Report processor service
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from PIL import Image

from ..storage import StorageService

class ReportProcessor:
    """
    Wraps your run_report + vision flow so it can be triggered from the web backend.
    Produces thumbnails, JSON, and two PDF versions (standard + HQ).
    """

    def __init__(self, storage: StorageService, bucket_name: str):
        self.storage = storage
        self.bucket_name = bucket_name

    # ---------- Entry ----------
    def process_report(
        self,
        photos_dir: str,
        vision_results: Dict[str, str],
        client_id: str,
        property_id: str,
        report_id: str,
    ) -> Dict[str, Any]:

        report_data = {
            "report_id": report_id,
            "property_id": property_id,
            "inspection_date": datetime.utcnow().isoformat(),
            "sections": [],
            "summary": {"total_photos": 0, "critical_count": 0, "important_count": 0},
        }

        thumbnails: List[str] = []
        for idx, (photo_path, analysis_text) in enumerate(vision_results.items()):
            section = self._parse_analysis(analysis_text)

            is_critical = self._is_critical(section)
            is_important = (not is_critical) and self._is_important(section)

            if is_critical:
                report_data["summary"]["critical_count"] += 1
            elif is_important:
                report_data["summary"]["important_count"] += 1

            # Thumbnail
            thumb_path = self._create_thumbnail(photo_path, idx)
            thumb_url = self._upload_thumbnail(thumb_path, client_id, property_id, report_id, idx)
            thumbnails.append(thumb_url)

            # Entry
            orig_key = f"clients/{client_id}/properties/{property_id}/reports/{report_id}/photos/{Path(photo_path).name}"
            original_url = self.storage.get_signed_url(orig_key)

            report_data["sections"].append({
                "photo_index": idx,
                "photo_filename": Path(photo_path).name,
                "thumbnail_url": thumb_url,
                "original_url": original_url,
                "location": section.get("location", ""),
                "materials_description": section.get("materials_description", ""),
                "observations": section.get("observations", []),
                "potential_issues": section.get("potential_issues", []),
                "recommendations": section.get("recommendations", []),
                "is_critical": is_critical,
                "is_important": is_important,
            })

        report_data["summary"]["total_photos"] = len(vision_results)

        # PDFs
        standard_pdf_path = self._generate_pdf(photos_dir, vision_results, compress=True)
        hq_pdf_path = self._generate_pdf(photos_dir, vision_results, compress=False)

        prefix = f"clients/{client_id}/properties/{property_id}/reports/{report_id}"
        json_url = self.storage.upload_json(report_data, f"{prefix}/report.json")
        standard_pdf_url = self.storage.upload_file(standard_pdf_path, f"{prefix}/report-standard.pdf", content_type="application/pdf")
        hq_pdf_url = self.storage.upload_file(hq_pdf_path, f"{prefix}/report-highquality.pdf", content_type="application/pdf")

        return {
            "json_url": json_url,
            "pdf_standard_url": standard_pdf_url,
            "pdf_hq_url": hq_pdf_url,
            "thumbnails": thumbnails,
            "report_data": report_data,
        }

    # ---------- Helpers ----------
    def _parse_analysis(self, text: str) -> Dict[str, Any]:
        sections = {"location": "", "materials_description": "", "observations": [], "potential_issues": [], "recommendations": []}
        current = None
        for raw in text.strip().splitlines():
            line = raw.strip()
            if line.lower().startswith("location:"):
                current = "location"; sections[current] = line.split(":",1)[1].strip()
            elif line.lower().startswith("materials/description:"):
                current = "materials_description"; sections[current] = line.split(":",1)[1].strip()
            elif line.lower().startswith("observations:"):
                current = "observations"
            elif line.lower().startswith("potential issues:"):
                current = "potential_issues"
            elif line.lower().startswith("recommendations:"):
                current = "recommendations"
            elif line.startswith("- ") and current in ("observations","potential_issues","recommendations"):
                sections[current].append(line[2:].strip())
            elif current and line:
                if isinstance(sections[current], list):
                    sections[current].append(line)
                else:
                    sections[current] += " " + line
        return sections

    def _is_critical(self, s: Dict[str, Any]) -> bool:
        keywords = ["structural", "foundation", "roof leak", "electrical hazard", "gas leak", "mold", "asbestos", "safety", "immediate"]
        hay = (" ".join(s.get("potential_issues", [])) + " " + " ".join(s.get("recommendations", []))).lower()
        return any(k in hay for k in keywords)

    def _is_important(self, s: Dict[str, Any]) -> bool:
        keywords = ["repair", "replace", "damage", "deteriorat", "crack", "leak", "moisture", "worn", "failing"]
        hay = (" ".join(s.get("potential_issues", [])) + " " + " ".join(s.get("observations", []))).lower()
        return any(k in hay for k in keywords)

    def _create_thumbnail(self, photo_path: str, index: int, max_size: int = 1200) -> str:
        img = Image.open(photo_path)
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        out = f"/tmp/thumb_{index}.jpg"
        img.save(out, "JPEG", quality=85, optimize=True)
        return out

    def _upload_thumbnail(self, thumb_path: str, client_id: str, property_id: str, report_id: str, idx: int) -> str:
        key = f"clients/{client_id}/properties/{property_id}/reports/{report_id}/thumbs/thumb_{idx}.jpg"
        return self.storage.upload_file(thumb_path, key, content_type="image/jpeg")

    def _generate_pdf(self, photos_dir: str, vision_results: Dict[str, str], compress: bool) -> str:
        """
        Delegates to scripts.bridge.generate_pdf, which calls your existing run_report.py.
        """
        from scripts.bridge import generate_pdf
        out = f"/tmp/report_{'standard' if compress else 'hq'}.pdf"
        if compress:
            photos_dir = self._compress_images(photos_dir)
        generate_pdf(photos_dir, vision_results, out)
        return out

    def _compress_images(self, photos_dir: str) -> str:
        dest = "/tmp/compressed_photos"
        os.makedirs(dest, exist_ok=True)
        for p in Path(photos_dir).glob("*"):
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            img = Image.open(p)
            if max(img.size) > 1920:
                img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            out = Path(dest, p.name).with_suffix(".jpg")
            img.save(out, "JPEG", quality=70, optimize=True)
        return dest
