"""
Test server for the owner dashboard with comprehensive mock data
"""
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import os
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

# Load or create mock data
def load_mock_data():
    if not os.path.exists("mock_portal_data.json"):
        import subprocess
        subprocess.run(["python", "create_test_portal.py"])
    
    with open("mock_portal_data.json", "r") as f:
        return json.load(f)

# Initialize mock data
mock_data = load_mock_data()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Redirect to Next.js dashboard
@app.get("/")
async def serve_root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="http://localhost:3000", status_code=302)

# API endpoint for dashboard data
@app.get("/api/portal")
async def get_portal_data(token: str = Query(...)):
    if token == mock_data.get("token"):
        return JSONResponse(mock_data["dashboard_data"])
    return JSONResponse({"error": "Invalid token"}, status_code=401)

# API endpoint for property details
@app.get("/api/portal/properties/{property_id}")
async def get_property_details(property_id: str, token: str = Query(...)):
    if token == mock_data.get("token"):
        property_details = mock_data.get("property_details", {})
        if property_id in property_details:
            return JSONResponse(property_details[property_id])
        # Return error for unknown property
        return JSONResponse({"error": "Property not found"}, status_code=404)
    return JSONResponse({"error": "Invalid token"}, status_code=401)

# API endpoint for downloading report
@app.get("/api/reports/{report_id}/download")
async def download_report(report_id: str, token: str = Query(...)):
    if token == mock_data.get("token"):
        # In a real app, this would serve the actual PDF
        return JSONResponse({
            "message": "Report download would be initiated",
            "report_id": report_id,
            "filename": f"inspection_report_{report_id[:8]}.pdf"
        })
    return JSONResponse({"error": "Invalid token"}, status_code=401)

# Health check endpoint
@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "mock_data_loaded": bool(mock_data)
    })

if __name__ == "__main__":
    import uvicorn
    
    # Ensure mock data exists
    mock_data = load_mock_data()
    
    print("\n" + "="*70)
    print("CHECKMYRENTAL OWNER PORTAL - TEST SERVER")
    print("="*70)
    print(f"\nDashboard URL: http://localhost:8005/?token={mock_data['token']}")
    print(f"\nDirect link (Ctrl+Click to open):")
    print(f"http://localhost:8005/?token={mock_data['token']}")
    print("\nAPI Endpoints:")
    print(f"  Dashboard: http://localhost:8005/api/portal?token={mock_data['token']}")
    print(f"  Property: http://localhost:8005/api/portal/properties/prop_1?token={mock_data['token']}")
    print("\nPress Ctrl+C to stop the server")
    print("="*70 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8005)