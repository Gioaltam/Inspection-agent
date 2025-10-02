from __future__ import annotations

from pathlib import Path
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

from ..lib.paths import (
    find_latest_report_dir_by_address,
    photos_dir_for_report_dir,
    list_photos_in_dir,
)

router = APIRouter(prefix="/api/photos", tags=["photos"])

def _ensure_within(base: Path, candidate: Path) -> None:
    """
    Ensure candidate is inside base to prevent path traversal attacks.
    """
    base_r = base.resolve()
    cand_r = candidate.resolve()
    try:
        cand_r.relative_to(base_r)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

@router.get("/property/{address}")
def list_property_photos(address: str):
    """
    Returns photo metadata + URLs for the most recent report for this address.
    """
    report_dir = find_latest_report_dir_by_address(address)
    if report_dir is None:
        return {"address": address, "count": 0, "items": []}

    photos_dir = photos_dir_for_report_dir(report_dir)
    files = list_photos_in_dir(photos_dir)
    items = [
        {
            "name": f.name,
            # The URL below is another endpoint in this file that serves the binary
            "url": f"/api/photos/property/{quote(address)}/{quote(f.name)}",
        }
        for f in files
    ]
    return {"address": address, "count": len(items), "items": items}

@router.get("/property/{address}/{filename}")
def serve_property_photo(address: str, filename: str):
    """
    Serves an individual photo file from the latest report for this address.
    """
    report_dir = find_latest_report_dir_by_address(address)
    if report_dir is None:
        raise HTTPException(status_code=404, detail="No report for address")

    photos_dir = photos_dir_for_report_dir(report_dir)
    file_path = photos_dir / filename

    _ensure_within(photos_dir, file_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")

    # Let Starlette guess the media type from the file extension
    return FileResponse(str(file_path))