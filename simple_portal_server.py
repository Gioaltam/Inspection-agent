"""
Simple test server for the owner dashboard
"""
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import os

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load dashboard data if it exists
dashboard_data = {}
if os.path.exists("dashboard_data.json"):
    with open("dashboard_data.json", "r") as f:
        dashboard_data = json.load(f)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the enhanced multi-property gallery (combined dashboard) at root
@app.get("/")
async def serve_root():
    return FileResponse("static/multi-property-gallery.html")

# API endpoint for dashboard data
@app.get("/api/portal")
async def get_portal_data(token: str = Query(...)):
    if token == dashboard_data.get("token"):
        return JSONResponse(dashboard_data["dashboard_data"])
    return JSONResponse({"error": "Invalid token"}, status_code=401)

# API endpoint for property details
@app.get("/api/portal/properties/{property_id}")
async def get_property_details(property_id: str, token: str = Query(...)):
    if token == dashboard_data.get("token"):
        property_details = dashboard_data.get("property_details", {})
        if property_id in property_details:
            return JSONResponse(property_details[property_id])
        # Return mock data for other properties
        return JSONResponse({
            "property": {
                "id": property_id,
                "label": f"Property {property_id}",
                "address": "123 Main St, Seattle, WA"
            },
            "reports": [
                {
                    "report_id": f"report_{property_id}_1",
                    "created_at": "2025-08-20T10:00:00Z",
                    "photos": 25,
                    "critical": 2,
                    "important": 5
                }
            ]
        })
    return JSONResponse({"error": "Invalid token"}, status_code=401)

if __name__ == "__main__":
    import uvicorn
    # First generate the token
    if not os.path.exists("dashboard_data.json"):
        import subprocess
        subprocess.run(["python", "generate_dashboard_token.py"])
    
    # Load the generated data
    with open("dashboard_data.json", "r") as f:
        dashboard_data = json.load(f)
    
    print(f"\n{'='*60}")
    print("OWNER PORTAL SERVER RUNNING")
    print(f"{'='*60}")
    print(f"\nOwner Portal URL: http://localhost:8005/?token={dashboard_data['token']}")
    print(f"\nDirect link (click to open):")
    print(f"http://localhost:8005/?token={dashboard_data['token']}")
    print(f"\n{'='*60}\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8005)