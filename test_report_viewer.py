#!/usr/bin/env python3
"""
Test script for report viewing functionality
"""
import os
import json
from datetime import datetime, timedelta
import sqlite3

def setup_test_data():
    """Create test data for report viewing"""
    
    # Connect to database
    db_path = 'backend/data/portal.db'
    os.makedirs('backend/data', exist_ok=True)
    
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
    
    # Clear existing test data
    cursor.execute("DELETE FROM reports WHERE property_id IN (SELECT id FROM properties WHERE client_id IN (SELECT id FROM clients WHERE portal_token = 'TEST123'))")
    cursor.execute("DELETE FROM properties WHERE client_id IN (SELECT id FROM clients WHERE portal_token = 'TEST123')")
    cursor.execute("DELETE FROM clients WHERE portal_token = 'TEST123'")
    
    # Insert test client
    client_id = 'test-client-001'
    cursor.execute('''
        INSERT INTO clients (id, name, email, portal_token, company_name, contact_name)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (client_id, 'Test Owner', 'test@example.com', 'TEST123', 'Test Company', 'John Test'))
    
    # Insert test property
    property_id = 'test-prop-001'
    cursor.execute('''
        INSERT INTO properties (id, client_id, address, label, property_type)
        VALUES (?, ?, ?, ?, ?)
    ''', (property_id, client_id, '123 Test Street, Miami, FL 33101', 'Test Property', 'single'))
    
    # Create sample report data
    sample_report = {
        "summary": "This property inspection found 2 critical issues and 5 important issues that need attention.",
        "sections": [
            {
                "id": "roof",
                "name": "Roof & Attic",
                "location": "Exterior",
                "issues": [
                    {
                        "title": "Missing Shingles",
                        "severity": "critical",
                        "description": "Several shingles are missing from the northeast section of the roof, exposing the underlayment to weather damage.",
                        "images": []
                    },
                    {
                        "title": "Poor Attic Ventilation",
                        "severity": "important",
                        "description": "Inadequate ventilation in the attic space may lead to moisture buildup and reduced shingle life.",
                        "images": []
                    }
                ]
            },
            {
                "id": "electrical",
                "name": "Electrical System",
                "location": "Interior",
                "issues": [
                    {
                        "title": "Outdated Panel",
                        "severity": "critical",
                        "description": "The electrical panel is a Federal Pacific model known for safety issues. Recommend immediate replacement by licensed electrician.",
                        "images": []
                    },
                    {
                        "title": "Missing GFCI Protection",
                        "severity": "important",
                        "description": "Kitchen and bathroom outlets lack GFCI protection required by current code.",
                        "images": []
                    }
                ]
            },
            {
                "id": "plumbing",
                "name": "Plumbing System",
                "location": "Interior",
                "issues": [
                    {
                        "title": "Slow Drain",
                        "severity": "minor",
                        "description": "Master bathroom sink drains slowly. Recommend professional cleaning.",
                        "images": []
                    }
                ]
            },
            {
                "id": "hvac",
                "name": "HVAC System",
                "location": "Interior/Exterior",
                "issues": [
                    {
                        "title": "AC Unit Age",
                        "severity": "important",
                        "description": "Air conditioning unit is 15 years old and nearing end of typical service life. Budget for replacement.",
                        "images": []
                    },
                    {
                        "title": "Dirty Filter",
                        "severity": "minor",
                        "description": "HVAC filter needs replacement. Recommend monthly inspection and replacement as needed.",
                        "images": []
                    }
                ]
            }
        ]
    }
    
    # Save sample report JSON
    json_path = f'backend/data/reports/test_report.json'
    os.makedirs('backend/data/reports', exist_ok=True)
    with open(json_path, 'w') as f:
        json.dump(sample_report, f, indent=2)
    
    # Insert test reports
    for i in range(3):
        report_id = f'test-report-00{i+1}'
        inspection_date = datetime.now() - timedelta(days=30 * (3-i))
        
        cursor.execute('''
            INSERT INTO reports (
                id, property_id, address, inspection_date,
                json_path, summary, critical_count, important_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            report_id,
            property_id,
            '123 Test Street, Miami, FL 33101',
            inspection_date,
            json_path,
            sample_report['summary'],
            2 if i == 0 else 1,  # Most recent has 2 critical
            5 if i == 0 else 3   # Most recent has 5 important
        ))
    
    conn.commit()
    conn.close()
    
    print("✅ Test data created successfully!")
    print("\nTest Access:")
    print("- Portal Token: TEST123")
    print("- Dashboard URL: http://localhost:8000/static/owner-dashboard.html?token=TEST123")
    print("\nTest Reports Created:")
    print("- 3 inspection reports with varying issue counts")
    print("- Interactive report data with multiple sections")
    print("- Sample issues of different severities")

def verify_api_endpoints():
    """Verify API endpoints are working"""
    import requests
    
    base_url = "http://localhost:8000"
    token = "TEST123"
    
    print("\n🔍 Testing API Endpoints...")
    
    # Test dashboard endpoint
    try:
        response = requests.get(f"{base_url}/api/portal/dashboard?portal_token={token}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Dashboard API: Found {len(data.get('properties', []))} properties")
            
            # Get first report if available
            if data.get('properties') and data['properties'][0].get('reports'):
                report_id = data['properties'][0]['reports'][0]['id']
                
                # Test report details endpoint
                response = requests.get(f"{base_url}/api/portal/report/{report_id}?portal_token={token}")
                if response.status_code == 200:
                    print(f"✅ Report Details API: Successfully loaded report {report_id}")
                else:
                    print(f"❌ Report Details API: Failed with status {response.status_code}")
        else:
            print(f"❌ Dashboard API: Failed with status {response.status_code}")
    except Exception as e:
        print(f"❌ API Test Failed: {e}")
        print("   Make sure the backend server is running: python backend/app/main.py")

if __name__ == "__main__":
    print("🚀 Setting up test data for report viewing...")
    setup_test_data()
    
    # Try to verify API if server is running
    try:
        verify_api_endpoints()
    except:
        print("\n⚠️  Could not test API endpoints. Make sure to start the backend server:")
        print("   python backend/app/main.py")
    
    print("\n✨ Setup complete! You can now test the report viewing functionality.")