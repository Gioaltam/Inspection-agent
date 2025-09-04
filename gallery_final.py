"""
Gallery Server using multi-property-gallery.html
"""

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from pathlib import Path
from datetime import datetime

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
STORAGE_DIR = Path("workspace/gallery_storage")
OUTPUTS_DIR = Path("workspace/outputs")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_gallery():
    """
    Serve the multi-property gallery HTML
    """
    return FileResponse("static/multi-property-gallery.html")

@app.get("/gallery")
async def serve_photo_gallery():
    """
    Serve the photo gallery viewer
    """
    return FileResponse("static/photo-gallery.html")

@app.get("/api/portal")
async def get_portal_data(token: str = Query(None)):
    """
    Get dashboard data for the multi-property gallery
    """
    # Collect all reports
    properties = []
    
    # Check outputs directory for all reports
    if OUTPUTS_DIR.exists():
        property_map = {}
        
        for report_dir in OUTPUTS_DIR.iterdir():
            if report_dir.is_dir():
                # Try to load report data
                json_file = report_dir / "report_data.json"
                if not json_file.exists():
                    json_file = report_dir / "web" / "report.json"
                
                if json_file.exists():
                    try:
                        with open(json_file, "r") as f:
                            data = json.load(f)
                            
                            property_address = data.get("property_address", report_dir.name)
                            client_name = data.get("client_name", "Property Owner")
                            
                            # Group by property
                            if property_address not in property_map:
                                property_map[property_address] = {
                                    "id": f"prop_{len(property_map)}",
                                    "label": property_address,
                                    "address": property_address,
                                    "client_name": client_name,
                                    "reports": []
                                }
                            
                            # Count issues
                            critical = 0
                            important = 0
                            for item in data.get("items", []):
                                severity = item.get("severity", "").lower()
                                if "critical" in severity or "high" in severity:
                                    critical += 1
                                elif "medium" in severity or "important" in severity:
                                    important += 1
                            
                            property_map[property_address]["reports"].append({
                                "report_id": data.get("report_id", report_dir.name),
                                "created_at": data.get("inspection_date", datetime.now().isoformat()),
                                "photos": len(data.get("items", [])),
                                "critical": critical,
                                "important": important,
                                "pdf_path": str(report_dir / "pdf"),
                                "local_path": str(report_dir)
                            })
                    except Exception as e:
                        print(f"Error loading report from {report_dir}: {e}")
        
        properties = list(property_map.values())
    
    # No need to check gallery_storage - all reports are in workspace/outputs
    
    # Get first client name from properties or use default
    client_name = "Property Owner"
    if properties and len(properties) > 0:
        client_name = properties[0].get("client_name", "Property Owner")
    
    # Calculate stats
    total_reports = sum(len(p["reports"]) for p in properties)
    total_issues = sum(sum(r.get("critical", 0) + r.get("important", 0) for r in p["reports"]) for p in properties)
    
    # Calculate totals for each severity
    total_critical = sum(sum(r.get("critical", 0) for r in p["reports"]) for p in properties)
    total_important = sum(sum(r.get("important", 0) for r in p["reports"]) for p in properties)
    
    # Return in the format expected by the multi-property-gallery.html
    return {
        "owner": {
            "name": client_name,
            "email": "owner@property.com"  # Default email
        },
        "totals": {
            "properties": len(properties),
            "reports": total_reports,
            "critical": total_critical,
            "important": total_important
        },
        "properties": properties,
        "stats": {
            "total_inspections": total_reports,
            "properties_monitored": len(properties),
            "issues_found": total_issues,
            "last_inspection": datetime.now().strftime("%Y-%m-%d")
        }
    }

@app.get("/api/portal/properties/{property_id}")
async def get_property_details(property_id: str, token: str = Query(None)):
    """
    Get detailed report for a specific property with photo gallery data
    Simply match by property address or property_id
    """
    property_data = None
    reports = []
    
    # Search in outputs directory
    if OUTPUTS_DIR.exists():
        for report_dir in OUTPUTS_DIR.iterdir():
            if report_dir.is_dir():
                json_file = report_dir / "report_data.json"
                if not json_file.exists():
                    json_file = report_dir / "web" / "report.json"
                
                if json_file.exists():
                    try:
                        with open(json_file, "r") as f:
                            data = json.load(f)
                            
                            property_address = data.get("property_address", report_dir.name)
                            
                            # Simple matching - just check if this property matches
                            # Match by address (encoded in property_id) or report_id
                            property_match = False
                            
                            # If property_id is an address, match directly
                            if property_address and (property_id in property_address or property_address in property_id):
                                property_match = True
                            
                            # If property_id matches the report_id
                            if data.get("report_id") == property_id:
                                property_match = True
                            
                            # If property_id is in the directory name
                            if property_id in str(report_dir.name):
                                property_match = True
                                
                            # Match by prop_X pattern - use the address ordering
                            if property_id.startswith("prop_"):
                                # Get all unique addresses in sorted order
                                all_addresses = []
                                for rd in OUTPUTS_DIR.iterdir():
                                    if rd.is_dir():
                                        jf = rd / "report_data.json"
                                        if not jf.exists():
                                            jf = rd / "web" / "report.json"
                                        if jf.exists():
                                            try:
                                                with open(jf, "r") as f2:
                                                    d = json.load(f2)
                                                    addr = d.get("property_address", rd.name)
                                                    if addr not in all_addresses:
                                                        all_addresses.append(addr)
                                            except:
                                                pass
                                
                                all_addresses.sort()
                                try:
                                    prop_index = int(property_id.replace("prop_", ""))
                                    if prop_index < len(all_addresses) and property_address == all_addresses[prop_index]:
                                        property_match = True
                                except:
                                    pass
                            
                            if property_match:
                                
                                if not property_data:
                                    property_data = {
                                        "id": property_id,
                                        "label": property_address,
                                        "address": property_address
                                    }
                                
                                # Process items to include photo URLs
                                items_with_photos = []
                                photos_dir = report_dir / "photos"
                                web_photos_dir = report_dir / "web" / "photos"
                                
                                for idx, item in enumerate(data.get("items", [])):
                                    # Find the corresponding photo
                                    photo_filename = None
                                    photo_found = False
                                    
                                    # First check web/photos directory
                                    if web_photos_dir.exists():
                                        expected_photo = f"photo_{idx+1:03d}.jpg"
                                        if (web_photos_dir / expected_photo).exists():
                                            photo_filename = expected_photo
                                            photo_found = True
                                            photo_url = f"/api/reports/{report_dir.name}/web/photos/{photo_filename}"
                                    
                                    # Then check photos directory
                                    if not photo_found and photos_dir.exists():
                                        # Look for numbered photos
                                        for photo_file in sorted(photos_dir.glob("*")):
                                            if photo_file.is_file() and photo_file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                                                # Use the photo that matches the index
                                                if f"{idx+1:03d}" in photo_file.name:
                                                    photo_filename = photo_file.name
                                                    photo_found = True
                                                    photo_url = f"/api/reports/{report_dir.name}/photos/{photo_filename}"
                                                    break
                                    
                                    # If still no photo, use the image filename from the data
                                    if not photo_found:
                                        image_filename = item.get("image_filename", f"photo_{idx+1:03d}.jpg")
                                        photo_url = f"/api/reports/{report_dir.name}/photos/{image_filename}"
                                    
                                    items_with_photos.append({
                                        **item,
                                        "photo_url": photo_url,
                                        "photo_index": idx,
                                        "report_dir": report_dir.name
                                    })
                                
                                # Add report with full details including photos
                                reports.append({
                                    "report_id": data.get("report_id", report_dir.name),
                                    "created_at": data.get("inspection_date", datetime.now().isoformat()),
                                    "photos": len(data.get("items", [])),
                                    "items": items_with_photos,
                                    "critical": sum(1 for item in data.get("items", []) if "critical" in item.get("severity", "").lower()),
                                    "important": sum(1 for item in data.get("items", []) if "important" in item.get("severity", "").lower()),
                                    "pdf_available": (report_dir / "pdf").exists(),
                                    "pdf_url": f"/api/reports/{report_dir.name}/pdf",
                                    "local_path": str(report_dir),
                                    "report_dir_name": report_dir.name
                                })
                    except Exception as e:
                        print(f"Error processing report {report_dir}: {e}")
    
    if property_data:
        return {
            "property": property_data,
            "reports": reports
        }
    else:
        # Return default data
        return {
            "property": {
                "id": property_id,
                "label": f"Property {property_id}",
                "address": "Property Address"
            },
            "reports": []
        }

@app.get("/api/reports/{report_id}/pdf")
async def download_pdf(report_id: str):
    """
    Download PDF for a specific report
    """
    # Search in outputs directory
    for report_dir in OUTPUTS_DIR.glob("*"):
        if report_id in str(report_dir) or report_dir.name == report_id:
            pdf_dir = report_dir / "pdf"
            if pdf_dir.exists():
                for pdf_file in pdf_dir.glob("*.pdf"):
                    return FileResponse(
                        pdf_file, 
                        media_type="application/pdf",
                        filename=pdf_file.name
                    )
    
    return JSONResponse({"error": "PDF not found"}, status_code=404)

@app.get("/api/reports/{report_id}/web/photos/{photo_name}")
async def get_web_photo(report_id: str, photo_name: str):
    """
    Serve photos from web/photos directory
    """
    for report_dir in OUTPUTS_DIR.glob("*"):
        if report_id in str(report_dir) or report_dir.name == report_id:
            web_photos_dir = report_dir / "web" / "photos"
            if web_photos_dir.exists():
                photo_file = web_photos_dir / photo_name
                if photo_file.exists():
                    return FileResponse(
                        photo_file,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
    
    return JSONResponse({"error": f"Photo not found: {photo_name}"}, status_code=404)

@app.get("/api/reports/{report_id}/photos/{photo_name}")
async def get_photo(report_id: str, photo_name: str):
    """
    Serve photos from reports
    """
    # Search in outputs directory
    for report_dir in OUTPUTS_DIR.glob("*"):
        if report_id in str(report_dir):
            photos_dir = report_dir / "photos"
            if photos_dir.exists():
                photo_file = photos_dir / photo_name
                if photo_file.exists():
                    return FileResponse(photo_file)
    
    return JSONResponse({"error": "Photo not found"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("GALLERY SERVER - Multi-Property Dashboard")
    print("="*60)
    print("\nAccess the gallery at:")
    print("  http://localhost:8005/")
    print("  http://localhost:8005/?token=test")
    print("\nYour reports from workspace/outputs/ will appear automatically")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8005)