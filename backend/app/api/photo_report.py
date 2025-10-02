"""Photo-specific report viewer"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path
import json
import sqlite3

router = APIRouter()

@router.get("/{report_id}/{photo_filename}/json")
def get_photo_analysis_json(report_id: str, photo_filename: str):
    """Get individual photo analysis as JSON"""
    try:
        # Get report from database
        db_path = Path("../workspace/inspection_portal.db")
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        cur.execute("SELECT web_dir FROM reports WHERE id = ?", (report_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return {"error": "Report not found"}
        
        web_dir = row[0]
        
        # Load JSON report
        json_path = Path("..") / web_dir.replace("\\", "/") / "report.json"
        
        if not json_path.exists():
            return {"error": "Report JSON not found"}
        
        with open(json_path, 'r') as f:
            report_data = json.load(f)
        
        # Find the specific item for this photo
        print(f"Looking for photo: {photo_filename}")
        
        # Try different matching strategies
        for report_item in report_data.get("items", []):
            image_url = report_item.get("image_url", "")
            print(f"Checking against: {image_url}")
            
            # Try exact match first
            if image_url == photo_filename:
                print(f"Found exact match for {photo_filename}")
                return {
                    "location": report_item.get("location", "Unknown Location"),
                    "severity": report_item.get("severity", "informational"),
                    "observations": report_item.get("observations", []),
                    "potential_issues": report_item.get("potential_issues", []),
                    "recommendations": report_item.get("recommendations", [])
                }
            
            # Try endswith match
            if image_url.endswith(photo_filename):
                print(f"Found endswith match for {photo_filename}")
                return {
                    "location": report_item.get("location", "Unknown Location"),
                    "severity": report_item.get("severity", "informational"),
                    "observations": report_item.get("observations", []),
                    "potential_issues": report_item.get("potential_issues", []),
                    "recommendations": report_item.get("recommendations", [])
                }
            
            # Try matching just the filename without path
            if photo_filename in image_url:
                print(f"Found partial match for {photo_filename}")
                return {
                    "location": report_item.get("location", "Unknown Location"),
                    "severity": report_item.get("severity", "informational"),
                    "observations": report_item.get("observations", []),
                    "potential_issues": report_item.get("potential_issues", []),
                    "recommendations": report_item.get("recommendations", [])
                }
            
            # Try matching with different extensions or naming patterns
            photo_base = photo_filename.split('.')[0]
            if photo_base in image_url:
                print(f"Found base name match for {photo_filename}")
                return {
                    "location": report_item.get("location", "Unknown Location"),
                    "severity": report_item.get("severity", "informational"),
                    "observations": report_item.get("observations", []),
                    "potential_issues": report_item.get("potential_issues", []),
                    "recommendations": report_item.get("recommendations", [])
                }
        
        # If no match found, return the first item as fallback with a note
        print(f"No match found for {photo_filename}, returning first item as fallback")
        if report_data.get("items"):
            first_item = report_data["items"][0]
            return {
                "location": first_item.get("location", "Unknown Location"),
                "severity": first_item.get("severity", "informational"),
                "observations": first_item.get("observations", []),
                "potential_issues": first_item.get("potential_issues", []),
                "recommendations": first_item.get("recommendations", []),
                "note": f"Using general analysis - specific match not found for {photo_filename}"
            }
        
        return {"error": f"Analysis not found for {photo_filename}"}
        
    except Exception as e:
        print(f"Error getting photo analysis JSON: {e}")
        return {"error": str(e)}

@router.get("/{report_id}/{photo_filename}")
def get_photo_analysis(report_id: str, photo_filename: str):
    """Get individual photo analysis from report"""
    try:
        # Get report from database
        db_path = Path("../workspace/inspection_portal.db")
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        cur.execute("SELECT web_dir FROM reports WHERE id = ?", (report_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return HTMLResponse(content="<h1>404: Report not found</h1>", status_code=404)
        
        web_dir = row[0]
        
        # Load JSON report
        json_path = Path("..") / web_dir.replace("\\", "/") / "report.json"
        
        if not json_path.exists():
            return HTMLResponse(content="<h1>404: Report JSON not found</h1>", status_code=404)
        
        with open(json_path, 'r') as f:
            report_data = json.load(f)
        
        # Find the specific item for this photo
        item = None
        print(f"[HTML] Looking for photo: {photo_filename}")
        
        for report_item in report_data.get("items", []):
            image_url = report_item.get("image_url", "")
            print(f"[HTML] Checking against: {image_url}")
            
            # Try different matching strategies
            if (image_url == photo_filename or 
                image_url.endswith(photo_filename) or 
                photo_filename in image_url or
                photo_filename.split('.')[0] in image_url):
                print(f"[HTML] Found match for {photo_filename}")
                item = report_item
                break
        
        if not item and report_data.get("items"):
            # Use first item as fallback
            print(f"[HTML] No match found, using first item as fallback")
            item = report_data["items"][0]
        
        if not item:
            return HTMLResponse(content=f"<h1>404: Analysis not found for {photo_filename}</h1>", status_code=404)
        
        # Generate HTML for just this one item
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Inspection Analysis - {item.get('location', 'Unknown Location')}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                .photo-container {{
                    background: white;
                    border-radius: 8px;
                    padding: 10px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .photo-container img {{
                    width: 100%;
                    height: auto;
                    border-radius: 4px;
                    display: block;
                }}
                .header {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .item {{
                    background: white;
                    border-radius: 8px;
                    padding: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .severity {{
                    display: inline-block;
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-weight: 500;
                    font-size: 14px;
                    text-transform: uppercase;
                    margin-bottom: 15px;
                }}
                .severity-critical {{ background: #fee; color: #c00; }}
                .severity-important {{ background: #ffeaa7; color: #d63031; }}
                .severity-minor {{ background: #fff3cd; color: #856404; }}
                .severity-informational {{ background: #d1ecf1; color: #0c5460; }}
                h2 {{
                    color: #2c3e50;
                    border-bottom: 2px solid #ecf0f1;
                    padding-bottom: 10px;
                    margin: 20px 0 15px 0;
                }}
                h3 {{
                    color: #34495e;
                    margin: 15px 0 10px 0;
                }}
                ul {{
                    margin: 10px 0;
                    padding-left: 25px;
                }}
                li {{
                    margin: 5px 0;
                }}
                .photo-info {{
                    background: #f8f9fa;
                    padding: 10px;
                    border-radius: 4px;
                    margin-bottom: 15px;
                    font-size: 14px;
                    color: #6c757d;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Inspection Analysis</h1>
                <div class="photo-info">
                    <strong>Property:</strong> {report_data.get('property_address', 'Unknown')}<br>
                    <strong>Date:</strong> {report_data.get('inspection_date', 'Unknown')}
                </div>
            </div>
            
            <div class="photo-container">
                <img src="/api/photos/image/{report_id}/{photo_filename}" alt="Inspection photo: {photo_filename}" />
            </div>
            
            <div class="item">
                <span class="severity severity-{item.get('severity', 'informational')}">{item.get('severity', 'informational')}</span>
                <h2>{item.get('location', 'Unknown Location')}</h2>
                
                <h3>Observations</h3>
                <ul>
                    {"".join(f'<li>{obs}</li>' for obs in item.get('observations', []))}
                </ul>
                
                <h3>Potential Issues</h3>
                <ul>
                    {"".join(f'<li>{issue}</li>' for issue in item.get('potential_issues', []))}
                </ul>
                
                <h3>Recommendations</h3>
                <ul>
                    {"".join(f'<li>{rec}</li>' for rec in item.get('recommendations', []))}
                </ul>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        print(f"Error generating photo report HTML: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=f"<h1>Error generating report</h1><p>{str(e)}</p>", status_code=500)