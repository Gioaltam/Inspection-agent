#!/usr/bin/env python3
"""
Ensures all inspection reports use the standardized gallery_template.html
This script:
1. Removes old individual HTML files 
2. Ensures all reports are viewed through the template
"""

import os
import json
from pathlib import Path

def ensure_template_usage():
    """Ensure all reports use the gallery template"""
    
    output_dir = Path("output")
    template_path = output_dir / "gallery_template.html"
    
    # Check template exists
    if not template_path.exists():
        print("❌ Error: gallery_template.html not found in output directory")
        return False
    
    # Find all JSON report files
    json_files = list(output_dir.glob("*.json"))
    json_files = [f for f in json_files if f.name != "reports_index.json"]
    
    print(f"Found {len(json_files)} report JSON files")
    
    # Remove any old individual HTML files (except the template)
    html_files = list(output_dir.glob("*.html"))
    for html_file in html_files:
        if html_file.name != "gallery_template.html":
            print(f"🗑️  Removing old HTML file: {html_file.name}")
            html_file.unlink()
    
    # Display how to access each report
    print("\n" + "="*60)
    print("✅ All reports now use the standardized template!")
    print("="*60)
    print("\nAccess your reports using:")
    print(f"http://localhost:8000/gallery_template.html?id=[report-id]\n")
    
    for json_file in json_files:
        # Extract report ID from filename
        report_id = json_file.stem
        
        # Try to get address from JSON
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                address = data.get('address', 'Unknown')
                print(f"📍 {address}")
                print(f"   → http://localhost:8000/gallery_template.html?id={report_id}")
        except:
            print(f"📄 {json_file.name}")
            print(f"   → http://localhost:8000/gallery_template.html?id={report_id}")
    
    print("\n💡 Tip: Start a local server with: python -m http.server 8000")
    return True

if __name__ == "__main__":
    ensure_template_usage()