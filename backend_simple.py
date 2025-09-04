"""
Simple Backend API for Testing
Handles report uploads without complex authentication
"""

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
import secrets

app = FastAPI(title="Inspection Backend Simple", version="1.0.0")

# Enable CORS for all origins during testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage directory
STORAGE_DIR = Path("workspace/gallery_storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Simple in-memory database for testing
reports_db = {}
properties_db = {}
clients_db = {}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "inspection-backend"}

@app.post("/api/admin/upload-report")
async def upload_report(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    property_id: str = Form(...),
    employee_id: str = Form(None)
):
    """
    Simple report upload endpoint for testing
    """
    try:
        # Generate report ID
        report_id = secrets.token_hex(16)
        
        # Create storage directory for this report
        report_dir = STORAGE_DIR / client_id / property_id / report_id
        report_dir.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded file
        file_path = report_dir / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Extract if it's a ZIP
        if file.filename.lower().endswith('.zip'):
            extract_dir = report_dir / "extracted"
            shutil.unpack_archive(file_path, extract_dir)
        
        # Store in simple database
        reports_db[report_id] = {
            "report_id": report_id,
            "client_id": client_id,
            "property_id": property_id,
            "employee_id": employee_id or "system",
            "filename": file.filename,
            "created_at": datetime.now().isoformat(),
            "status": "completed"
        }
        
        # Save to JSON file for persistence
        db_file = STORAGE_DIR / "reports_db.json"
        with open(db_file, "w") as f:
            json.dump(reports_db, f, indent=2)
        
        print(f"✓ Report uploaded: {report_id}")
        print(f"  Client: {client_id}")
        print(f"  Property: {property_id}")
        print(f"  File: {file.filename}")
        
        return JSONResponse({
            "message": "Report upload successful",
            "report_id": report_id,
            "status": "completed",
            "gallery_url": f"http://localhost:8005/?token=test"
        })
        
    except Exception as e:
        print(f"✗ Upload error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/api/portal/generate-token")
async def generate_token(request_body: dict = None):
    """
    Generate access token for client
    """
    # Handle both JSON body and form data
    client_id = None
    if request_body:
        client_id = request_body.get("client_id", "default")
    
    token = secrets.token_urlsafe(32)
    return {"token": token, "client_id": client_id or "default"}

@app.get("/api/admin/property-lookup")
async def property_lookup(address: str):
    """
    Look up property by address (returns test data for now)
    """
    # Generate consistent IDs based on address
    import hashlib
    addr_hash = hashlib.md5(address.encode()).hexdigest()[:8]
    
    return {
        "client_id": f"client_{addr_hash}",
        "property_id": f"prop_{addr_hash}",
        "address": address
    }

@app.post("/api/admin/create-client-property")
async def create_client_property(request_body: dict):
    """
    Create new client and property
    """
    client_name = request_body.get("client_name", "Unknown")
    property_address = request_body.get("property_address", "Unknown")
    
    import hashlib
    client_id = f"client_{hashlib.md5(client_name.encode()).hexdigest()[:8]}"
    property_id = f"prop_{hashlib.md5(property_address.encode()).hexdigest()[:8]}"
    
    clients_db[client_id] = {"name": client_name, "id": client_id}
    properties_db[property_id] = {
        "id": property_id,
        "address": property_address,
        "client_id": client_id
    }
    
    return {
        "client_id": client_id,
        "property_id": property_id
    }

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("SIMPLE BACKEND API RUNNING")
    print("="*60)
    print("\nEndpoints available:")
    print("  - POST /api/admin/upload-report")
    print("  - GET  /api/admin/property-lookup")
    print("  - POST /api/portal/generate-token")
    print("  - GET  /health")
    print("\nListening on: http://localhost:8000")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)