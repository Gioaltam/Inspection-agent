#!/usr/bin/env python3
"""
Run Report Module - Core functionality for inspection report generation from ZIP files
This module handles the complete workflow of processing property inspection photos:
1. Extract photos from ZIP files
2. Analyze each photo using AI vision
3. Generate comprehensive HTML and PDF reports
4. Register reports with the portal system
"""

import os
import sys

# Fix Windows console encoding issues with Unicode
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import json
import secrets
import sqlite3
import zipfile
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import inch

# Import vision analysis module
try:
    from vision import describe_image
except ImportError:
    print("Warning: vision.py not found, using placeholder analysis")
    def describe_image(path):
        return "Image analysis not available"

# Directory Configuration
WORKSPACE = Path(os.environ.get('WORKSPACE_DIR', './workspace'))
OUTPUTS_DIR = WORKSPACE / 'outputs'
INCOMING_DIR = WORKSPACE / 'incoming'
DB_PATH = WORKSPACE / 'inspection_portal.db'

# Ensure directories exist
for dir_path in [WORKSPACE, OUTPUTS_DIR, INCOMING_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Portal configuration
PORTAL_EXTERNAL_BASE_URL = os.environ.get("PORTAL_EXTERNAL_BASE_URL", "http://localhost:8000").rstrip("/")

def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return the path"""
    path.mkdir(parents=True, exist_ok=True)
    return path

# ============== Database Functions ==============

def db_init():
    """Initialize database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Create tables if they don't exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            address TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            property_id INTEGER,
            web_dir TEXT,
            pdf_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (property_id) REFERENCES properties(id)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_id TEXT,
            expires_at TEXT NOT NULL,
            revoked INTEGER DEFAULT 0,
            payload_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES reports(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def db_connect():
    """Connect to database with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def db_upsert_client(conn: sqlite3.Connection, name: str, email: str = "") -> int:
    """Insert or update client and return client ID"""
    cur = conn.cursor()
    
    # Check if client exists
    cur.execute("SELECT id FROM clients WHERE name = ? AND email = ?", (name, email))
    row = cur.fetchone()
    
    if row:
        return row['id']
    
    # Insert new client
    cur.execute("INSERT INTO clients (name, email) VALUES (?, ?)", (name, email))
    conn.commit()
    return cur.lastrowid

def db_upsert_property(conn: sqlite3.Connection, client_id: int, address: str) -> int:
    """Insert or update property and return property ID"""
    cur = conn.cursor()
    
    # Check if property exists
    cur.execute("SELECT id FROM properties WHERE client_id = ? AND address = ?", (client_id, address))
    row = cur.fetchone()
    
    if row:
        return row['id']
    
    # Insert new property
    cur.execute("INSERT INTO properties (client_id, address) VALUES (?, ?)", (client_id, address))
    conn.commit()
    return cur.lastrowid

def db_insert_report(conn: sqlite3.Connection, report_id: str, property_id: int, web_dir: str, pdf_path: str) -> str:
    """Insert report and return report ID"""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reports (id, property_id, web_dir, pdf_path) VALUES (?, ?, ?, ?)",
        (report_id, property_id, web_dir, pdf_path)
    )
    conn.commit()
    return report_id

def db_create_token(conn: sqlite3.Connection, kind: str, ttl_hours: int, 
                   report_id: Optional[str] = None, payload_json: Optional[str] = None) -> str:
    """Create access token with expiration"""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat() + 'Z'
    
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tokens (token, kind, report_id, expires_at, payload_json) VALUES (?, ?, ?, ?, ?)",
        (token, kind, report_id, expires_at, payload_json)
    )
    conn.commit()
    return token

def now_iso() -> str:
    """Return current time in ISO format"""
    return datetime.utcnow().isoformat() + 'Z'

# ============== Image Processing Functions ==============

def extract_zip(zip_path: Path) -> Path:
    """Extract ZIP file to temporary directory and return path to photos"""
    extract_dir = Path(tempfile.mkdtemp(prefix="inspection_"))
    
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)
    
    # Check for common photo directory names
    for subdir_name in ['photos', 'images', 'Pictures']:
        subdir = extract_dir / subdir_name
        if subdir.exists() and subdir.is_dir():
            return subdir
    
    # Return root extraction dir if no subdirectory found
    return extract_dir

def collect_images(photos_dir: Path) -> List[Path]:
    """Collect all image files from directory"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    images = []
    
    for file_path in photos_dir.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            images.append(file_path)
    
    # Sort by name for consistent ordering
    images.sort(key=lambda p: p.name.lower())
    return images

def analyze_images(images: List[Path]) -> Dict[str, str]:
    """Analyze all images using vision AI with concurrent processing"""
    import concurrent.futures
    import threading
    
    results = {}
    total = len(images)
    
    # Get concurrency setting from environment
    max_workers = int(os.getenv('ANALYSIS_CONCURRENCY', '3'))
    
    print(f"Starting analysis of {total} images (concurrency={max_workers})...")
    
    # Thread-safe counter for progress
    counter_lock = threading.Lock()
    counter = [0]
    
    def analyze_one(img_path: Path) -> Tuple[str, str]:
        """Analyze a single image and return path and result"""
        with counter_lock:
            counter[0] += 1
            current = counter[0]
        
        print(f"[{current}/{total}] Analyzing {img_path.name}...")
        try:
            analysis = describe_image(img_path)
            return str(img_path), analysis
        except Exception as e:
            print(f"  Error analyzing {img_path.name}: {e}")
            return str(img_path), f"Analysis failed: {str(e)}"
    
    # Process images concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = [executor.submit(analyze_one, img) for img in images]
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            try:
                path, analysis = future.result()
                results[path] = analysis
            except Exception as e:
                print(f"  Unexpected error: {e}")
    
    return results

# ============== Report Generation Functions ==============

def parse_analysis(text: str) -> Dict[str, Any]:
    """Parse vision analysis text into structured sections"""
    sections = {
        "location": "",
        "observations": [],
        "potential_issues": [],
        "recommendations": []
    }
    
    current_section = None
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Check for section headers (support both old and new formats)
        if line.lower().startswith("location:"):
            current_section = "location"
            sections[current_section] = line.split(":", 1)[1].strip() if ":" in line else ""
        elif line.lower().startswith("what i see:") or line.lower().startswith("observations:"):
            current_section = "observations"
        elif line.lower().startswith("issues to address:") or line.lower().startswith("potential issues:"):
            current_section = "potential_issues"
        elif line.lower().startswith("recommended action:") or line.lower().startswith("recommendations:"):
            current_section = "recommendations"
        elif line.startswith("- ") and current_section in ["observations", "potential_issues", "recommendations"]:
            sections[current_section].append(line[2:].strip())
        elif line and current_section == "location":
            sections[current_section] += " " + line
        elif line and current_section in ["observations", "potential_issues", "recommendations"]:
            # Handle "No repairs needed" or similar messages
            if "no repairs needed" in line.lower() or "no issues" in line.lower():
                if current_section == "potential_issues" and not sections[current_section]:
                    sections[current_section] = []  # Keep empty for no issues
            else:
                sections[current_section].append(line)
    
    return sections

def categorize_issue(sections: Dict[str, Any]) -> str:
    """Categorize issue severity based on analysis content"""
    critical_keywords = ["structural", "foundation", "roof leak", "electrical hazard", 
                        "gas leak", "black mold", "asbestos", "immediate safety", "dangerous", "urgent"]
    important_keywords = ["needs repair", "should replace", "significant damage", "water damage", 
                         "major crack", "active leak", "extensive", "failing"]
    
    # Combine text for analysis - focus on actual issues reported
    issues = sections.get("potential_issues", [])
    
    # If no issues reported, it's informational
    if not issues or all("no repairs" in str(i).lower() or "no issues" in str(i).lower() for i in issues):
        return "informational"
    
    text = " ".join(issues) + " " + " ".join(sections.get("recommendations", []))
    text_lower = text.lower()
    
    # Check for critical issues
    for keyword in critical_keywords:
        if keyword in text_lower:
            return "critical"
    
    # Check for important issues
    for keyword in important_keywords:
        if keyword in text_lower:
            return "important"
    
    return "minor"

def save_report_json(report_data: Dict[str, Any], output_dir: Path) -> Path:
    """Save report data as JSON for template consumption"""
    json_path = output_dir / "report.json"
    
    # Enhanced JSON structure with metadata
    enhanced_data = {
        **report_data,
        'generated_at': datetime.now().isoformat(),
        'version': '2.0',
        'categories': categorize_photos(report_data['items']),
        'statistics': calculate_statistics(report_data['items'])
    }
    
    json_path.write_text(json.dumps(enhanced_data, indent=2), encoding='utf-8')
    return json_path

def categorize_photos(items: List[Dict]) -> Dict[str, List[int]]:
    """Categorize photos by location and severity"""
    categories = {
        'by_location': {},
        'by_severity': {'critical': [], 'important': [], 'minor': [], 'informational': []},
        'by_type': {}
    }
    
    for i, item in enumerate(items):
        # By severity - handle all possible values including 'informational'
        severity = item.get('severity', 'minor')
        if severity in categories['by_severity']:
            categories['by_severity'][severity].append(i)
        
        # By location
        location = item.get('location', 'General').split(':')[0].strip()
        if location not in categories['by_location']:
            categories['by_location'][location] = []
        categories['by_location'][location].append(i)
        
        # By issue type (extracted from observations)
        for obs in item.get('observations', []):
            if 'water' in obs.lower() or 'leak' in obs.lower():
                categories['by_type'].setdefault('Water/Moisture', []).append(i)
            if 'electrical' in obs.lower():
                categories['by_type'].setdefault('Electrical', []).append(i)
            if 'structural' in obs.lower():
                categories['by_type'].setdefault('Structural', []).append(i)
    
    return categories

def calculate_statistics(items: List[Dict]) -> Dict:
    """Calculate report statistics"""
    return {
        'total_photos': len(items),
        'critical_count': sum(1 for item in items if item.get('severity') == 'critical'),
        'important_count': sum(1 for item in items if item.get('severity') == 'important'),
        'minor_count': sum(1 for item in items if item.get('severity') == 'minor'),
        'informational_count': sum(1 for item in items if item.get('severity') == 'informational'),
        'has_issues': sum(1 for item in items if item.get('potential_issues')),
        'needs_action': sum(1 for item in items if item.get('recommendations'))
    }

def generate_html_report(report_data: Dict[str, Any], output_dir: Path) -> Path:
    """Generate HTML report with all photos and analysis"""
    html_path = output_dir / "index.html"
    
    # Count issues by severity
    critical_count = sum(1 for item in report_data['items'] if item.get('severity') == 'critical')
    important_count = sum(1 for item in report_data['items'] if item.get('severity') == 'important')
    minor_count = sum(1 for item in report_data['items'] if item.get('severity') == 'minor')
    informational_count = sum(1 for item in report_data['items'] if item.get('severity') == 'informational')
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Inspection Report - {report_data['property_address']}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #2c3e50;
            background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(44, 62, 80, 0.1);
            padding: 40px;
            border-radius: 16px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            position: relative;
            overflow: hidden;
        }}
        .header::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: linear-gradient(90deg, #e74c3c 0%, #2c3e50 100%);
        }}
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .logo-icon {{
            position: relative;
            width: 45px;
            height: 45px;
            flex-shrink: 0;
        }}
        .logo-house {{
            width: 35px;
            height: 35px;
            background: #2c3e50;
            transform: rotate(45deg);
            position: absolute;
            top: 5px;
            left: 5px;
        }}
        .logo-window {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 12px;
            height: 12px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            grid-template-rows: 1fr 1fr;
            gap: 2px;
        }}
        .logo-window span {{
            background: white;
            display: block;
        }}
        .logo-check {{
            position: absolute;
            bottom: 0;
            right: 0;
            width: 20px;
            height: 20px;
            background: #e74c3c;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .logo-check::after {{
            content: '';
            width: 8px;
            height: 4px;
            border: 2px solid white;
            border-top: none;
            border-right: none;
            transform: rotate(-45deg);
            margin-bottom: 2px;
        }}
        .logo-text {{
            font-size: 28px;
            font-weight: 700;
            color: #2c3e50;
        }}
        .header h1 {{
            font-size: 2.2em;
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .header-info {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .header-info-item {{
            display: flex;
            flex-direction: column;
        }}
        .header-info-label {{
            font-size: 12px;
            text-transform: uppercase;
            color: #7f8c8d;
            letter-spacing: 1px;
            margin-bottom: 4px;
        }}
        .header-info-value {{
            font-size: 16px;
            font-weight: 600;
            color: #2c3e50;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: rgba(255, 255, 255, 0.95);
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border: 1px solid rgba(44, 62, 80, 0.1);
        }}
        .summary-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.2);
        }}
        .summary-card .number {{
            font-size: 3em;
            font-weight: 700;
            margin-bottom: 5px;
        }}
        .summary-card .label {{
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #7f8c8d;
        }}
        .critical {{ 
            color: #e74c3c;
            background: linear-gradient(135deg, #e74c3c, #c0392b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .important {{ 
            color: #f39c12;
            background: linear-gradient(135deg, #f39c12, #e67e22);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .minor {{ 
            color: #27ae60;
            background: linear-gradient(135deg, #27ae60, #229954);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .item {{
            background: rgba(255, 255, 255, 0.98);
            margin-bottom: 30px;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            border: 1px solid rgba(44, 62, 80, 0.1);
            transition: transform 0.3s ease;
        }}
        .item:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 25px rgba(0,0,0,0.2);
        }}
        .item-header {{
            padding: 25px;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border-bottom: 3px solid #2c3e50;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .item-header h3 {{
            margin: 0;
            color: #2c3e50;
            font-size: 1.3em;
            font-weight: 600;
        }}
        .severity-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 24px;
            font-size: 0.85em;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }}
        .severity-critical {{
            background: linear-gradient(135deg, #e74c3c, #c0392b);
            color: white;
        }}
        .severity-important {{
            background: linear-gradient(135deg, #f39c12, #e67e22);
            color: white;
        }}
        .severity-minor {{
            background: linear-gradient(135deg, #27ae60, #229954);
            color: white;
        }}
        .severity-informational {{
            background: linear-gradient(135deg, #95a5a6, #7f8c8d);
            color: white;
        }}
        .item-image {{
            width: 100%;
            max-height: 600px;
            object-fit: contain;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        .item-content {{
            padding: 30px;
            background: white;
        }}
        .section {{
            margin-bottom: 25px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #2c3e50;
        }}
        .section h4 {{
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 1.2em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .section ul {{
            margin: 0;
            padding-left: 0;
            list-style: none;
        }}
        .section li {{
            margin-bottom: 10px;
            padding-left: 25px;
            position: relative;
            line-height: 1.8;
            color: #495057;
        }}
        .section li::before {{
            content: '▸';
            position: absolute;
            left: 0;
            color: #e74c3c;
            font-weight: bold;
        }}
        .footer {{
            margin-top: 50px;
            padding: 30px;
            background: rgba(255, 255, 255, 0.98);
            border-radius: 12px;
            text-align: center;
            border: 1px solid rgba(44, 62, 80, 0.1);
        }}
        .footer-logo {{
            font-size: 24px;
            font-weight: 700;
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .footer-text {{
            color: #7f8c8d;
            font-size: 14px;
        }}
        @media print {{
            body {{ background: white; }}
            .item {{ page-break-inside: avoid; box-shadow: none; }}
            .summary-card {{ box-shadow: none; }}
            .header {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-section">
                <div class="logo-icon">
                    <div class="logo-house">
                        <div class="logo-window">
                            <span></span>
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </div>
                    <div class="logo-check"></div>
                </div>
                <div class="logo-text">CheckMyRental</div>
            </div>
            <h1>Property Inspection Report</h1>
            <div class="header-info">
                <div class="header-info-item">
                    <div class="header-info-label">Property Address</div>
                    <div class="header-info-value">{report_data['property_address']}</div>
                </div>
                <div class="header-info-item">
                    <div class="header-info-label">Client</div>
                    <div class="header-info-value">{report_data['client_name']}</div>
                </div>
                <div class="header-info-item">
                    <div class="header-info-label">Inspection Date</div>
                    <div class="header-info-value">{report_data['inspection_date']}</div>
                </div>
                <div class="header-info-item">
                    <div class="header-info-label">Report ID</div>
                    <div class="header-info-value">{report_data['report_id'][:8]}...</div>
                </div>
            </div>
        </div>
        
        <div class="summary">
            <div class="summary-card">
                <div class="number">{len(report_data['items'])}</div>
                <div class="label">Total Photos</div>
            </div>
            <div class="summary-card">
                <div class="number critical">{critical_count}</div>
                <div class="label">Critical Issues</div>
            </div>
            <div class="summary-card">
                <div class="number important">{important_count}</div>
                <div class="label">Important Issues</div>
            </div>
            <div class="summary-card">
                <div class="number minor">{minor_count}</div>
                <div class="label">Minor Issues</div>
            </div>
        </div>
"""
    
    # Add each photo and analysis
    for i, item in enumerate(report_data['items'], 1):
        severity_class = f"severity-{item['severity']}"
        
        # Use the image URL that's already set in report_data (photos are already copied)
        img_url = item.get('image_url', f"photos/photo_{i:03d}.jpg")
        
        html_content += f"""
    <div class="item">
        <div class="item-header">
            <h3>Photo {i}: {item['location'] or 'General Area'}</h3>
            <span class="severity-badge {severity_class}">{item['severity']}</span>
        </div>
        <img src="{img_url}" alt="Photo {i}" class="item-image">
        <div class="item-content">
"""
        
        if item['observations']:
            html_content += """
            <div class="section">
                <h4>Observations</h4>
                <ul>
"""
            for obs in item['observations']:
                html_content += f"                    <li>{obs}</li>\n"
            html_content += """                </ul>
            </div>
"""
        
        if item['potential_issues']:
            html_content += """
            <div class="section">
                <h4>Potential Issues</h4>
                <ul>
"""
            for issue in item['potential_issues']:
                html_content += f"                    <li>{issue}</li>\n"
            html_content += """                </ul>
            </div>
"""
        
        if item['recommendations']:
            html_content += """
            <div class="section">
                <h4>Recommendations</h4>
                <ul>
"""
            for rec in item['recommendations']:
                html_content += f"                    <li>{rec}</li>\n"
            html_content += """                </ul>
            </div>
"""
        
        html_content += """        </div>
    </div>
"""
    
    html_content += """
        <div class="footer">
            <div class="footer-logo">CheckMyRental</div>
            <div class="footer-text">Professional Property Inspection Services</div>
            <div class="footer-text" style="margin-top: 10px;">© 2025 Altam CO LLC. All rights reserved.</div>
        </div>
    </div>
</body>
</html>
"""
    
    html_path.write_text(html_content, encoding='utf-8')
    return html_path

def generate_pdf(address: str, images: List[Path], out_pdf: Path, vision_results: Optional[Dict[str, str]] = None, client_name: str = "") -> None:
    """Generate executive-quality PDF report with sophisticated design"""
    from PIL import Image as PILImage, ImageOps, ImageDraw, ImageFilter
    from reportlab.lib.colors import HexColor, Color
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    
    c = Canvas(str(out_pdf), pagesize=letter)
    width, height = letter
    
    # Executive color palette - sophisticated and professional
    primary_color = HexColor('#1a1a2e')      # Deep navy
    accent_color = HexColor('#e74c3c')       # Signature red
    text_primary = HexColor('#2c3e50')       # Dark blue-gray
    text_secondary = HexColor('#7f8c8d')     # Medium gray
    text_light = HexColor('#95a5a6')         # Light gray
    bg_light = HexColor('#f8f9fa')           # Very light gray
    bg_accent = HexColor('#ecf0f1')          # Light accent
    gold_accent = HexColor('#d4af37')        # Executive gold
    
    # EXECUTIVE COVER PAGE DESIGN
    
    # Subtle gradient background effect using overlapping rectangles
    c.setFillColor(HexColor('#ffffff'))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    
    # Top section with subtle gray background
    c.setFillColor(bg_accent)
    c.rect(0, height - 180, width, 180, fill=1, stroke=0)
    
    # Thin accent line at top
    c.setFillColor(accent_color)
    c.rect(0, height - 3, width, 3, fill=1, stroke=0)
    
    # Logo symbol only (centered at top) - larger and more prominent
    logo_x = width / 2 - 30
    logo_y = height - 120
    
    # Draw sophisticated logo mark
    # Outer circle for elegance
    c.setStrokeColor(primary_color)
    c.setLineWidth(2)
    c.circle(logo_x + 30, logo_y + 30, 35, fill=0, stroke=1)
    
    # House shape (rotated square) - refined design
    c.saveState()
    c.translate(logo_x + 30, logo_y + 30)
    c.rotate(45)
    c.setFillColor(primary_color)
    c.rect(-18, -18, 36, 36, fill=1, stroke=0)
    c.restoreState()
    
    # Window grid - more sophisticated
    c.setFillColor(HexColor('#ffffff'))
    window_size = 7
    c.rect(logo_x + 23, logo_y + 23, window_size, window_size, fill=1)
    c.rect(logo_x + 31, logo_y + 23, window_size, window_size, fill=1)
    c.rect(logo_x + 23, logo_y + 31, window_size, window_size, fill=1)
    c.rect(logo_x + 31, logo_y + 31, window_size, window_size, fill=1)
    
    # Checkmark badge - positioned elegantly
    c.setFillColor(accent_color)
    c.circle(logo_x + 45, logo_y + 15, 10, fill=1, stroke=0)
    c.setStrokeColor(HexColor('#ffffff'))
    c.setLineWidth(3)
    c.line(logo_x + 40, logo_y + 15, logo_x + 43, logo_y + 12)
    c.line(logo_x + 43, logo_y + 12, logo_x + 50, logo_y + 19)
    
    # MAIN TITLE - Centered and elegant
    c.setFont("Helvetica", 14)
    c.setFillColor(text_secondary)
    title_text = "PROPERTY INSPECTION"
    title_width = c.stringWidth(title_text, "Helvetica", 14)
    c.drawString((width - title_width) / 2, height - 200, title_text)
    
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(text_primary)
    report_text = "REPORT"
    report_width = c.stringWidth(report_text, "Helvetica-Bold", 32)
    c.drawString((width - report_width) / 2, height - 235, report_text)
    
    # Decorative line under title
    line_width = 100
    c.setStrokeColor(gold_accent)
    c.setLineWidth(2)
    c.line((width - line_width) / 2, height - 250, (width + line_width) / 2, height - 250)
    
    # Property Information Card - elevated design
    card_y = height - 480
    card_height = 180
    card_margin = 60
    
    # Card shadow effect
    c.setFillColor(HexColor('#e8e8e8'))
    c.roundRect(card_margin + 2, card_y - 2, width - (2 * card_margin), card_height, 8, fill=1, stroke=0)
    
    # Main card
    c.setFillColor(HexColor('#ffffff'))
    c.setStrokeColor(HexColor('#e0e0e0'))
    c.setLineWidth(1)
    c.roundRect(card_margin, card_y, width - (2 * card_margin), card_height, 8, fill=1, stroke=1)
    
    # Property Address Section
    info_x = card_margin + 30
    info_y = card_y + card_height - 40
    
    c.setFont("Helvetica", 10)
    c.setFillColor(text_light)
    c.drawString(info_x, info_y, "PROPERTY ADDRESS")
    
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(text_primary)
    c.drawString(info_x, info_y - 25, address[:50])  # Truncate if too long
    if len(address) > 50:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(info_x, info_y - 45, address[50:100])
    
    # Vertical separator
    c.setStrokeColor(HexColor('#e0e0e0'))
    c.setLineWidth(1)
    separator_x = width / 2
    c.line(separator_x, card_y + 20, separator_x, card_y + card_height - 20)
    
    # Right side information
    right_x = separator_x + 30
    
    # Date
    c.setFont("Helvetica", 10)
    c.setFillColor(text_light)
    c.drawString(right_x, info_y, "INSPECTION DATE")
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(text_primary)
    c.drawString(right_x, info_y - 22, datetime.now().strftime('%B %d, %Y'))
    
    # Client name if provided
    if client_name:
        c.setFont("Helvetica", 10)
        c.setFillColor(text_light)
        c.drawString(right_x, info_y - 50, "PREPARED FOR")
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(text_primary)
        c.drawString(right_x, info_y - 72, client_name[:30])
    
    # Statistics box at bottom
    stats_y = card_y - 60
    c.setFillColor(bg_accent)
    c.roundRect(card_margin, stats_y, width - (2 * card_margin), 45, 8, fill=1, stroke=0)
    
    # Photo count with icon
    c.setFont("Helvetica", 11)
    c.setFillColor(text_secondary)
    stats_text = f"This report contains {len(images)} detailed inspection photographs with professional analysis"
    stats_width = c.stringWidth(stats_text, "Helvetica", 11)
    c.drawString((width - stats_width) / 2, stats_y + 18, stats_text)
    
    # Professional footer - minimal and elegant
    c.setFont("Helvetica", 8)
    c.setFillColor(text_light)
    c.drawString(card_margin, 40, "Confidential Property Inspection Report")
    c.drawRightString(width - card_margin, 40, f"Generated {datetime.now().strftime('%Y-%m-%d')}")
    
    c.showPage()
    
    # Add each image with analysis
    for i, img_path in enumerate(images, 1):
        try:
            # Compress image for smaller PDF size
            with PILImage.open(img_path) as pil_img:
                # IMPORTANT: Auto-rotate image based on EXIF orientation
                # This ensures the image appears upright in the PDF
                try:
                    # Use ImageOps.exif_transpose to automatically handle EXIF orientation
                    pil_img = ImageOps.exif_transpose(pil_img)
                except Exception:
                    # If EXIF handling fails, try manual rotation based on orientation tag
                    try:
                        exif = pil_img._getexif()
                        if exif:
                            orientation = exif.get(0x0112)  # Orientation tag
                            if orientation:
                                rotations = {
                                    3: PILImage.Transpose.ROTATE_180,
                                    6: PILImage.Transpose.ROTATE_270,
                                    8: PILImage.Transpose.ROTATE_90
                                }
                                if orientation in rotations:
                                    pil_img = pil_img.transpose(rotations[orientation])
                    except (AttributeError, KeyError):
                        pass  # No EXIF data or orientation info
                
                # Convert to RGB if necessary (after rotation)
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                
                # Resize if too large (max 1200px on longest side for print)
                max_dim = max(pil_img.size)
                if max_dim > 1200:
                    scale = 1200 / max_dim
                    new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
                    pil_img = pil_img.resize(new_size, PILImage.Resampling.LANCZOS)
                
                # Save to temporary compressed JPEG with corrected orientation
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    pil_img.save(tmp.name, 'JPEG', quality=85, optimize=True)
                    compressed_path = tmp.name
            
            # EXECUTIVE PAGE HEADER - Minimal and sophisticated
            # Thin top border
            c.setStrokeColor(accent_color)
            c.setLineWidth(2)
            c.line(0, height - 30, width, height - 30)
            
            # Small logo mark (left side)
            logo_size = 12
            c.saveState()
            c.translate(35, height - 18)
            c.rotate(45)
            c.setFillColor(primary_color)
            c.rect(-logo_size/2, -logo_size/2, logo_size, logo_size, fill=1, stroke=0)
            c.restoreState()
            
            # Mini window
            c.setFillColor(HexColor('#ffffff'))
            c.rect(32, height - 21, 3, 3, fill=1)
            c.rect(36, height - 21, 3, 3, fill=1)
            
            # Check badge
            c.setFillColor(accent_color)
            c.circle(42, height - 22, 3, fill=1, stroke=0)
            
            # Page information - clean typography
            c.setFont("Helvetica", 9)
            c.setFillColor(text_secondary)
            c.drawString(55, height - 22, f"Photo {i} of {len(images)}")
            
            # Property address (right aligned)
            c.setFont("Helvetica", 8)
            c.drawRightString(width - 35, height - 22, address[:45])
            
            # Add compressed image
            img = ImageReader(compressed_path)
            img_width, img_height = img.getSize()
            
            # Calculate scaling to fit on page with room for text
            max_width = width - 120  # More margin for executive look
            max_height = 380  # Leave room for analysis text
            scale = min(max_width / img_width, max_height / img_height, 1.0)
            
            draw_width = img_width * scale
            draw_height = img_height * scale
            
            # Center image horizontally
            x = (width - draw_width) / 2
            y = height - draw_height - 50
            
            # Image frame with shadow effect
            c.setFillColor(HexColor('#e0e0e0'))
            c.rect(x - 2, y - 2, draw_width + 4, draw_height + 4, fill=1, stroke=0)
            
            # White border around image
            c.setFillColor(HexColor('#ffffff'))
            c.setStrokeColor(HexColor('#d0d0d0'))
            c.setLineWidth(1)
            c.rect(x - 5, y - 5, draw_width + 10, draw_height + 10, fill=1, stroke=1)
            
            # Draw image
            c.drawImage(img, x, y, draw_width, draw_height, preserveAspectRatio=True)
            
            # Clean up temp file
            os.unlink(compressed_path)
            
            # Add analysis text below image
            if vision_results:
                # Try to find the analysis with different path formats
                analysis = None
                img_path_str = str(img_path)
                
                # Check exact match first
                if img_path_str in vision_results:
                    analysis = vision_results[img_path_str]
                else:
                    # Try matching by filename
                    for key, value in vision_results.items():
                        if Path(key).name == img_path.name:
                            analysis = value
                            break
                
                if analysis:
                    # Starting Y position for text
                    text_y = y - 20
                else:
                    # No analysis found - add a note
                    c.setFont("Helvetica-Oblique", 9)
                    c.setFillColor(text_secondary)
                    c.drawString(50, y - 20, "Analysis pending for this image")
                    analysis = None
                
                if analysis:
                    # Write analysis as simple text
                    c.setFont("Helvetica", 10)
                    lines = analysis.split('\n')
                    for line in lines:
                        if text_y < 60:  # Start new page if running out of room
                            c.setFont("Helvetica", 8)
                            c.drawString(width - 100, 30, f"Page {c.getPageNumber()}")
                            c.showPage()
                            c.setFont("Helvetica-Bold", 12)
                            c.drawString(50, height - 40, f"Photo {i} (continued)")
                            text_y = height - 60
                            c.setFont("Helvetica", 10)
                        
                        # Handle section headers with color coding (updated for new format)
                        line_stripped = line.strip()
                        if line_stripped.endswith(':') and any(header in line_stripped for header in 
                            ['Location:', 'What I See:', 'Issues to Address:', 'Recommended Action:', 
                             'Observations:', 'Potential Issues:', 'Recommendations:']):
                            if 'Issues' in line_stripped:
                                c.setFillColor(accent_color)
                            else:
                                c.setFillColor(primary_color)
                            c.setFont("Helvetica-Bold", 11)
                            c.drawString(50, text_y, line_stripped)
                            c.setFillColor(HexColor('#333333'))
                            c.setFont("Helvetica", 10)
                            text_y -= 15
                        elif line.strip().startswith('-'):
                            # Wrap long lines
                            text = line.strip()
                            if len(text) > 90:
                                words = text.split()
                                current_line = ""
                                for word in words:
                                    test_line = current_line + " " + word if current_line else word
                                    if len(test_line) > 90:
                                        c.drawString(60, text_y, current_line)
                                        text_y -= 12
                                        current_line = word
                                    else:
                                        current_line = test_line
                                if current_line:
                                    c.drawString(60, text_y, current_line)
                                    text_y -= 12
                            else:
                                c.drawString(60, text_y, text)
                                text_y -= 12
                        elif line.strip():
                            c.drawString(50, text_y, line.strip())
                            text_y -= 12
            
            # Page number
            c.setFont("Helvetica", 8)
            c.drawString(width / 2 - 20, 30, f"Page {c.getPageNumber()}")
            
            c.showPage()
            
        except Exception as e:
            print(f"Error adding {img_path.name} to PDF: {e}")
            continue
    
    c.save()
    print(f"PDF saved to: {out_pdf}")

def build_reports(source_path: Path, client_name: str, property_address: str, gallery_name: str = None) -> Dict[str, Any]:
    """
    Main function to build inspection reports from source (ZIP or directory)
    Returns artifacts dictionary with paths to generated files
    """
    try:
        print(f"\n{'='*60}")
        print(f"Building report for: {property_address}")
        print(f"Client: {client_name}")
        if gallery_name:
            # Clean gallery name for console output - remove emojis
            safe_gallery = ''.join(c if ord(c) < 128 else '' for c in str(gallery_name))
            if safe_gallery.strip():
                print(f"Gallery: {safe_gallery.strip()}")
        print(f"{'='*60}\n")
    except UnicodeEncodeError as e:
        # Fallback for any encoding issues
        print("\n" + "="*60)
        print("Building report...")
        print("="*60 + "\n")
    
    # Extract if ZIP, otherwise use as directory
    if source_path.suffix.lower() == '.zip':
        photos_dir = extract_zip(source_path)
        cleanup_needed = True
    else:
        photos_dir = source_path
        cleanup_needed = False
    
    try:
        # Collect and analyze images
        images = collect_images(photos_dir)
        if not images:
            raise ValueError(f"No images found in {photos_dir}")
        
        print(f"Found {len(images)} images to process")
        
        # Analyze images with vision AI
        vision_results = analyze_images(images)
        
        # Generate report ID and create descriptive directory name
        report_id = secrets.token_hex(16)
        
        # Create descriptive directory name from ZIP filename or property address
        if source_path.suffix.lower() == '.zip':
            # Use ZIP filename (without extension) as base
            dir_name = source_path.stem
        else:
            # Use sanitized property address for directories
            dir_name = property_address.replace(' ', '_').replace(',', '').replace('.', '')
            dir_name = ''.join(c if c.isalnum() or c in '_-' else '_' for c in dir_name)
        
        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        full_dir_name = f"{dir_name}_{timestamp}"
        
        print(f"\nREPORT_ID={report_id}")
        print(f"OUTPUT_DIR={full_dir_name}")
        
        # Create output directory with descriptive name and organized subfolders
        # If gallery name is provided, organize under gallery folder
        if gallery_name:
            # Sanitize gallery name for filesystem - remove emojis and special chars
            # First remove any emoji/unicode characters
            clean_gallery = ''.join(c for c in gallery_name if ord(c) < 128)
            # Then sanitize for filesystem
            safe_gallery = ''.join(c if c.isalnum() or c in '_- ' else '_' for c in clean_gallery).strip()
            # Remove any duplicate underscores and clean up
            safe_gallery = '_'.join(part for part in safe_gallery.split('_') if part)
            report_dir = OUTPUTS_DIR / safe_gallery / full_dir_name
        else:
            report_dir = OUTPUTS_DIR / full_dir_name
        
        # Create organized subfolder structure
        web_dir = ensure_dir(report_dir / 'web')
        # Remove redundant photos_dir - we'll only use web/photos
        analysis_dir = ensure_dir(report_dir / 'analysis')
        pdf_dir = ensure_dir(report_dir / 'pdf')
        
        # Prepare report data
        report_data = {
            'report_id': report_id,
            'client_name': client_name,
            'property_address': property_address,
            'inspection_date': datetime.now().strftime('%Y-%m-%d'),
            'items': []
        }
        
        # Copy photos ONLY to web/photos folder (single location)
        web_photos_dir = ensure_dir(web_dir / 'photos')
        for i, img_path in enumerate(images, 1):
            # Copy to web/photos for both web serving and archival
            web_photo_path = web_photos_dir / f"photo_{i:03d}{img_path.suffix}"
            shutil.copy2(img_path, web_photo_path)
        
        # Save individual analysis files
        for i, img_path in enumerate(images, 1):
            analysis_text = vision_results.get(str(img_path), "")
            if analysis_text:
                analysis_file = analysis_dir / f"{i:03d}_{img_path.stem}_analysis.txt"
                analysis_file.write_text(analysis_text, encoding='utf-8')
        
        # Process each image and analysis for report
        for i, img_path in enumerate(images, 1):
            analysis_text = vision_results.get(str(img_path), "")
            sections = parse_analysis(analysis_text)
            severity = categorize_issue(sections)
            
            # Create relative path for web access
            web_image_path = f"photos/photo_{i:03d}{img_path.suffix}"
            
            report_data['items'].append({
                'image_path': str(img_path),
                'image_url': web_image_path,  # Relative URL for web access
                'image_filename': img_path.name,
                'location': sections['location'],
                'observations': sections['observations'],
                'potential_issues': sections['potential_issues'],
                'recommendations': sections['recommendations'],
                'severity': severity
            })
        
        # Save enhanced JSON report data
        json_path = save_report_json(report_data, web_dir)
        print(f"JSON data saved: {json_path}")
        
        # Copy gallery template to web folder (portal uses this to display reports)
        template_src = Path('static/gallery-template.html')
        if template_src.exists():
            html_path = web_dir / 'index.html'
            shutil.copy2(template_src, html_path)
            print(f"Gallery template copied for portal display: {html_path}")
        else:
            # Template is required for portal display
            print(f"Warning: Gallery template not found at {template_src}")
            html_path = web_dir / 'index.html'
        
        # Generate PDF report in pdf subfolder
        pdf_filename = f"{property_address.replace(' ', '_').replace(',', '')}_inspection.pdf"
        pdf_path = pdf_dir / pdf_filename
        try:
            generate_pdf(property_address, images, pdf_path, vision_results, client_name)
            print(f"PDF report: {pdf_path}")
        except Exception as e:
            print(f"ERROR generating PDF: {e}")
            import traceback
            traceback.print_exc()
            print(f"Failed to generate PDF at: {pdf_path}")
        
        # Also save a copy of JSON in main directory for reference
        main_json_path = report_dir / 'report_data.json'
        main_json_path.write_text(json.dumps(report_data, indent=2), encoding='utf-8')
        
        # Create summary file
        summary_path = report_dir / 'summary.txt'
        summary_content = f"""Property Inspection Report
========================
Property: {property_address}
Client: {client_name}
Date: {datetime.now().strftime('%B %d, %Y')}
Report ID: {report_id}

Total Photos: {len(images)}
Issues Found: {sum(1 for item in report_data['items'] if item['potential_issues'])}

Output Directory Structure:
- /web/photos/ - Inspection photos for portal display
- /web/report.json - Structured report data for portal
- /web/index.html - Gallery template for portal viewer
- /analysis/ - Individual AI analysis text files  
- /pdf/ - PDF report for download/printing
- report_data.json - Backup of structured data
- summary.txt - This summary file
"""
        summary_path.write_text(summary_content, encoding='utf-8')
        
        return {
            'report_id': report_id,
            'web_dir': str(web_dir),
            'pdf_path': str(pdf_path),
            'html_path': str(html_path) if 'html_path' in locals() else str(web_dir / 'index.html'),
            'json_path': str(json_path) if 'json_path' in locals() else str(web_dir / 'report.json'),
            'client_name': client_name,
            'property_address': property_address
        }
        
    finally:
        # Clean up temporary extraction directory
        if cleanup_needed and photos_dir.exists():
            try:
                shutil.rmtree(photos_dir)
            except Exception as e:
                print(f"Warning: Could not clean up temp directory: {e}")

def upload_to_backend(artifacts: Dict[str, Any], owner_id: str, property_address: str):
    """
    Upload report data to FastAPI backend for dashboard display
    """
    import requests

    try:
        # Prepare report data for API
        report_data = {
            "report_id": artifacts['report_id'],
            "owner_id": owner_id,
            "property_address": property_address,
            "date": datetime.now().isoformat(),
            "inspector": "CheckMyRental Inspector",
            "status": "completed",
            "web_dir": artifacts['web_dir'],
            "pdf_path": artifacts['pdf_path']
        }

        # Read the JSON report to get issue counts
        json_path = Path(artifacts['web_dir']) / 'report.json'
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                report_json = json.load(f)

                # Count issues by severity
                critical_count = 0
                important_count = 0

                for item in report_json.get('items', []):
                    severity = item.get('severity', '').lower()
                    if severity == 'critical':
                        critical_count += 1
                    elif severity == 'important':
                        important_count += 1

                report_data['critical_issues'] = critical_count
                report_data['important_issues'] = important_count

        # Send to backend API
        api_url = "http://localhost:5000/api/reports/save"
        response = requests.post(api_url, json=report_data, timeout=10)

        if response.status_code == 200:
            print(f"✅ Report uploaded to owner dashboard: {owner_id}")
        else:
            print(f"⚠️ Failed to upload report to dashboard: {response.status_code}")
            print(f"   Response: {response.text}")

    except Exception as e:
        print(f"⚠️ Error uploading to backend: {e}")
        # Don't fail the whole process if upload fails
        pass

def register_with_portal(artifacts: Dict[str, Any], client_name: str, client_email: str,
                        property_address: str, owner_id: str = None, ttl_hours: int = 720) -> Dict[str, Any]:
    """
    Register report with portal and create access token
    """
    db_init()
    conn = db_connect()

    try:
        # Create or get client and property
        # If owner_id is provided, use it as the client name for owner-specific galleries
        effective_client_name = owner_id if owner_id else client_name
        client_id = db_upsert_client(conn, effective_client_name, client_email)
        property_id = db_upsert_property(conn, client_id, property_address)

        # Insert report
        report_id = db_insert_report(
            conn,
            artifacts['report_id'],
            property_id,
            artifacts['web_dir'],
            artifacts['pdf_path']
        )

        # Create view token
        token = db_create_token(conn, kind='view', ttl_hours=ttl_hours, report_id=report_id)

        # Build share URL
        share_url = f"{PORTAL_EXTERNAL_BASE_URL}/r/{token}"

        # Upload report to FastAPI backend if owner_id is provided
        if owner_id:
            upload_to_backend(artifacts, owner_id, property_address)

        print(f"\n{'='*60}")
        print(f"Report registered successfully!")
        print(f"Share URL: {share_url}")
        print(f"Token expires: {(datetime.utcnow() + timedelta(hours=ttl_hours)).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"{'='*60}\n")

        return {
            'report_id': report_id,
            'token': token,
            'share_url': share_url,
            'expires_at': (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat() + 'Z'
        }
    finally:
        conn.close()

# ============== CLI Interface ==============

def main():
    """Command-line interface for running reports"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate inspection report from photos')
    parser.add_argument('--zip', type=str, help='Path to ZIP file containing photos')
    parser.add_argument('--dir', type=str, help='Path to directory containing photos')
    parser.add_argument('--client', type=str, default='Property Owner', help='Client name')
    parser.add_argument('--email', type=str, default='', help='Client email')
    parser.add_argument('--property', type=str, default='Property Address', help='Property address')
    parser.add_argument('--owner-id', type=str, default=None, help='Owner ID for routing to specific dashboard')
    parser.add_argument('--gallery', type=str, default=None, help='Gallery name for organizing reports')
    parser.add_argument('--register', action='store_true', help='Register with portal and generate share link')
    
    args = parser.parse_args()
    
    # Determine source
    if args.zip:
        source = Path(args.zip)
        if not source.exists():
            print(f"Error: ZIP file not found: {source}")
            sys.exit(1)
    elif args.dir:
        source = Path(args.dir)
        if not source.exists():
            print(f"Error: Directory not found: {source}")
            sys.exit(1)
    else:
        print("Error: Please specify --zip or --dir")
        parser.print_help()
        sys.exit(1)
    
    try:
        # Generate reports
        gallery = getattr(args, 'gallery', None)
        artifacts = build_reports(source, args.client, args.property, gallery)
        
        # Register with portal if requested
        if args.register:
            owner_id = getattr(args, 'owner_id', None)
            register_with_portal(artifacts, args.client, args.email, args.property, owner_id)
        
        print("\nReport generation complete!")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()