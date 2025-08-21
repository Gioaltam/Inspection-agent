# Admin endpoints
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import tempfile, zipfile, os, shutil
from uuid import uuid4

from ..database import get_db
from ..auth import get_current_admin
from ..models import Property, Report, Asset
from ..services.report_processor import ReportProcessor
from ..storage import StorageService
from ..config import settings

router = APIRouter()

@router.post("/upload-report")
async def upload_report_zip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    client_id: str = Form(...),
    property_id: str = Form(...),
    current_admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    # Verify property belongs to client
    prop = db.query(Property).filter(Property.id == property_id, Property.client_id == client_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Save uploaded zip temporarily
    temp_dir = tempfile.mkdtemp(prefix="upload_")
    zip_path = os.path.join(temp_dir, file.filename)
    with open(zip_path, "wb") as f:
        f.write(await file.read())

    # New report ID
    report_id = str(uuid4())

    # Process asynchronously
    background_tasks.add_task(
        process_report_upload,
        zip_path=zip_path,
        client_id=client_id,
        property_id=property_id,
        report_id=report_id,
    )

    return {"message": "Report upload initiated", "report_id": report_id, "status": "processing"}


def _extract_zip(zip_path: str) -> str:
    extract_dir = tempfile.mkdtemp(prefix="photos_")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)
    # prefer "photos" subfolder if present
    photos = os.path.join(extract_dir, "photos")
    return photos if os.path.isdir(photos) else extract_dir


def _upload_originals(storage: StorageService, photos_dir: str, prefix: str):
    """Upload all original images so report JSON can link back."""
    for name in os.listdir(photos_dir):
        full = os.path.join(photos_dir, name)
        if os.path.isfile(full) and name.lower().endswith((".jpg", ".jpeg", ".png")):
            storage.upload_file(full, f"{prefix}/photos/{name}", content_type="image/jpeg")


async def process_report_upload(zip_path: str, client_id: str, property_id: str, report_id: str):
    extract_dir = ""
    try:
        # 1. Extract photos
        photos_dir = _extract_zip(zip_path)
        extract_dir = photos_dir

        # 2. Run vision analysis (hook into your vision.py)
        from scripts.vision import analyze_photos
        vision_results = analyze_photos(photos_dir)

        # 3. Init storage & processor
        storage = StorageService(settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY, settings.S3_BUCKET_NAME, settings.S3_ENDPOINT_URL)
        processor = ReportProcessor(storage, settings.S3_BUCKET_NAME)

        prefix = f"clients/{client_id}/properties/{property_id}/reports/{report_id}"
        _upload_originals(storage, photos_dir, prefix)

        # 4. Generate report outputs (PDFs + JSON + thumbs)
        result = processor.process_report(
            photos_dir=photos_dir,
            vision_results=vision_results,
            client_id=client_id,
            property_id=property_id,
            report_id=report_id,
        )

        # 5. Save to database
        from ..database import SessionLocal
        db = SessionLocal()
        try:
            report = Report(
                id=report_id,
                property_id=property_id,
                inspection_date=datetime.utcnow(),
                pdf_standard_url=result["pdf_standard_url"],
                pdf_hq_url=result["pdf_hq_url"],
                pdf_hq_expires_at=datetime.utcnow() + timedelta(days=90),
                json_url=result["json_url"],
                critical_count=result["report_data"]["summary"]["critical_count"],
                important_count=result["report_data"]["summary"]["important_count"],
            )
            db.add(report)

            for idx, thumb_url in enumerate(result["thumbnails"]):
                db.add(Asset(report_id=report_id, asset_type="thumbnail", filename=f"thumb_{idx}.jpg", url=thumb_url))

            db.commit()
        finally:
            db.close()

    except Exception as e:
        print(f"[admin] Error processing report: {e}")
    finally:
        try:
            base = os.path.dirname(zip_path)
            if os.path.isdir(base): shutil.rmtree(base, ignore_errors=True)
            if extract_dir and os.path.isdir(extract_dir): shutil.rmtree(extract_dir, ignore_errors=True)
        except Exception:
            pass
