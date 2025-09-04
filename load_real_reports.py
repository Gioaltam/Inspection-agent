#!/usr/bin/env python3
"""
Load real inspection reports from workspace/outputs into the database
"""
import os
import json
import sqlite3
from datetime import datetime
import glob

def load_reports_to_database():
    """Load all reports from workspace/outputs into the database"""
    
    # Connect to database (using the same database as backend)
    db_path = 'backend/inspection_portal.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            portal_token TEXT UNIQUE,
            company_name TEXT,
            contact_name TEXT,
            phone TEXT,
            address TEXT,
            user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            address TEXT,
            label TEXT,
            property_type TEXT,
            details_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            property_id TEXT,
            address TEXT,
            inspection_date TIMESTAMP,
            pdf_path TEXT,
            json_path TEXT,
            photos TEXT,
            pdf_standard_url TEXT,
            pdf_hq_url TEXT,
            pdf_hq_expires_at TIMESTAMP,
            json_url TEXT,
            summary TEXT,
            critical_count INTEGER DEFAULT 0,
            important_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (property_id) REFERENCES properties(id)
        )
    ''')
    
    # Find all report folders in workspace/outputs
    report_folders = glob.glob('workspace/outputs/*')
    
    if not report_folders:
        print("No reports found in workspace/outputs/")
        return
    
    print(f"Found {len(report_folders)} reports to process")
    
    for folder in report_folders:
        folder_name = os.path.basename(folder)
        print(f"\nProcessing: {folder_name}")
        
        # Load report data
        report_json_path = os.path.join(folder, 'report_data.json')
        if not os.path.exists(report_json_path):
            print(f"  [WARNING] No report_data.json found, skipping")
            continue
            
        with open(report_json_path, 'r') as f:
            report_data = json.load(f)
        
        # Parse report data
        client_name = report_data.get('client_name', 'Unknown Client')
        property_address = report_data.get('property_address', folder_name.split('_')[0])
        inspection_date = report_data.get('inspection_date', datetime.now().isoformat())
        report_id = report_data.get('report_id', folder_name)
        
        # Count issues by severity
        critical_count = 0
        important_count = 0
        minor_count = 0
        
        items = report_data.get('items', [])
        for item in items:
            severity = item.get('severity', 'minor').lower()
            if severity == 'critical':
                critical_count += 1
            elif severity == 'important':
                important_count += 1
            else:
                minor_count += 1
        
        # Check if client exists, if not create
        cursor.execute("SELECT id FROM clients WHERE name = ? OR contact_name = ?", 
                      (client_name, client_name))
        client_row = cursor.fetchone()
        
        if not client_row:
            # Create new client with TEST123 token for testing
            client_id = f'client_{report_id[:8]}'
            cursor.execute('''
                INSERT INTO clients (id, name, contact_name, email, portal_token, company_name)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (client_id, client_name, client_name, 
                 f'{client_name.lower().replace(" ", ".")}@example.com',
                 'TEST123', f'{client_name} Properties'))
            print(f"  [OK] Created client: {client_name}")
        else:
            client_id = client_row[0]
            print(f"  [INFO] Using existing client: {client_name}")
        
        # Check if property exists, if not create
        cursor.execute("SELECT id FROM properties WHERE address = ? AND client_id = ?", 
                      (property_address, client_id))
        property_row = cursor.fetchone()
        
        if not property_row:
            property_id = f'prop_{report_id[:8]}'
            cursor.execute('''
                INSERT INTO properties (id, client_id, address, label, property_type)
                VALUES (?, ?, ?, ?, ?)
            ''', (property_id, client_id, property_address, 
                 property_address.split(',')[0], 'residential'))
            print(f"  [OK] Created property: {property_address}")
        else:
            property_id = property_row[0]
            print(f"  [INFO] Using existing property: {property_address}")
        
        # Check if report exists
        cursor.execute("SELECT id FROM reports WHERE id = ?", (report_id,))
        if cursor.fetchone():
            print(f"  [INFO] Report already exists, updating...")
            cursor.execute('''
                UPDATE reports 
                SET critical_count = ?, important_count = ?,
                    json_path = ?, pdf_path = ?
                WHERE id = ?
            ''', (critical_count, important_count,
                  report_json_path, 
                  os.path.join(folder, 'pdf', '*.pdf'),
                  report_id))
        else:
            # Create structured report for interactive viewer
            structured_report = {
                "summary": f"Inspection found {critical_count} critical issues, {important_count} important issues, and {minor_count} minor issues.",
                "sections": []
            }
            
            # Group items by location
            locations = {}
            for item in items:
                location = item.get('location', 'General').strip(' -')
                if location not in locations:
                    locations[location] = []
                locations[location].append(item)
            
            # Create sections from locations
            for location, location_items in locations.items():
                section = {
                    "id": location.lower().replace(' ', '_')[:30],
                    "name": location,
                    "location": location,
                    "issues": []
                }
                
                for item in location_items:
                    issue = {
                        "title": item.get('observations', ['Issue'])[0] if item.get('observations') else 'Inspection Finding',
                        "severity": item.get('severity', 'minor'),
                        "description": '\n'.join(item.get('potential_issues', [])),
                        "recommendations": '\n'.join(item.get('recommendations', [])),
                        "images": [{"url": item.get('image_url', '')}] if item.get('image_url') else []
                    }
                    section["issues"].append(issue)
                
                structured_report["sections"].append(section)
            
            # Save structured report
            structured_json_path = os.path.join(folder, 'structured_report.json')
            with open(structured_json_path, 'w') as f:
                json.dump(structured_report, f, indent=2)
            
            # Find PDF file
            pdf_files = glob.glob(os.path.join(folder, 'pdf', '*.pdf'))
            pdf_path = pdf_files[0] if pdf_files else None
            
            # Insert report
            cursor.execute('''
                INSERT INTO reports (
                    id, property_id, address, inspection_date,
                    json_path, pdf_path, summary, 
                    critical_count, important_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                report_id, property_id, property_address,
                inspection_date, structured_json_path, pdf_path,
                structured_report['summary'],
                critical_count, important_count
            ))
            print(f"  [OK] Created report: {report_id}")
            print(f"     Critical: {critical_count}, Important: {important_count}, Minor: {minor_count}")
    
    conn.commit()
    conn.close()
    
    print("\n[SUCCESS] All reports loaded successfully!")
    print("\n[INSTRUCTIONS] Access Instructions:")
    print("1. Start the backend server: python backend/app/main.py")
    print("2. Open dashboard: http://localhost:8000/static/owner-dashboard.html?token=TEST123")
    print("3. Click on 'All Properties' to see the real inspection data")
    print("4. Click 'View' on any report to see the interactive inspection details")

if __name__ == "__main__":
    load_reports_to_database()