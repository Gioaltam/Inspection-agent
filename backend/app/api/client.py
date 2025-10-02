# Client endpoints
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import requests
from pydantic import BaseModel, EmailStr
from typing import Optional

from ..database import get_db
from ..auth import get_current_user, get_password_hash, verify_password, create_access_token
from ..models import Client, Property, Report
from ..storage import StorageService
from ..config import settings

router = APIRouter()

# ---------- Schemas ----------
class OwnerRegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    owner_id: str
    password: str
    phone: Optional[str] = None

class OwnerLoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    owner_id: Optional[str] = None
    is_paid: bool = False

# ---------- Owner Registration & Login ----------
@router.post("/register-owner", response_model=AuthResponse)
def register_owner(request: OwnerRegisterRequest, db: Session = Depends(get_db)):
    """Register a new property owner with their own dashboard"""
    
    # Check if owner_id already exists
    existing = db.query(Client).filter(
        (Client.name == request.owner_id) | (Client.email == request.email)
    ).first()
    
    if existing:
        if existing.email == request.email:
            raise HTTPException(status_code=400, detail="Email already registered")
        else:
            raise HTTPException(status_code=400, detail="Owner ID already taken")
    
    # Create new client/owner
    client = Client(
        name=request.owner_id,  # Use owner_id as the unique identifier
        company_name=request.full_name,
        contact_name=request.full_name,
        email=request.email,
        phone=request.phone,
        portal_token=request.owner_id,  # Set portal token to owner_id for easy access
        password_hash=get_password_hash(request.password)
    )
    
    db.add(client)
    db.commit()
    db.refresh(client)
    
    # Create access token
    access_token = create_access_token(data={"sub": request.email, "owner_id": request.owner_id})

    return AuthResponse(
        access_token=access_token,
        owner_id=request.owner_id,
        is_paid=False  # New registrations are unpaid by default
    )

@router.post("/login-owner", response_model=AuthResponse)
def login_owner(request: OwnerLoginRequest, db: Session = Depends(get_db)):
    """Login for property owners"""
    
    # Find client by email
    client = db.query(Client).filter(Client.email == request.email).first()
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not hasattr(client, 'password_hash') or not client.password_hash:
        raise HTTPException(status_code=401, detail="Account not set up for login")
    
    if not verify_password(request.password, client.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Create access token
    owner_id = client.name if client.name else client.email.split('@')[0]
    access_token = create_access_token(data={"sub": client.email, "owner_id": owner_id})

    # Get paid status (default to False if not set)
    is_paid = getattr(client, 'is_paid', False)

    return AuthResponse(
        access_token=access_token,
        owner_id=owner_id,
        is_paid=is_paid
    )

# ---------- Get Paid Owners for Inspector GUI ----------
@router.get("/paid-owners")
def get_paid_owners(db: Session = Depends(get_db)):
    """Get list of PAID owners only - for inspector GUI to know where to send reports"""

    paid_owners = []

    # Get all paid clients from the database
    clients = db.query(Client).filter(Client.is_paid == True).all()

    for client in clients:
        # Get properties for this client
        properties = db.query(Property).filter(Property.client_id == client.id).all()
        property_list = []
        for prop in properties:
            property_list.append({
                "name": prop.label or prop.address,
                "address": prop.address
            })

        owner_data = {
            "owner_id": client.name or client.portal_token,  # Use name as owner_id
            "name": client.contact_name or client.company_name or client.name,
            "full_name": client.contact_name or client.company_name,
            "email": client.email,
            "is_paid": True,  # Only paid owners are returned
            "properties": property_list
        }
        paid_owners.append(owner_data)

    return {"owners": paid_owners, "message": "Only showing paid customers"}

# ---------- Payment Webhook (Stripe simulation) ----------
@router.post("/payment-webhook")
def handle_payment_webhook(request: dict, db: Session = Depends(get_db)):
    """
    Webhook endpoint to mark customer as paid when payment is received.
    In production, this would be called by Stripe/PayPal/etc.

    Expected payload:
    {
        "email": "customer@example.com",
        "payment_status": "completed",
        "amount": 49.00
    }
    """

    email = request.get("email")
    payment_status = request.get("payment_status")

    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    if payment_status != "completed":
        return {"message": "Payment not completed, no action taken"}

    # Find the client by email
    client = db.query(Client).filter(Client.email == email).first()

    if not client:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Mark as paid
    client.is_paid = True
    db.commit()

    # Log the payment
    print(f"✅ Payment received for {email} - Customer marked as PAID")

    return {
        "message": "Payment processed successfully",
        "customer": email,
        "status": "paid",
        "owner_id": client.name or client.portal_token
    }

# ---------- Get All Registered Owners ----------
@router.get("/owners")
def get_all_owners(db: Session = Depends(get_db)):
    """Get list of all registered owners for frontend selection"""
    
    owner_list = []
    
    # Always include Juliana's demo account
    owner_list.append({
        "owner_id": "DEMO1234",
        "name": "Juliana Shewmaker",
        "full_name": "Juliana Shewmaker",
        "email": "juliana@checkmyrental.com",
        "is_paid": True,
        "properties": [
            {"name": "Harborview 12B", "address": "4155 Key Thatch Dr, Tampa, FL"},
            {"name": "Seaside Cottage", "address": "308 Lookout Dr, Apollo Beach"},
            {"name": "Palm Grove 3C", "address": "Pinellas Park"}
        ]
    })
    
    # Try to add portal clients if they exist
    try:
        import json
        from ..portal_models import PortalClient
        
        portal_clients = db.query(PortalClient).all()
        for client in portal_clients:
            # Skip if already added (like Juliana)
            if client.email == "juliana@checkmyrental.com":
                continue
                
            # Parse properties if available
            properties = []
            if hasattr(client, 'properties_data') and client.properties_data:
                try:
                    properties = json.loads(client.properties_data)
                except:
                    properties = []
            
            owner_data = {
                "owner_id": f"portal_{client.id}",
                "name": client.full_name or client.email,
                "full_name": client.full_name or "",
                "email": client.email,
                "is_paid": getattr(client, 'is_paid', False),
                "properties": properties
            }
            owner_list.append(owner_data)
    except Exception as e:
        # Portal clients table might not exist or have issues
        print(f"Could not load portal clients: {e}")
    
    return {"owners": owner_list}

# ---------- Portal Dashboard (for simple token-based access) ----------
@router.get("/dashboard")
def get_portal_dashboard(portal_token: str, db: Session = Depends(get_db)):
    """Get dashboard data for a specific portal token (owner ID)"""
    print(f"Dashboard requested for token: {portal_token}")
    
    # Try to find a client with this owner ID (portal_token could be the owner name/ID)
    # First try exact match on portal_token field
    client = db.query(Client).filter(Client.portal_token == portal_token).first()
    
    # If not found, try to match by name (for owner IDs)
    if not client:
        client = db.query(Client).filter(Client.name == portal_token).first()
    
    if not client:
        # For now, return mock data for the demo token
        if portal_token == "DEMO1234":
            return {
                "owner": "Juliana Shewmaker",
                "properties": [
                    {
                        "address": "123 Demo Street, Miami, FL 33101",
                        "type": "single",
                        "label": "Demo Property",
                        "lastInspection": "2024-01-15",
                        "reportCount": 3,
                        "reports": [
                            {
                                "date": "2024-01-15",
                                "inspector": "John Smith",
                                "status": "completed",
                                "criticalIssues": 2,
                                "importantIssues": 5,
                                "id": "report1"
                            },
                            {
                                "date": "2023-11-20",
                                "inspector": "Mike Johnson",
                                "status": "completed",
                                "criticalIssues": 1,
                                "importantIssues": 3,
                                "id": "report2"
                            },
                            {
                                "date": "2023-09-10",
                                "inspector": "Sarah Williams",
                                "status": "completed",
                                "criticalIssues": 0,
                                "importantIssues": 2,
                                "id": "report3"
                            }
                        ]
                    }
                ]
            }
        else:
            raise HTTPException(status_code=404, detail="Property not found")
    
    # Get all properties for this client
    properties = db.query(Property).filter(Property.client_id == client.id).all()
    
    property_data = []
    for prop in properties:
        # Get all reports for this property
        reports = db.query(Report).filter(
            Report.property_id == prop.id
        ).order_by(Report.inspection_date.desc()).all()
        
        report_data = []
        for report in reports:
            report_data.append({
                "id": report.id,
                "date": report.inspection_date.isoformat() if report.inspection_date else report.created_at.isoformat(),
                "inspector": "Inspector",  # Could store this in report metadata
                "status": "completed",
                "criticalIssues": report.critical_count or 0,
                "importantIssues": report.important_count or 0,
                "hasPdf": bool(report.pdf_standard_url or report.pdf_path),
                "hasInteractiveView": bool(report.json_url or report.json_path)
            })
        
        last_inspection = reports[0] if reports else None
        property_data.append({
            "id": prop.id,
            "address": prop.address,
            "type": prop.property_type or "single",
            "label": prop.label or prop.address,
            "lastInspection": (last_inspection.inspection_date.isoformat() if last_inspection and last_inspection.inspection_date 
                             else last_inspection.created_at.isoformat() if last_inspection else None),
            "reportCount": len(reports),
            "reports": report_data
        })
    
    return {
        "owner": client.contact_name or client.name or client.company_name or "Property Owner",
        "properties": property_data
    }

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

# ---------- Portal report details (for token-based access) ----------
@router.get("/portal/report/{report_id}")
def get_portal_report_details(
    report_id: str,
    portal_token: str,
    db: Session = Depends(get_db),
):
    """Get detailed report data for portal access"""
    # Verify token and fetch report
    client = db.query(Client).filter(Client.portal_token == portal_token).first()
    if not client:
        raise HTTPException(status_code=404, detail="Invalid portal token")
    
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Verify the report belongs to this client's property
    prop = db.query(Property).filter(Property.id == report.property_id).first()
    if not prop or prop.client_id != client.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this report")
    
    # Try to get JSON data
    report_json = None
    if report.json_url:
        try:
            resp = requests.get(report.json_url, timeout=20)
            resp.raise_for_status()
            report_json = resp.json()
        except Exception as e:
            print(f"Failed to fetch report JSON from URL: {e}")
    elif report.json_path:
        # Try local file
        try:
            import json
            with open(report.json_path, 'r') as f:
                report_json = json.load(f)
        except Exception as e:
            print(f"Failed to read local JSON file: {e}")
    
    # Build PDF URLs
    pdf_urls = {}
    if report.pdf_standard_url:
        pdf_urls["standard"] = report.pdf_standard_url
    elif report.pdf_path:
        # For local files, we'll need to serve them through the API
        pdf_urls["standard"] = f"/api/portal/report/{report_id}/pdf?portal_token={portal_token}"
    
    if report.pdf_hq_url and (report.pdf_hq_expires_at or datetime.min) > datetime.utcnow():
        pdf_urls["highquality"] = report.pdf_hq_url
    
    return {
        "report": report_json or {"summary": report.summary or "No interactive data available"},
        "pdf_urls": pdf_urls,
        "property": {
            "address": prop.address,
            "property_type": prop.property_type,
            "label": prop.label or prop.address
        },
        "metadata": {
            "inspection_date": report.inspection_date.isoformat() if report.inspection_date else report.created_at.isoformat(),
            "critical_count": report.critical_count or 0,
            "important_count": report.important_count or 0
        }
    }

# ---------- PDF download for portal ----------
@router.get("/portal/report/{report_id}/pdf")
def download_portal_report_pdf(
    report_id: str,
    portal_token: str,
    db: Session = Depends(get_db),
):
    """Download PDF for portal access"""
    from fastapi.responses import FileResponse
    import os
    
    # Verify token and fetch report
    client = db.query(Client).filter(Client.portal_token == portal_token).first()
    if not client:
        raise HTTPException(status_code=404, detail="Invalid portal token")
    
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Verify the report belongs to this client's property
    prop = db.query(Property).filter(Property.id == report.property_id).first()
    if not prop or prop.client_id != client.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this report")
    
    # Check if we have a local PDF file
    if report.pdf_path and os.path.exists(report.pdf_path):
        return FileResponse(
            report.pdf_path,
            media_type="application/pdf",
            filename=f"inspection_report_{report_id}.pdf"
        )
    elif report.pdf_standard_url:
        # Redirect to external URL
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=report.pdf_standard_url)
    else:
        raise HTTPException(status_code=404, detail="PDF not available")

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
