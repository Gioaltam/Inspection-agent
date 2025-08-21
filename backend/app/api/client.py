# Client endpoints
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import requests

from ..database import get_db
from ..auth import get_current_user
from ..models import Client, Property, Report
from ..storage import StorageService
from ..config import settings

router = APIRouter()

# ---------- Dashboard (client-level) ----------
@router.get("/")
def get_client_dashboard(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = db.query(Client).filter(Client.user_id == getattr(current_user, "id", None)).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    props = db.query(Property).filter(Property.client_id == client.id).all()
    data = {
        "client": {
            "id": client.id,
            "company_name": client.company_name,
            "contact_name": client.contact_name,
        },
        "properties": [],
    }

    for p in props:
        latest = (
            db.query(Report)
            .filter(Report.property_id == p.id)
            .order_by(Report.created_at.desc())
            .first()
        )
        data["properties"].append({
            "id": p.id,
            "address": p.address,
            "property_type": p.property_type,
            "latest_report": None if not latest else {
                "id": latest.id,
                "inspection_date": latest.inspection_date.isoformat(),
                "critical_count": latest.critical_count,
                "important_count": latest.important_count,
            },
        })

    return data

# ---------- List reports for one property ----------
@router.get("/properties/{property_id}")
def get_property_reports(
    property_id: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = db.query(Client).filter(Client.user_id == getattr(current_user, "id", None)).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    prop = (
        db.query(Property)
        .filter(Property.id == property_id, Property.client_id == client.id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    reports = (
        db.query(Report)
        .filter(Report.property_id == property_id)
        .order_by(Report.created_at.desc())
        .all()
    )

    return {
        "property": {"id": prop.id, "address": prop.address, "property_type": prop.property_type},
        "reports": [
            {
                "id": r.id,
                "inspection_date": r.inspection_date.isoformat(),
                "critical_count": r.critical_count,
                "important_count": r.important_count,
                "pdf_standard_available": bool(r.pdf_standard_url),
                "pdf_hq_available": bool(r.pdf_hq_url and (r.pdf_hq_expires_at or datetime.min) > datetime.utcnow()),
                "created_at": r.created_at.isoformat(),
            }
            for r in reports
        ],
    }

# ---------- Detailed interactive report payload ----------
@router.get("/reports/{report_id}")
def get_report_details(
    report_id: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Fetch report + verify ownership via the property's client
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    prop = db.query(Property).filter(Property.id == report.property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found for report")

    client = db.query(Client).filter(Client.id == prop.client_id).first()
    if not client or client.user_id != getattr(current_user, "id", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this report")

    # Pull JSON describing the interactive report
    try:
        resp = requests.get(report.json_url, timeout=20)
        resp.raise_for_status()
        report_json = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch report JSON: {e}")

    # Build (pre)signed PDF links based on our storage prefix convention
    storage = StorageService(
        settings.S3_ACCESS_KEY,
        settings.S3_SECRET_KEY,
        settings.S3_BUCKET_NAME,
        settings.S3_ENDPOINT_URL,
    )
    prefix = f"clients/{client.id}/properties/{prop.id}/reports/{report.id}"

    pdf_urls = {
        "standard": storage.get_signed_url(f"{prefix}/report-standard.pdf"),
        "highquality": None,
    }
    if report.pdf_hq_url and (report.pdf_hq_expires_at or datetime.min) > datetime.utcnow():
        pdf_urls["highquality"] = storage.get_signed_url(f"{prefix}/report-highquality.pdf")

    return {
        "report": report_json,
        "pdf_urls": pdf_urls,
        "property": {
            "address": prop.address,
            "property_type": prop.property_type,
        },
    }
