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
app.include_router(client.router, prefix="/api/owners", tags=["Owner Management"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])
app.include_router(simple_report_router, prefix="/api/simple", tags=["Simple Reports"])
app.include_router(photos_router)  # Router has its own prefix and tags
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
    # Redirect to Next.js dashboard running on port 3000 with token parameter
    return RedirectResponse(url=f"http://localhost:3000?token={owner_id}", status_code=302)

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
            
            
            return {"owners": owners}
        finally:
            db.close()
    except Exception as e:
        print(f"Error fetching owners: {e}")
        # Return empty list as fallback
        return {"owners": []}

@app.get("/api/portal/owners/{owner_id}/galleries")
def get_owner_galleries(owner_id: str):
    """Get galleries/properties for a specific owner"""
    try:
        import json
        from sqlalchemy.orm import Session
        from .database import SessionLocal
        from .portal_models import PortalClient
        
        
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
    """Get dashboard data for a specific owner (portal_token is actually the owner_id)"""
    owner_id = portal_token  # portal_token parameter name kept for compatibility, but it's really owner_id
    print(f"Dashboard requested for owner_id: {owner_id}")

    # Handle real client IDs (e.g., "client_2" for Juliana)
    if owner_id.startswith("client_"):
        try:
            from sqlalchemy.orm import Session
            from .database import SessionLocal
            from .portal_models import PortalClient
            import json

            client_id = int(owner_id.replace("client_", ""))
            db = SessionLocal()
            try:
                client = db.query(PortalClient).filter(PortalClient.id == client_id).first()
                if client:
                    # Parse properties from the client data
                    properties = []
                    if client.properties_data:
                        try:
                            props = json.loads(client.properties_data)
                            for prop in props:
                                properties.append({
                                    "id": prop.get("name", "").replace(" ", "_").lower(),
                                    "address": prop.get("address", ""),
                                    "type": "single",
                                    "label": prop.get("name", ""),
                                    "lastInspection": "2024-08-20",
                                    "reportCount": 0,
                                    "criticalIssues": 0,
                                    "importantIssues": 0,
                                    "reports": []
                                })
                        except:
                            pass

                    return {
                        "owner": client.full_name or client.email,
                        "email": client.email,
                        "client_id": f"client_{client.id}",
                        "properties": properties
                    }
            finally:
                db.close()
        except Exception as e:
            print(f"Error fetching client data: {e}")

    # If no client found, return error
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Owner not found")

