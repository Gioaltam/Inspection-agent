"""
Integrated Gallery Server - Works with uploaded reports
"""

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_gallery(token: str = Query(None), report: str = Query(None)):
    """
    Serve the gallery with report data
    """
    # For now, serve the gallery viewer
    gallery_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Inspection Report Gallery</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 {
                color: #333;
                margin-bottom: 30px;
                text-align: center;
            }
            .report-section {
                margin: 20px 0;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 10px;
            }
            .report-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .report-card {
                background: white;
                border-radius: 10px;
                padding: 15px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                transition: transform 0.3s;
            }
            .report-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 5px 20px rgba(0,0,0,0.2);
            }
            .report-card h3 {
                color: #667eea;
                margin-bottom: 10px;
            }
            .report-card p {
                color: #666;
                margin: 5px 0;
            }
            .status-badge {
                display: inline-block;
                padding: 5px 10px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
            }
            .status-completed {
                background: #48bb78;
                color: white;
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 10px;
                transition: background 0.3s;
            }
            .btn:hover {
                background: #5a67d8;
            }
            .photo-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 20px;
            }
            .photo-item {
                background: #f0f0f0;
                border-radius: 8px;
                padding: 10px;
                text-align: center;
            }
            .photo-item img {
                max-width: 100%;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏠 Inspection Report Gallery</h1>
            <div id="content"></div>
        </div>
        
        <script>
            async function loadReports() {
                const content = document.getElementById('content');
                
                // Get URL parameters
                const params = new URLSearchParams(window.location.search);
                const reportId = params.get('report');
                
                if (reportId) {
                    // Load specific report
                    content.innerHTML = `
                        <div class="report-section">
                            <h2>Report Details</h2>
                            <div class="report-card">
                                <h3>Report ID: ${reportId}</h3>
                                <span class="status-badge status-completed">Completed</span>
                                <p>Upload Time: ${new Date().toLocaleString()}</p>
                                <p>Status: Report successfully uploaded and processed</p>
                            </div>
                            <div class="report-section">
                                <h3>📁 Report Files</h3>
                                <p>Your report has been saved in:</p>
                                <code>workspace/gallery_storage/</code>
                                <br><br>
                                <a href="/api/reports/${reportId}/pdf" class="btn">📄 Download PDF</a>
                                <a href="/api/reports/${reportId}/json" class="btn">📊 View JSON Data</a>
                            </div>
                        </div>
                    `;
                } else {
                    // Show all reports
                    try {
                        const response = await fetch('/api/reports');
                        const reports = await response.json();
                        
                        if (reports.length > 0) {
                            let html = '<div class="report-section"><h2>All Reports</h2><div class="report-grid">';
                            reports.forEach(report => {
                                html += `
                                    <div class="report-card">
                                        <h3>${report.property_address || 'Property Report'}</h3>
                                        <p>Client: ${report.client_id}</p>
                                        <p>Created: ${new Date(report.created_at).toLocaleDateString()}</p>
                                        <span class="status-badge status-completed">${report.status}</span>
                                        <br>
                                        <a href="/?report=${report.report_id}" class="btn">View Report</a>
                                    </div>
                                `;
                            });
                            html += '</div></div>';
                            content.innerHTML = html;
                        } else {
                            content.innerHTML = '<p>No reports found. Upload a report to see it here!</p>';
                        }
                    } catch (error) {
                        content.innerHTML = `
                            <div class="report-section">
                                <h2>Welcome to the Gallery</h2>
                                <p>Reports will appear here after uploading from the inspection app.</p>
                                <p>Recent uploads will be stored in: <code>workspace/gallery_storage/</code></p>
                            </div>
                        `;
                    }
                }
            }
            
            // Load reports on page load
            loadReports();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=gallery_html)

@app.get("/api/reports")
async def get_all_reports():
    """
    Get all uploaded reports
    """
    reports = []
    
    # Load from simple database
    db_file = STORAGE_DIR / "reports_db.json"
    if db_file.exists():
        with open(db_file, "r") as f:
            reports_db = json.load(f)
            reports = list(reports_db.values())
    
    # Also check outputs directory for local reports
    if OUTPUTS_DIR.exists():
        for report_dir in OUTPUTS_DIR.iterdir():
            if report_dir.is_dir():
                json_file = report_dir / "web" / "report.json"
                if json_file.exists():
                    try:
                        with open(json_file, "r") as f:
                            data = json.load(f)
                            reports.append({
                                "report_id": data.get("report_id", report_dir.name),
                                "property_address": data.get("property_address", report_dir.name),
                                "client_id": data.get("client_name", "Unknown"),
                                "created_at": datetime.fromtimestamp(report_dir.stat().st_mtime).isoformat(),
                                "status": "completed",
                                "local_path": str(report_dir)
                            })
                    except:
                        pass
    
    return reports

@app.get("/api/reports/{report_id}/pdf")
async def get_report_pdf(report_id: str):
    """
    Download PDF for a specific report
    """
    # Check in gallery storage
    for client_dir in STORAGE_DIR.glob("*"):
        for prop_dir in client_dir.glob("*"):
            for report_dir in prop_dir.glob("*"):
                if report_id in str(report_dir):
                    # Look for PDF
                    for pdf_file in report_dir.glob("**/*.pdf"):
                        return FileResponse(pdf_file, media_type="application/pdf")
    
    # Check in outputs directory
    for report_dir in OUTPUTS_DIR.glob("*"):
        if report_dir.is_dir():
            pdf_dir = report_dir / "pdf"
            if pdf_dir.exists():
                for pdf_file in pdf_dir.glob("*.pdf"):
                    return FileResponse(pdf_file, media_type="application/pdf")
    
    return JSONResponse({"error": "PDF not found"}, status_code=404)

@app.get("/api/reports/{report_id}/json")
async def get_report_json(report_id: str):
    """
    Get JSON data for a specific report
    """
    # Check in outputs directory
    for report_dir in OUTPUTS_DIR.glob("*"):
        if report_dir.is_dir():
            json_file = report_dir / "report_data.json"
            if not json_file.exists():
                json_file = report_dir / "web" / "report.json"
            
            if json_file.exists():
                with open(json_file, "r") as f:
                    return json.load(f)
    
    return JSONResponse({"error": "Report data not found"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("INTEGRATED GALLERY SERVER")
    print("="*60)
    print("\nGallery URLs:")
    print("  Main Gallery: http://localhost:8005/")
    print("  View Report: http://localhost:8005/?report=REPORT_ID")
    print("  All Reports: http://localhost:8005/api/reports")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8005)