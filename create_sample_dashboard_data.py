#!/usr/bin/env python3
"""
Create sample dashboard data with multiple properties and inspections
"""
import json
import secrets
from datetime import datetime, timedelta
import random

def generate_sample_data():
    """Generate sample dashboard data with multiple properties"""
    
    # Generate a secure token
    token = secrets.token_urlsafe(32)
    
    # Sample properties with various inspection reports
    properties = [
        {
            "id": "prop_001",
            "label": "Lakefront Mansion",
            "address": "456 Lakeshore Drive, Seattle, WA 98122",
            "type": "single",
            "report_count": 4,
            "latest_report_at": "2025-01-15T10:30:00Z",
            "reports": [
                {
                    "report_id": "rpt_001_q1_2025",
                    "created_at": "2025-01-15T10:30:00Z",
                    "photos": 45,
                    "critical": 2,
                    "important": 5,
                    "minor": 8,
                    "quarter": "Q1 2025"
                },
                {
                    "report_id": "rpt_001_q4_2024",
                    "created_at": "2024-10-12T14:20:00Z",
                    "photos": 38,
                    "critical": 1,
                    "important": 3,
                    "minor": 6,
                    "quarter": "Q4 2024"
                },
                {
                    "report_id": "rpt_001_q3_2024",
                    "created_at": "2024-07-08T09:15:00Z",
                    "photos": 42,
                    "critical": 0,
                    "important": 2,
                    "minor": 5,
                    "quarter": "Q3 2024"
                },
                {
                    "report_id": "rpt_001_q2_2024",
                    "created_at": "2024-04-10T11:45:00Z",
                    "photos": 35,
                    "critical": 1,
                    "important": 4,
                    "minor": 7,
                    "quarter": "Q2 2024"
                }
            ]
        },
        {
            "id": "prop_002",
            "label": "Downtown Condo Unit 204",
            "address": "789 Broadway E #204, Seattle, WA 98102",
            "type": "condo",
            "report_count": 3,
            "latest_report_at": "2025-02-01T15:00:00Z",
            "reports": [
                {
                    "report_id": "rpt_002_q1_2025",
                    "created_at": "2025-02-01T15:00:00Z",
                    "photos": 28,
                    "critical": 3,
                    "important": 7,
                    "minor": 10,
                    "quarter": "Q1 2025"
                },
                {
                    "report_id": "rpt_002_q4_2024",
                    "created_at": "2024-11-05T13:30:00Z",
                    "photos": 25,
                    "critical": 2,
                    "important": 6,
                    "minor": 9,
                    "quarter": "Q4 2024"
                },
                {
                    "report_id": "rpt_002_q3_2024",
                    "created_at": "2024-08-20T10:00:00Z",
                    "photos": 30,
                    "critical": 1,
                    "important": 4,
                    "minor": 8,
                    "quarter": "Q3 2024"
                }
            ]
        },
        {
            "id": "prop_003",
            "label": "Suburban Family Home",
            "address": "2355 Pine Street, Bellevue, WA 98004",
            "type": "single",
            "report_count": 3,
            "latest_report_at": "2025-01-20T09:00:00Z",
            "reports": [
                {
                    "report_id": "rpt_003_q1_2025",
                    "created_at": "2025-01-20T09:00:00Z",
                    "photos": 52,
                    "critical": 0,
                    "important": 2,
                    "minor": 4,
                    "quarter": "Q1 2025"
                },
                {
                    "report_id": "rpt_003_q4_2024",
                    "created_at": "2024-10-18T14:00:00Z",
                    "photos": 48,
                    "critical": 1,
                    "important": 3,
                    "minor": 5,
                    "quarter": "Q4 2024"
                },
                {
                    "report_id": "rpt_003_q3_2024",
                    "created_at": "2024-07-22T10:30:00Z",
                    "photos": 50,
                    "critical": 0,
                    "important": 1,
                    "minor": 3,
                    "quarter": "Q3 2024"
                }
            ]
        },
        {
            "id": "prop_004",
            "label": "Kirkland Duplex",
            "address": "13699 99th Ave NE, Kirkland, WA 98034",
            "type": "duplex",
            "report_count": 2,
            "latest_report_at": "2024-12-15T11:00:00Z",
            "reports": [
                {
                    "report_id": "rpt_004_q4_2024",
                    "created_at": "2024-12-15T11:00:00Z",
                    "photos": 65,
                    "critical": 4,
                    "important": 8,
                    "minor": 12,
                    "quarter": "Q4 2024"
                },
                {
                    "report_id": "rpt_004_q3_2024",
                    "created_at": "2024-09-10T13:00:00Z",
                    "photos": 60,
                    "critical": 3,
                    "important": 7,
                    "minor": 10,
                    "quarter": "Q3 2024"
                }
            ]
        },
        {
            "id": "prop_005",
            "label": "Commercial Plaza",
            "address": "7823 Lake City Way NE, Seattle, WA 98115",
            "type": "commercial",
            "report_count": 2,
            "latest_report_at": "2025-01-05T08:30:00Z",
            "reports": [
                {
                    "report_id": "rpt_005_q1_2025",
                    "created_at": "2025-01-05T08:30:00Z",
                    "photos": 75,
                    "critical": 5,
                    "important": 10,
                    "minor": 15,
                    "quarter": "Q1 2025"
                },
                {
                    "report_id": "rpt_005_q4_2024",
                    "created_at": "2024-10-01T09:00:00Z",
                    "photos": 70,
                    "critical": 4,
                    "important": 9,
                    "minor": 14,
                    "quarter": "Q4 2024"
                }
            ]
        },
        {
            "id": "prop_006",
            "label": "Capitol Hill Townhouse",
            "address": "1234 15th Ave E, Seattle, WA 98112",
            "type": "townhouse",
            "report_count": 3,
            "latest_report_at": "2025-01-25T14:00:00Z",
            "reports": [
                {
                    "report_id": "rpt_006_q1_2025",
                    "created_at": "2025-01-25T14:00:00Z",
                    "photos": 33,
                    "critical": 1,
                    "important": 3,
                    "minor": 6,
                    "quarter": "Q1 2025"
                },
                {
                    "report_id": "rpt_006_q4_2024",
                    "created_at": "2024-10-25T15:30:00Z",
                    "photos": 30,
                    "critical": 0,
                    "important": 2,
                    "minor": 5,
                    "quarter": "Q4 2024"
                },
                {
                    "report_id": "rpt_006_q3_2024",
                    "created_at": "2024-07-15T09:45:00Z",
                    "photos": 35,
                    "critical": 2,
                    "important": 4,
                    "minor": 7,
                    "quarter": "Q3 2024"
                }
            ]
        },
        {
            "id": "prop_007",
            "label": "Waterfront Studio",
            "address": "5678 Alaskan Way #401, Seattle, WA 98101",
            "type": "condo",
            "report_count": 2,
            "latest_report_at": "2025-01-10T10:00:00Z",
            "reports": [
                {
                    "report_id": "rpt_007_q1_2025",
                    "created_at": "2025-01-10T10:00:00Z",
                    "photos": 22,
                    "critical": 0,
                    "important": 1,
                    "minor": 3,
                    "quarter": "Q1 2025"
                },
                {
                    "report_id": "rpt_007_q4_2024",
                    "created_at": "2024-10-08T11:15:00Z",
                    "photos": 20,
                    "critical": 1,
                    "important": 2,
                    "minor": 4,
                    "quarter": "Q4 2024"
                }
            ]
        },
        {
            "id": "prop_008",
            "label": "Queen Anne Victorian",
            "address": "901 Queen Anne Ave N, Seattle, WA 98109",
            "type": "single",
            "report_count": 4,
            "latest_report_at": "2025-02-05T16:00:00Z",
            "reports": [
                {
                    "report_id": "rpt_008_q1_2025",
                    "created_at": "2025-02-05T16:00:00Z",
                    "photos": 58,
                    "critical": 3,
                    "important": 6,
                    "minor": 11,
                    "quarter": "Q1 2025"
                },
                {
                    "report_id": "rpt_008_q4_2024",
                    "created_at": "2024-11-20T14:30:00Z",
                    "photos": 55,
                    "critical": 2,
                    "important": 5,
                    "minor": 9,
                    "quarter": "Q4 2024"
                },
                {
                    "report_id": "rpt_008_q3_2024",
                    "created_at": "2024-08-15T10:00:00Z",
                    "photos": 53,
                    "critical": 1,
                    "important": 4,
                    "minor": 8,
                    "quarter": "Q3 2024"
                },
                {
                    "report_id": "rpt_008_q2_2024",
                    "created_at": "2024-05-10T09:30:00Z",
                    "photos": 50,
                    "critical": 2,
                    "important": 3,
                    "minor": 7,
                    "quarter": "Q2 2024"
                }
            ]
        }
    ]
    
    # Calculate totals
    total_properties = len(properties)
    total_reports = sum(p["report_count"] for p in properties)
    total_critical = sum(sum(r["critical"] for r in p["reports"]) for p in properties)
    total_important = sum(sum(r["important"] for r in p["reports"]) for p in properties)
    
    # Create dashboard data
    dashboard_data = {
        "owner": {
            "name": "Sarah Johnson",
            "email": "sarah.johnson@premierproperties.com",
            "company": "Premier Property Management"
        },
        "totals": {
            "properties": total_properties,
            "reports": total_reports,
            "critical": total_critical,
            "important": total_important
        },
        "properties": properties
    }
    
    # Create property details for API endpoints
    property_details = {}
    for prop in properties:
        property_details[prop["id"]] = {
            "property": {
                "id": prop["id"],
                "label": prop["label"],
                "address": prop["address"],
                "type": prop["type"]
            },
            "reports": prop["reports"]
        }
    
    # Save to file
    data = {
        "token": token,
        "dashboard_data": dashboard_data,
        "property_details": property_details
    }
    
    with open("dashboard_data.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"Sample dashboard data created successfully!")
    print(f"Token: {token}")
    print(f"Total Properties: {total_properties}")
    print(f"Total Reports: {total_reports}")
    print(f"Total Critical Issues: {total_critical}")
    print(f"Total Important Issues: {total_important}")
    
    return token

if __name__ == "__main__":
    token = generate_sample_data()
    print(f"\nAccess URL: http://localhost:8005/?token={token}")