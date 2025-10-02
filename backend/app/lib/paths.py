from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

# Image types we consider as inspection photos
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

_TS_RE = re.compile(r"^(?P<addr>.+)_(?P<date>\d{8})_(?P<time>\d{6})$")

def repo_root() -> Path:
    # backend/app/lib/paths.py -> parents[3] is the repository root
    return Path(__file__).resolve().parents[3]

def outputs_root() -> Path:
    # Allow override; else default to <repo>/workspace/outputs
    env = os.getenv("OUTPUTS_DIR")
    base = Path(env).expanduser().resolve() if env else (repo_root() / "workspace" / "outputs")
    base.mkdir(parents=True, exist_ok=True)
    return base

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def find_latest_report_dir_by_address(address: str) -> Optional[Path]:
    """
    Finds the most recent report directory under outputs for the given address.
    Matches folder names like: "<address>_YYYYMMDD_HHMMSS"
    If no timestamped dir exists, will also accept a dir exactly equal to address.
    """
    root = outputs_root()
    want = _norm(address)
    best: Optional[Path] = None

    for d in root.iterdir():
        if not d.is_dir():
            continue

        m = _TS_RE.match(d.name)
        addr_part = _norm(m.group("addr") if m else d.name)
        if addr_part != want:
            continue

        if best is None or d.stat().st_mtime > best.stat().st_mtime:
            best = d

    return best

def photos_dir_for_report_dir(report_dir: Path) -> Path:
    # Reports write web assets under <report>/web/photos
    return report_dir / "web" / "photos"

def list_photos_in_dir(p: Path) -> List[Path]:
    if not p.exists():
        return []
    return sorted([f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMG_EXTS])