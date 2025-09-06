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

@app.get("/owner/{owner_id}")
def owner_dashboard(owner_id: str):
    """Serve owner dashboard for specific owner ID"""
    dashboard = static_dir / "owner-dashboard.html"
    if dashboard.exists():
        return FileResponse(str(dashboard))
    return {"message": "Owner dashboard not found", "owner_id": owner_id}

# Temporary dashboard endpoint for demo portal
@app.get("/api/portal/dashboard")
def get_portal_dashboard(portal_token: str):
    """Get dashboard data for a specific portal token (property)"""
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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Property not found")
