# FastAPI entrypoint
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import engine
from .models import Base
from .api import admin, client
from .api.portal_accounts import router as portal_router
from .api.reports import router as reports_router
from .api.simple_report import router as simple_report_router
from .api.photos import router as photos_router
from .api.photo_report import router as photo_report_router
from .config import settings

# Create tables on startup (SQLite/Postgres compatible)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inspection Portal API", version="0.1.0")

# CORS configuration based on environment
allowed_origins = ["*"] if settings.ENVIRONMENT == "development" else [
    "http://localhost:3000",
    "http://localhost:8000",
    # Add your production domains here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Custom exception handlers to ensure JSON responses for API errors
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Only return JSON for API routes
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    # For non-API routes, let default handler take over
    raise exc

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# API routes
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(portal_router, prefix="/api/portal", tags=["portal"])
app.include_router(client.router, prefix="/api/portal", tags=["Client Portal"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])
app.include_router(simple_report_router, prefix="/api/simple", tags=["Simple Reports"])
app.include_router(photos_router, prefix="/api/photos", tags=["Photos"])
app.include_router(photo_report_router, prefix="/api/photo-report", tags=["Photo Reports"])

# Serve static frontend (landing + owner dashboard)
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    print(f"Warning: Static directory not found at {static_dir}")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def landing():
    index = static_dir / "landing.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Static landing not found", "static_dir": str(static_dir)}

@app.get("/payment")
def payment_page():
    payment = static_dir / "payment.html"
    if payment.exists():
        return FileResponse(str(payment))
    return {"message": "Payment page not found"}

@app.get("/owner/{owner_id}")
def owner_dashboard(owner_id: str):
    """Redirect to Next.js dashboard for specific owner ID"""
    from fastapi.responses import RedirectResponse
    # Redirect to Next.js dashboard running on port 3000
    return RedirectResponse(url=f"http://localhost:3000?owner_id={owner_id}", status_code=302)

# Temporary dashboard endpoint for demo portal
@app.get("/api/portal/owners")
def get_all_owners():
    """Get all registered clients for the employee GUI"""
    try:
        import json
        from sqlalchemy.orm import Session
        from .database import SessionLocal
        from .portal_models import PortalClient
        
        db = SessionLocal()
        try:
            # Get all clients from database
            clients = db.query(PortalClient).all()
            
            owners = []
            for client in clients:
                # Parse properties if available
                properties = []
                if client.properties_data:
                    try:
                        properties = json.loads(client.properties_data)
                    except:
                        properties = []
                
                owner_data = {
                    "owner_id": f"client_{client.id}",
                    "name": client.full_name or client.email,
                    "email": client.email,
                    "is_paid": client.is_paid,
                    "properties": properties,
                    "created_at": client.created_at.isoformat() if client.created_at else None
                }
                owners.append(owner_data)
            
            # Always include demo account if not in database
            if not any(o["email"] == "juliana@checkmyrental.com" for o in owners):
                owners.insert(0, {
                    "owner_id": "DEMO1234",
                    "name": "Juliana Shewmaker (Demo)",
                    "email": "juliana@checkmyrental.com",
                    "is_paid": True,
                    "properties": [
                        {"name": "Harborview 12B", "address": "4155 Key Thatch Dr, Tampa, FL"},
                        {"name": "Seaside Cottage", "address": "308 Lookout Dr, Apollo Beach"},
                        {"name": "Palm Grove 3C", "address": "Pinellas Park"}
                    ]
                })
            
            return {"owners": owners}
        finally:
            db.close()
    except Exception as e:
        print(f"Error fetching owners: {e}")
        # Return demo data as fallback
        return {
            "owners": [
                {
                    "owner_id": "DEMO1234",
                    "name": "Juliana Shewmaker (Demo)",
                    "email": "juliana@checkmyrental.com",
                    "is_paid": True,
                    "properties": []
                }
            ]
        }

@app.get("/api/portal/owners/{owner_id}/galleries")
def get_owner_galleries(owner_id: str):
    """Get galleries/properties for a specific owner"""
    try:
        import json
        from sqlalchemy.orm import Session
        from .database import SessionLocal
        from .portal_models import PortalClient
        
        # Handle demo account
        if owner_id == "DEMO1234":
            return {
                "galleries": [
                    {"name": "Harborview 12B", "gallery_name": "Harborview 12B - 4155 Key Thatch Dr"},
                    {"name": "Seaside Cottage", "gallery_name": "Seaside Cottage - Apollo Beach"},
                    {"name": "Palm Grove 3C", "gallery_name": "Palm Grove 3C - Pinellas Park"}
                ]
            }
        
        # Extract client ID from owner_id (format: "client_123")
        if owner_id.startswith("client_"):
            client_id = int(owner_id.replace("client_", ""))
            
            db = SessionLocal()
            try:
                client = db.query(PortalClient).filter(PortalClient.id == client_id).first()
                if client and client.properties_data:
                    properties = json.loads(client.properties_data)
                    galleries = []
                    for prop in properties:
                        galleries.append({
                            "name": prop.get("name", ""),
                            "gallery_name": f"{prop.get('name', '')} - {prop.get('address', '')}"
                        })
                    return {"galleries": galleries}
            finally:
                db.close()
        
        return {"galleries": []}
    except Exception as e:
        print(f"Error fetching galleries: {e}")
        return {"galleries": []}

@app.get("/api/portal/dashboard")
def get_portal_dashboard(portal_token: str):
    """Get dashboard data for a specific portal token (property)"""
    print(f"Dashboard requested for token: {portal_token}")
    
    # For now, just return hardcoded data for DEMO1234
    if portal_token == "DEMO1234":
        return {
            "owner": "Juliana Shewmaker", 
            "properties": [
                {
                    "id": "prop1",
                    "address": "4155 Key Thatch Dr, Tampa, FL 33101",
                    "type": "single",
                    "label": "Harborview 12B",
                    "lastInspection": "2024-01-15",
                    "reportCount": 3,
                    "criticalIssues": 2,
                    "importantIssues": 5,
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
                },
                {
                    "id": "prop2",
                    "address": "308 Lookout Dr, Apollo Beach, FL 33572",
                    "type": "single",
                    "label": "Seaside Cottage",
                    "lastInspection": "2024-08-20",
                    "reportCount": 2,
                    "criticalIssues": 0,
                    "importantIssues": 1,
                    "reports": []
                },
                {
                    "id": "prop3",
                    "address": "5823 Palmetto Way, Pinellas Park, FL 33782",
                    "type": "condo",
                    "label": "Palm Grove 3C",
                    "lastInspection": "2024-07-11",
                    "reportCount": 4,
                    "criticalIssues": 1,
                    "importantIssues": 3,
                    "reports": []
                }
            ]
        }
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Property not found")

