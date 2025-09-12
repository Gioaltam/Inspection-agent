"""Reports API endpoints"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
import sqlite3
import json
from pathlib import Path

router = APIRouter()

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
        
        # Get reports for the owner
        if owner_id == "DEMO1234":
            # For Juliana, get reports where client name is DEMO1234 OR client ID is 2
            cur.execute("""
                SELECT r.id, r.web_dir, r.pdf_path, r.created_at,
                       p.address, c.name as client_name
                FROM reports r
                JOIN properties p ON r.property_id = p.id
                JOIN clients c ON p.client_id = c.id
                WHERE c.name = 'DEMO1234' OR c.id = 2
                ORDER BY r.created_at DESC
            """)
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
            
            # Parse the report details from the path
            html_path = Path(html_path) if html_path else None
            
            # Try to read the report JSON for more details
            report_details = {}
            if html_path and html_path.parent.exists():
                json_path = html_path.parent.parent / "analysis" / "report.json"
                if json_path.exists():
                    try:
                        with open(json_path, 'r') as f:
                            report_data = json.load(f)
                            report_details = {
                                "criticalIssues": len([i for i in report_data.get("items", []) 
                                                      if i.get("severity") == "critical"]),
                                "importantIssues": len([i for i in report_data.get("items", []) 
                                                       if i.get("severity") == "important"]),
                                "totalPhotos": len(report_data.get("items", []))
                            }
                    except:
                        pass
            
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