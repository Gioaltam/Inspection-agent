"""Reports API endpoints"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from pydantic import BaseModel
import sqlite3
import json
from pathlib import Path
from datetime import datetime

from ..lib.paths import (
    repo_root,
    outputs_root,
    find_latest_report_dir_by_address,
    photos_dir_for_report_dir,
    list_photos_in_dir,
)

router = APIRouter()

def _photos_count_from_web_dir(web_dir: str) -> int:
    """
    Accepts web_dir as either absolute or repo-relative and returns count of photos.
    """
    base = Path(web_dir)
    base = base if base.is_absolute() else (repo_root() / base)
    photos_dir = base / "photos"  # web_dir already points at ".../web"
    return len(list_photos_in_dir(photos_dir))

class ReportSaveRequest(BaseModel):
    report_id: str
    owner_id: str
    property_address: str
    date: str
    inspector: str
    status: str
    web_dir: str
    pdf_path: str
    critical_issues: int = 0
    important_issues: int = 0

@router.get("/list")
def get_reports(owner_id: str = Query(None, description="Owner ID to filter reports")):
    """Get all reports for a specific owner or all reports"""
    
    try:
        # Connect to the inspection database (not the backend database)
        db_path = Path("../workspace/inspection_portal.db")
        print(f"Looking for database at: {db_path.absolute()}")
        if not db_path.exists():
            print(f"Database not found at {db_path}")
            return {"reports": []}
            
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        # Get reports for the specific owner
        if owner_id:
            # Get reports where client name matches the owner_id
            cur.execute("""
                SELECT r.id, r.web_dir, r.pdf_path, r.created_at,
                       p.address, c.name as client_name
                FROM reports r
                JOIN properties p ON r.property_id = p.id
                JOIN clients c ON p.client_id = c.id
                WHERE c.name = ?
                ORDER BY r.created_at DESC
            """, (owner_id,))
        else:
            # Get all reports
            cur.execute("""
                SELECT r.id, r.web_dir, r.pdf_path, r.created_at,
                       p.address, c.name as client_name
                FROM reports r
                JOIN properties p ON r.property_id = p.id
                JOIN clients c ON p.client_id = c.id
                ORDER BY r.created_at DESC
            """)
        
        rows = cur.fetchall()
        reports = []
        
        for row in rows:
            report_id, html_path, pdf_path, created_at, address, client_name = row

            # Try to read report details and count photos
            report_details = {}

            # Count actual photos from the web_dir
            photo_count = 0
            if html_path:
                try:
                    photo_count = _photos_count_from_web_dir(html_path)
                except Exception as e:
                    print(f"Error counting photos: {e}")
                    # Fallback to address-based resolution
                    report_dir = find_latest_report_dir_by_address(address)
                    if report_dir:
                        photos_dir = photos_dir_for_report_dir(report_dir)
                        photo_count = len(list_photos_in_dir(photos_dir))

            # Try to read report.json for issue counts
            if html_path:
                base = Path(html_path)
                base = base if base.is_absolute() else (repo_root() / base)
                json_path = base / "report.json"

                if json_path.exists():
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            report_data = json.load(f)
                            items = report_data.get("items", [])

                            # Count issues by severity (map minor to important for display)
                            critical_count = sum(1 for i in items if i.get("severity") in ["critical", "major"])
                            important_count = sum(1 for i in items if i.get("severity") in ["important", "minor"])

                            report_details = {
                                "criticalIssues": critical_count,
                                "importantIssues": important_count,
                                "totalPhotos": photo_count  # Use actual photo count from files
                            }
                    except Exception as e:
                        print(f"Error reading report JSON: {e}")
                        report_details = {
                            "criticalIssues": 0,
                            "importantIssues": 0,
                            "totalPhotos": photo_count
                        }
                else:
                    # No JSON file, just use photo count
                    report_details = {
                        "criticalIssues": 0,
                        "importantIssues": 0,
                        "totalPhotos": photo_count
                    }
            
            reports.append({
                "id": report_id,
                "date": created_at,
                "property": address,
                "inspector": "Inspection Agent",
                "status": "completed",
                "criticalIssues": report_details.get("criticalIssues", 0),
                "importantIssues": report_details.get("importantIssues", 0),
                "totalPhotos": report_details.get("totalPhotos", 0),
                "htmlPath": str(html_path) if html_path else None,
                "pdfPath": str(pdf_path) if pdf_path else None,
                "reportUrl": f"/api/reports/view/{report_id}"
            })
        
        conn.close()
        return {"reports": reports}
        
    except Exception as e:
        print(f"Error fetching reports: {e}")
        return {"reports": []}

@router.post("/save")
def save_report(report: ReportSaveRequest):
    """Save report data from run_report.py for dashboard display"""
    try:
        # For now, store in the same SQLite database
        db_path = Path("../workspace/inspection_portal.db")

        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # First ensure the clients table exists and get/create client
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                UNIQUE(name, email)
            )
        """)

        # Insert or get client for this owner_id
        cur.execute("SELECT id FROM clients WHERE name = ?", (report.owner_id,))
        row = cur.fetchone()
        if row:
            client_id = row['id']
        else:
            cur.execute("INSERT INTO clients (name, email) VALUES (?, '')", (report.owner_id,))
            client_id = cur.lastrowid

        # Ensure properties table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id),
                UNIQUE(client_id, address)
            )
        """)

        # Insert or get property
        cur.execute("SELECT id FROM properties WHERE client_id = ? AND address = ?",
                   (client_id, report.property_address))
        row = cur.fetchone()
        if row:
            property_id = row['id']
        else:
            cur.execute("INSERT INTO properties (client_id, address) VALUES (?, ?)",
                       (client_id, report.property_address))
            property_id = cur.lastrowid

        # Ensure reports table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                property_id INTEGER NOT NULL,
                web_dir TEXT,
                pdf_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties(id)
            )
        """)

        # Check if report already exists
        cur.execute("SELECT id FROM reports WHERE id = ?", (report.report_id,))
        if not cur.fetchone():
            # Insert new report
            cur.execute("""
                INSERT INTO reports (id, property_id, web_dir, pdf_path)
                VALUES (?, ?, ?, ?)
            """, (report.report_id, property_id, report.web_dir, report.pdf_path))

        conn.commit()
        conn.close()

        print(f"✅ Report {report.report_id} saved for owner {report.owner_id}")
        return {"status": "success", "report_id": report.report_id}

    except Exception as e:
        print(f"Error saving report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save report: {str(e)}")

@router.get("/view/{report_id}")
def view_report(report_id: str):
    """Get report details and serve the HTML"""
    from fastapi.responses import HTMLResponse
    
    try:
        db_path = Path("../workspace/inspection_portal.db")
        if not db_path.exists():
            raise HTTPException(status_code=404, detail="Database not found")
            
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        cur.execute("""
            SELECT r.web_dir, r.pdf_path, p.address
            FROM reports r
            JOIN properties p ON r.property_id = p.id
            WHERE r.id = ?
        """, (report_id,))
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
            
        web_dir, pdf_path, address = row
        
        # Look for report.json in the web directory
        if web_dir:
            # Convert Windows path and make it relative to backend
            web_path = Path("..") / web_dir.replace("\\", "/")
            json_file = web_path / "report.json"
            
            print(f"Looking for report JSON at: {json_file}")
            print(f"Absolute path: {json_file.absolute()}")
            print(f"File exists: {json_file.exists()}")
            
            if json_file.exists():
                with open(json_file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                
                # Generate HTML from the report data
                html_content = f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Inspection Report - {address}</title>
                    <style>
                        body {{
                            font-family: system-ui, -apple-system, sans-serif;
                            background: #0a0a0a;
                            color: #fff;
                            margin: 0;
                            padding: 20px;
                        }}
                        .container {{
                            max-width: 1200px;
                            margin: 0 auto;
                        }}
                        h1 {{
                            color: #ef4444;
                            border-bottom: 1px solid rgba(255,255,255,0.1);
                            padding-bottom: 1rem;
                        }}
                        .summary {{
                            background: rgba(255,255,255,0.05);
                            border-radius: 8px;
                            padding: 20px;
                            margin: 20px 0;
                        }}
                        .item {{
                            background: rgba(255,255,255,0.05);
                            border-radius: 8px;
                            padding: 20px;
                            margin: 20px 0;
                        }}
                        .item h3 {{
                            margin-top: 0;
                            color: #fbbf24;
                        }}
                        .severity-critical {{
                            border-left: 4px solid #ef4444;
                        }}
                        .severity-important {{
                            border-left: 4px solid #f59e0b;
                        }}
                        .severity-minor {{
                            border-left: 4px solid #3b82f6;
                        }}
                        .photos {{
                            display: grid;
                            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                            gap: 10px;
                            margin-top: 10px;
                        }}
                        .photos img {{
                            width: 100%;
                            border-radius: 4px;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Inspection Report</h1>
                        <div class="summary">
                            <h2>Property: {address}</h2>
                            <p>Report ID: {report_id}</p>
                            <p>Total Issues: {len(report_data.get('items', []))}</p>
                        </div>
                """
                
                # Add items
                for item in report_data.get('items', []):
                    severity_class = f"severity-{item.get('severity', 'minor')}"
                    html_content += f"""
                        <div class="item {severity_class}">
                            <h3>{item.get('location', 'Unknown Location')}</h3>
                            <p><strong>Severity:</strong> {item.get('severity', 'minor').capitalize()}</p>
                            <p>{item.get('description', 'No description available')}</p>
                    """
                    
                    # Add photos if available
                    photos = item.get('photos', [])
                    if photos:
                        html_content += '<div class="photos">'
                        for photo in photos:
                            photo_path = f"/static/{photo}"  # Adjust path as needed
                            html_content += f'<img src="{photo_path}" alt="Inspection photo">'
                        html_content += '</div>'
                    
                    html_content += '</div>'
                
                html_content += """
                    </div>
                </body>
                </html>
                """
                
                return HTMLResponse(content=html_content)
        
        raise HTTPException(status_code=404, detail="Report data not found")
            
    except Exception as e:
        print(f"Error viewing report: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{report_id}")
def download_report(report_id: str):
    """Download report PDF"""
    from fastapi.responses import FileResponse
    
    try:
        db_path = Path("../workspace/inspection_portal.db")
        if not db_path.exists():
            raise HTTPException(status_code=404, detail="Database not found")
            
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        cur.execute("""
            SELECT r.pdf_path, p.address
            FROM reports r
            JOIN properties p ON r.property_id = p.id
            WHERE r.id = ?
        """, (report_id,))
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
            
        pdf_path, address = row
        
        if pdf_path:
            pdf_file = Path(pdf_path)
            if pdf_file.exists():
                return FileResponse(
                    str(pdf_file), 
                    media_type="application/pdf",
                    filename=f"inspection_report_{report_id}.pdf"
                )
        
        raise HTTPException(status_code=404, detail="PDF not found")
            
    except Exception as e:
        print(f"Error downloading report: {e}")
        raise HTTPException(status_code=500, detail=str(e))