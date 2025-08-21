# FastAPI entrypoint
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import engine
from .models import Base
from .api import admin, client
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

# API routes
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(client.router, prefix="/api/portal", tags=["Client Portal"])

# Serve the interactive report viewer (static HTML)
# Use absolute path resolution for reliability
frontend_dir = Path(__file__).parent.parent.parent / "frontend_web"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {frontend_dir}")

@app.get("/health")
def health():
    return {"status": "ok"}
