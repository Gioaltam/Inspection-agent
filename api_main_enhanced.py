"""
Enhanced API with magic link authentication, pagination, and search.
This is an extended version of api_main.py with the polish features.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import json
import secrets
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Query, Header, Request, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

# Import database and models
from backend.app.database import SessionLocal, engine
from backend.app.models import Report, Client, Property, Base, User

# Import authentication utilities
from auth_utils import (
    SignedURLGenerator, MagicLinkAuth, EmailService, 
    PaginationParams, SECRET_KEY
)

# Define paths for static files
ROOT = Path(__file__).resolve().parent  # Current directory where api_main_enhanced.py is
WEB = ROOT / "frontend_web"  # Path to frontend_web folder

# In-memory storage for magic links (use Redis in production)
MAGIC_LINK_STORAGE: Dict[str, Dict[str, Any]] = {}
SESSION_STORAGE: Dict[str, Dict[str, Any]] = {}

app = FastAPI(
    title="Inspection Portal API (Enhanced)", 
    version="2.0.0",
    description="Enhanced API with magic links, pagination, and search"
)

# Add CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database when the API starts"""
    Base.metadata.create_all(bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _get_or_create_property(db: Session, owner: Client, address: str, label: str | None = None) -> Property:
    prop = db.query(Property).filter(
        Property.client_id == owner.id,
        Property.address == address
    ).first()
    if prop:
        return prop
    prop = Property(
        id=str(uuid4()),
        client_id=owner.id,
        address=address
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


# ==================== Authentication Models ====================

class LoginRequest(BaseModel):
    email: EmailStr

class LoginResponse(BaseModel):
    message: str
    email: str

class VerifyTokenRequest(BaseModel):
    token: str

class VerifyTokenResponse(BaseModel):
    session_token: str
    owner: dict
    expires_at: datetime


# ==================== Magic Link Authentication ====================

@app.post("/auth/login", response_model=LoginResponse)
def request_magic_link(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Request a magic link login for the given email.
    Sends an email with a time-limited login link.
    """
    # Find owner by email
    owner = db.query(Client).filter(Client.email == request.email).first()
    
    if not owner:
        # Don't reveal whether email exists
        return LoginResponse(
            message="If your email is registered, you will receive a login link.",
            email=request.email
        )
    
    # Generate magic link
    magic_token, magic_link = MagicLinkAuth.generate_magic_link(
        email=owner.email,
        owner_id=owner.id
    )
    
    # Store magic link data (in production, use Redis with TTL)
    MAGIC_LINK_STORAGE[magic_token] = {
        "email": owner.email,
        "owner_id": owner.id,
        "expires": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
        "token": magic_token
    }
    
    # Send email
    EmailService.send_magic_link_email(
        to_email=owner.email,
        name=owner.name,
        magic_link=magic_link
    )
    
    return LoginResponse(
        message="Login link sent to your email. Please check your inbox.",
        email=request.email
    )


@app.post("/auth/verify", response_model=VerifyTokenResponse)
def verify_magic_link(
    request: VerifyTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Verify a magic link token and create a session.
    Returns a session token for subsequent API calls.
    """
    # Check if token exists
    token_data = MAGIC_LINK_STORAGE.get(request.token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Validate token
    if not MagicLinkAuth.validate_magic_token(request.token, token_data):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get owner
    owner = db.query(Client).filter(Client.id == token_data["owner_id"]).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Create session token
    session_token = secrets.token_urlsafe(32)
    session_expires = datetime.utcnow() + timedelta(hours=24)
    
    # Store session (in production, use Redis with TTL)
    SESSION_STORAGE[session_token] = {
        "owner_id": owner.id,
        "email": owner.email,
        "expires": session_expires.isoformat()
    }
    
    # Remove used magic link token
    del MAGIC_LINK_STORAGE[request.token]
    
    return VerifyTokenResponse(
        session_token=session_token,
        owner={
            "id": owner.id,
            "name": owner.name,
            "email": owner.email
        },
        expires_at=session_expires
    )


@app.post("/auth/logout")
def logout(session_token: str = Header(None, alias="X-Session-Token")):
    """Logout and invalidate session token."""
    if session_token and session_token in SESSION_STORAGE:
        del SESSION_STORAGE[session_token]
        return {"message": "Logged out successfully"}
    return {"message": "No active session"}


# ==================== Enhanced Authentication Dependency ====================

def get_current_owner(
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    token: Optional[str] = Query(None, description="Legacy portal token"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Client:
    """
    Enhanced authentication supporting both session tokens and legacy portal tokens.
    """
    # Try session token first (from magic link login)
    if session_token:
        session_data = SESSION_STORAGE.get(session_token)
        if session_data:
            # Check expiry
            expires = datetime.fromisoformat(session_data["expires"])
            if datetime.utcnow() < expires:
                owner = db.query(Client).filter(Client.id == session_data["owner_id"]).first()
                if owner:
                    return owner
    
    # Fall back to legacy portal token
    portal_token = token
    if not portal_token and authorization:
        if authorization.startswith("Bearer "):
            portal_token = authorization[7:]
    
    if portal_token:
        owner = db.query(Client).filter(Client.portal_token == portal_token).first()
        if owner:
            return owner
    
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Please log in or provide a valid token."
    )


# ==================== Enhanced Portal Endpoints with Pagination & Search ====================

class PaginatedResponse(BaseModel):
    data: List[Any]
    pagination: dict


@app.get("/api/v2/portal/dashboard")
def enhanced_portal_dashboard(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search properties by address or label"),
    owner: Client = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    """
    Enhanced dashboard with pagination and search.
    """
    # Base query for properties
    query = db.query(Property).filter(Property.client_id == owner.id)
    
    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Property.label.ilike(search_term),
                Property.address.ilike(search_term)
            )
        )
    
    # Get total count before pagination
    total_count = query.count()
    
    # Apply pagination
    pagination = PaginationParams(page, page_size)
    properties = pagination.paginate_query(query).all()
    
    # Calculate totals
    total_reports = 0
    total_critical = 0
    total_important = 0
    
    property_summaries = []
    for prop in properties:
        reports = db.query(Report).filter(Report.property_id == prop.id).all()
        report_count = len(reports)
        latest_report = max((r.created_at for r in reports), default=None)
        
        prop_critical = sum(r.critical_count or 0 for r in reports)
        prop_important = sum(r.important_count or 0 for r in reports)
        
        total_reports += report_count
        total_critical += prop_critical
        total_important += prop_important
        
        property_summaries.append({
            "id": prop.id,
            "label": prop.label,
            "address": prop.address,
            "report_count": report_count,
            "latest_report_at": latest_report.isoformat() if latest_report else None,
            "critical_issues": prop_critical,
            "important_issues": prop_important
        })
    
    return {
        "owner": {
            "id": owner.id,
            "name": owner.name,
            "email": owner.email
        },
        "totals": {
            "properties": total_count,
            "reports": total_reports,
            "critical": total_critical,
            "important": total_important
        },
        "properties": property_summaries,
        "pagination": pagination.get_pagination_metadata(total_count)
    }


@app.get("/api/v2/portal/reports")
def list_all_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    property_id: Optional[str] = Query(None, description="Filter by property"),
    search: Optional[str] = Query(None, description="Search by address"),
    critical_only: bool = Query(False, description="Show only reports with critical issues"),
    sort_by: str = Query("created_at", description="Sort field: created_at, critical_count, important_count"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    owner: Client = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    """
    List all reports across all properties with advanced filtering.
    """
    # Base query - join with Property to ensure ownership
    query = db.query(Report).join(Property).filter(Property.client_id == owner.id)
    
    # Apply filters
    if property_id:
        query = query.filter(Report.property_id == property_id)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(Report.address.ilike(search_term))
    
    if critical_only:
        query = query.filter(Report.critical_count > 0)
    
    # Apply sorting
    sort_column = {
        "created_at": Report.created_at,
        "critical_count": Report.critical_count,
        "important_count": Report.important_count
    }.get(sort_by, Report.created_at)
    
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())
    
    # Get total count
    total_count = query.count()
    
    # Apply pagination
    pagination = PaginationParams(page, page_size)
    reports = pagination.paginate_query(query).all()
    
    # Build response with signed URLs
    report_list = []
    for report in reports:
        # Generate signed URLs for PDF and JSON
        pdf_signed_url = SignedURLGenerator.generate_signed_url(
            f"reports/{report.id}/pdf",
            expiry_hours=24
        )
        json_signed_url = SignedURLGenerator.generate_signed_url(
            f"reports/{report.id}/json",
            expiry_hours=24
        )
        
        report_list.append({
            "id": report.id,
            "property_id": report.property_id,
            "address": report.address,
            "created_at": report.created_at.isoformat(),
            "photo_count": len(report.photos) if report.photos else 0,
            "critical_count": report.critical_count or 0,
            "important_count": report.important_count or 0,
            "pdf_url": pdf_signed_url,
            "json_url": json_signed_url
        })
    
    return {
        "reports": report_list,
        "pagination": pagination.get_pagination_metadata(total_count)
    }


@app.get("/api/v2/portal/search")
def global_search(
    q: str = Query(..., min_length=2, description="Search query"),
    owner: Client = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    """
    Global search across properties and reports.
    """
    search_term = f"%{q}%"
    
    # Search properties
    properties = db.query(Property).filter(
        and_(
            Property.client_id == owner.id,
            or_(
                Property.label.ilike(search_term),
                Property.address.ilike(search_term)
            )
        )
    ).limit(10).all()
    
    # Search reports
    reports = db.query(Report).join(Property).filter(
        and_(
            Property.client_id == owner.id,
            Report.address.ilike(search_term)
        )
    ).limit(10).all()
    
    return {
        "query": q,
        "results": {
            "properties": [
                {
                    "id": p.id,
                    "label": p.label,
                    "address": p.address,
                    "type": "property"
                }
                for p in properties
            ],
            "reports": [
                {
                    "id": r.id,
                    "address": r.address,
                    "created_at": r.created_at.isoformat(),
                    "type": "report"
                }
                for r in reports
            ]
        },
        "total_results": len(properties) + len(reports)
    }


# ==================== Signed URL Validation Endpoint ====================

@app.get("/api/portal/signed/{resource_type}/{resource_id}/{file_type}")
def serve_signed_resource(
    resource_type: str,
    resource_id: str,
    file_type: str,
    expires: int = Query(...),
    signature: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Serve resources with signed URL validation.
    This endpoint validates signed URLs and serves the requested resource.
    """
    # Validate signature
    resource_path = f"{resource_type}/{resource_id}/{file_type}"
    if not SignedURLGenerator.validate_signed_url(resource_path, str(expires), signature):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")
    
    # Handle different resource types
    if resource_type == "reports":
        # Verify report exists (no ownership check since URL is signed)
        report = db.query(Report).filter(Report.id == resource_id).first()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        if file_type == "pdf":
            pdf_path = Path(report.pdf_path) if report.pdf_path else None
            if not pdf_path or not pdf_path.exists():
                raise HTTPException(status_code=404, detail="PDF not found")
            return FileResponse(str(pdf_path), media_type="application/pdf")
        
        elif file_type == "json":
            json_path = Path(report.json_path) if report.json_path else None
            if not json_path or not json_path.exists():
                raise HTTPException(status_code=404, detail="JSON not found")
            with open(json_path, 'r') as f:
                return JSONResponse(content=json.load(f))
    
    raise HTTPException(status_code=404, detail="Resource not found")


# ==================== Analytics Endpoint ====================

@app.get("/api/v2/portal/analytics")
def get_analytics(
    owner: Client = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    """
    Get analytics and statistics for the owner's properties.
    """
    # Get all properties
    properties = db.query(Property).filter(Property.client_id == owner.id).all()
    
    # Aggregate statistics
    stats = {
        "total_properties": len(properties),
        "total_reports": 0,
        "total_critical_issues": 0,
        "total_important_issues": 0,
        "reports_by_month": defaultdict(int),
        "issues_by_property": [],
        "recent_activity": []
    }
    
    for prop in properties:
        reports = db.query(Report).filter(Report.property_id == prop.id).all()
        
        prop_stats = {
            "property_id": prop.id,
            "property_label": prop.label,
            "property_address": prop.address,
            "report_count": len(reports),
            "critical_issues": sum(r.critical_count or 0 for r in reports),
            "important_issues": sum(r.important_count or 0 for r in reports)
        }
        
        stats["issues_by_property"].append(prop_stats)
        stats["total_reports"] += len(reports)
        stats["total_critical_issues"] += prop_stats["critical_issues"]
        stats["total_important_issues"] += prop_stats["important_issues"]
        
        # Group reports by month
        for report in reports:
            month_key = report.created_at.strftime("%Y-%m")
            stats["reports_by_month"][month_key] += 1
    
    # Get recent activity (last 10 reports)
    recent_reports = db.query(Report).join(Property).filter(
        Property.client_id == owner.id
    ).order_by(Report.created_at.desc()).limit(10).all()
    
    stats["recent_activity"] = [
        {
            "report_id": r.id,
            "address": r.address,
            "created_at": r.created_at.isoformat(),
            "critical": r.critical_count or 0,
            "important": r.important_count or 0
        }
        for r in recent_reports
    ]
    
    # Convert defaultdict to regular dict for JSON serialization
    stats["reports_by_month"] = dict(stats["reports_by_month"])
    
    return stats


# ==================== Ingest Endpoint ====================

@app.post("/api/ingest")
async def ingest_report(
    pdf: UploadFile = File(..., description="Generated inspection PDF"),
    json_report: UploadFile | None = File(None, description="Optional JSON summary from run_report.py"),
    property_address: str = Form(..., description="Property address to attach this report to"),
    client_name: str | None = Form(None),
    background: BackgroundTasks = None,
    owner: Client = Depends(get_current_owner),  # uses token or session
    db: Session = Depends(get_db)
):
    """
    Simple ingestion endpoint for the desktop frontend's 'Send to Portal' action.
    - Auth: token query or Authorization header (handled by get_current_owner)
    - Saves uploaded PDF/JSON to disk
    - Upserts Property by address
    - Creates Report row and returns signed URLs
    """

    # ---- 1) Save files to disk ------------------------------------------------
    base_dir = Path("output") / "portal_uploads" / datetime.utcnow().strftime("%Y%m%d")
    base_dir.mkdir(parents=True, exist_ok=True)

    # Normalize filenames
    report_id = str(uuid4())
    pdf_name = f"{report_id}.pdf"
    json_name = f"{report_id}.json"

    # Save PDF
    pdf_path = base_dir / pdf_name
    with open(pdf_path, "wb") as f:
        f.write(await pdf.read())

    # Save JSON if provided and parse counts/address fallback
    counts = {"critical": 0, "important": 0, "photos": 0}
    if json_report is not None:
        json_path = base_dir / json_name
        with open(json_path, "wb") as f:
            f.write(await json_report.read())
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            counts["critical"] = int(data.get("totals", {}).get("critical_issues", 0))
            counts["important"] = int(data.get("totals", {}).get("important_issues", 0))
            counts["photos"] = int(data.get("totals", {}).get("photos", 0))
            # If caller forgot to pass property_address, pull it from JSON
            if not property_address and data.get("address"):
                property_address = data["address"]
        except Exception:
            json_path = None
    else:
        json_path = None

    if not property_address:
        raise HTTPException(status_code=400, detail="property_address is required")

    # ---- 2) Upsert Property and insert Report ---------------------------------
    prop = _get_or_create_property(db, owner, property_address, label=client_name)

    report = Report(
        id=report_id,
        property_id=prop.id,
        address=property_address,
        created_at=datetime.utcnow(),
        pdf_path=str(pdf_path),
        json_path=str(json_path) if json_path else None,
        critical_count=counts["critical"],
        important_count=counts["important"]
    )
    db.add(report)
    db.commit()

    # ---- 3) Build signed URLs for return payload ------------------------------
    pdf_url = SignedURLGenerator.generate_signed_url(f"reports/{report.id}/pdf", expiry_hours=24)
    json_url = (
        SignedURLGenerator.generate_signed_url(f"reports/{report.id}/json", expiry_hours=24)
        if json_path else None
    )

    return {
        "message": "Report uploaded",
        "report": {
            "id": report.id,
            "property_id": prop.id,
            "address": report.address,
            "created_at": report.created_at.isoformat(),
            "photo_count": counts["photos"],
            "critical_count": counts["critical"],
            "important_count": counts["important"],
            "pdf_url": pdf_url,
            "json_url": json_url,
        }
    }


# ==================== Keep existing health check ====================

@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "version": "2.0.0", "features": ["magic_links", "pagination", "search", "signed_urls"]}


# === DEV viewer for local testing of /reports/{id} ===
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pathlib import Path
import json

def _find_report_record(report_id: str):
    idx_path = Path("output") / "reports_index.json"
    if not idx_path.exists():
        return None
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        for rec in data.get("reports", []):
            if rec.get("report_id") == report_id:
                return rec
    except Exception:
        pass
    return None

# Portal viewer route
@app.get("/portal/{client_id}/{property_id}/{report_id}", response_class=HTMLResponse)
async def portal_viewer(client_id: str, property_id: str, report_id: str):
    portal_path = Path("frontend_web") / "portal.html"
    if not portal_path.exists():
        raise HTTPException(status_code=404, detail="Portal viewer not found")
    return HTMLResponse(content=portal_path.read_text())

# API endpoint for report index.json
@app.get("/api/report/{client_id}/{property_id}/{report_id}/index.json")
async def get_report_index(client_id: str, property_id: str, report_id: str):
    json_path = Path("output") / f"{report_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rec = _find_report_record(report_id) or {}
    
    # Build index response
    index_data = {
        "reportId": report_id,
        "clientId": client_id,
        "propertyId": property_id,
        "address": rec.get("address", data.get("address", "Property Report")),
        "generated_at": rec.get("generated_at", data.get("generated_at", "")),
        "pdf": {
            "presignedUrl": f"/api/report/{client_id}/{property_id}/{report_id}/report.pdf"
        },
        "interactive": {
            "basePath": f"/reports/{report_id}"
        }
    }
    return JSONResponse(content=index_data)

# API endpoint for report PDF
@app.get("/api/report/{client_id}/{property_id}/{report_id}/report.pdf")
async def get_report_pdf_api(client_id: str, property_id: str, report_id: str):
    rec = _find_report_record(report_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    pdf_path = rec.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=Path(pdf_path).name)

# API endpoint for interactive report
@app.get("/api/report/{client_id}/{property_id}/{report_id}/interactive/index.html", response_class=HTMLResponse)
async def get_interactive_report(client_id: str, property_id: str, report_id: str):
    # Redirect to the existing reports viewer
    return HTMLResponse(content=f"""
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url=/reports/{report_id}">
    </head>
    <body>
        <p>Redirecting to interactive report...</p>
    </body>
    </html>
    """)

@app.get("/reports/{report_id}", response_class=HTMLResponse)
def view_report(report_id: str):
    json_path = Path("output") / f"{report_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Not Found")

    rec = _find_report_record(report_id) or {}
    pdf_path = rec.get("pdf_path")
    addr = rec.get("address", "Property Inspection Report")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    totals = data.get("totals", {})
    photos = data.get("photos", [])

    items = []
    for p in photos:
        flags = p.get("flags", {})
        badge = []
        if flags.get("critical"): badge.append("CRITICAL")
        if flags.get("important"): badge.append("IMPORTANT")
        items.append(f"<li><strong>{p.get('file_name')}</strong>" + ((" — " + ", ".join(badge)) if badge else "") + "</li>")

    pdf_link = f"/reports/{report_id}/pdf" if pdf_path else "#"
    json_link = f"/reports/{report_id}/json"

    html = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>{addr}</title>
      <style>
        body {{ font-family: system-ui, Segoe UI, Arial; max-width: 960px; margin: 24px auto; padding: 0 16px; }}
        header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }}
        a.button {{ display:inline-block; padding:8px 12px; border-radius:8px; text-decoration:none; border:1px solid #ddd; }}
      </style>
    </head>
    <body>
      <header>
        <h2>{addr}</h2>
        <div>
          <a class="button" href="{pdf_link}">Download PDF</a>
          <a class="button" href="{json_link}">View JSON</a>
        </div>
      </header>

      <p><strong>Total photos:</strong> {totals.get('photos', 0)}
         &nbsp;&nbsp; <strong>Critical:</strong> {totals.get('critical_issues', 0)}
         &nbsp;&nbsp; <strong>Important:</strong> {totals.get('important_issues', 0)}</p>

      <h3>Photos</h3>
      <ul>
        {''.join(items)}
      </ul>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/reports/{report_id}/json")
def get_report_json(report_id: str):
    json_path = Path("output") / f"{report_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Not Found")
    return JSONResponse(content=json.loads(json_path.read_text(encoding="utf-8")))

@app.get("/reports/{report_id}/pdf")
def get_report_pdf(report_id: str):
    rec = _find_report_record(report_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Not Found")
    pdf_path = rec.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=Path(pdf_path).name)


# ==================== Portal Routes ====================

@app.get("/portal/{client_id}/{property_id}/{report_id}")
def portal_page(client_id: str, property_id: str, report_id: str):
    """Serve the portal HTML page for viewing reports"""
    portal_html = WEB / "portal.html"
    if not portal_html.exists():
        # Fallback to report-viewer.html if portal.html doesn't exist
        portal_html = WEB / "report-viewer.html"
    if not portal_html.exists():
        raise HTTPException(status_code=404, detail="Portal page not found")
    return FileResponse(portal_html)

# Mount static files for serving report artifacts (PDFs, JSONs, images)
# This allows access to files in the output directory via /static/...
app.mount("/static", StaticFiles(directory=ROOT / "output"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)