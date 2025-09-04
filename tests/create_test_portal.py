"""
Create comprehensive test data for the owner portal demonstration
"""
import json
import secrets
from datetime import datetime, timedelta
import random

# Generate a test token
test_token = secrets.token_urlsafe(32)

# Create comprehensive mock dashboard data
dashboard_data = {
    "owner": {
        "name": "Sarah Johnson",
        "email": "sarah.johnson@example.com",
        "company": "Premier Property Management"
    },
    "totals": {
        "properties": 12,
        "reports": 47,
        "critical": 23,
        "important": 89,
        "photos": 1847
    },
    "properties": []
}

# Property data with realistic addresses
properties_data = [
    {"label": "904 Marshal St", "address": "904 Marshal St, Seattle, WA 98109", "type": "Single Family", "units": 1},
    {"label": "4666 12th Ave S", "address": "4666 12th Ave S, Seattle, WA 98108", "type": "Duplex", "units": 2},
    {"label": "13699 99th Ave Unit 3", "address": "13699 99th Ave Unit 3, Kirkland, WA 98034", "type": "Condo", "units": 1},
    {"label": "2355 Pine St", "address": "2355 Pine St, Seattle, WA 98122", "type": "Single Family", "units": 1},
    {"label": "8901 Rainier Ave S", "address": "8901 Rainier Ave S, Seattle, WA 98118", "type": "Apartment Complex", "units": 8},
    {"label": "456 Broadway E", "address": "456 Broadway E #204, Seattle, WA 98102", "type": "Condo", "units": 1},
    {"label": "7823 Lake City Way", "address": "7823 Lake City Way NE, Seattle, WA 98115", "type": "Commercial", "units": 4},
    {"label": "1200 Alaskan Way", "address": "1200 Alaskan Way #301, Seattle, WA 98101", "type": "Waterfront Condo", "units": 1},
    {"label": "5555 University Way", "address": "5555 University Way NE, Seattle, WA 98105", "type": "Student Housing", "units": 6},
    {"label": "3421 Wallingford Ave", "address": "3421 Wallingford Ave N, Seattle, WA 98103", "type": "Townhouse", "units": 3},
    {"label": "9876 Beacon Ave", "address": "9876 Beacon Ave S, Seattle, WA 98108", "type": "Single Family", "units": 1},
    {"label": "234 Mercer St", "address": "234 Mercer St #502, Seattle, WA 98109", "type": "High-Rise Condo", "units": 1}
]

# Generate property records with varying report counts
property_details = {}
for i, prop in enumerate(properties_data):
    prop_id = f"prop_{i+1}"
    
    # Generate 1-6 reports per property
    num_reports = random.randint(1, 6)
    reports = []
    
    for j in range(num_reports):
        # Create reports going back up to 180 days
        days_ago = random.randint(0, 180) if j > 0 else random.randint(0, 30)
        report_date = datetime.now() - timedelta(days=days_ago)
        
        reports.append({
            "report_id": secrets.token_hex(16),
            "created_at": report_date.isoformat() + "Z",
            "inspection_type": random.choice(["Quarterly", "Move-in", "Move-out", "Annual", "Maintenance"]),
            "photos": random.randint(15, 85),
            "critical": random.randint(0, 8),
            "important": random.randint(2, 15),
            "minor": random.randint(5, 25),
            "inspector": random.choice(["John Smith", "Maria Garcia", "David Lee", "Emma Wilson"]),
            "duration_minutes": random.randint(45, 120),
            "weather": random.choice(["Clear", "Partly Cloudy", "Overcast", "Light Rain"]),
            "access_notes": random.choice([
                "Full access granted",
                "Tenant present during inspection", 
                "Used lockbox for entry",
                "Property manager on site"
            ])
        })
    
    # Sort reports by date (newest first)
    reports.sort(key=lambda x: x["created_at"], reverse=True)
    
    # Add to dashboard properties list
    dashboard_data["properties"].append({
        "id": prop_id,
        "label": prop["label"],
        "address": prop["address"],
        "type": prop["type"],
        "units": prop["units"],
        "report_count": len(reports),
        "latest_report_at": reports[0]["created_at"],
        "status": random.choice(["Active", "Active", "Active", "Pending"]),
        "next_inspection": (datetime.now() + timedelta(days=random.randint(7, 90))).isoformat() + "Z"
    })
    
    # Store detailed property info
    property_details[prop_id] = {
        "property": {
            "id": prop_id,
            "label": prop["label"],
            "address": prop["address"],
            "type": prop["type"],
            "units": prop["units"],
            "year_built": random.randint(1960, 2020),
            "square_feet": random.randint(800, 4500),
            "bedrooms": random.randint(1, 5),
            "bathrooms": random.choice([1, 1.5, 2, 2.5, 3, 3.5]),
            "parking": random.choice(["Garage", "Driveway", "Street", "Covered", "None"]),
            "heating": random.choice(["Forced Air", "Baseboard", "Radiant", "Heat Pump"]),
            "cooling": random.choice(["Central AC", "Window Units", "None", "Heat Pump"]),
            "notes": random.choice([
                "Well-maintained property with recent updates",
                "Original hardwood floors throughout",
                "Recently remodeled kitchen and bathrooms",
                "Needs some exterior maintenance",
                "Great tenant history, minimal issues"
            ])
        },
        "reports": reports,
        "maintenance_history": [
            {
                "date": (datetime.now() - timedelta(days=random.randint(30, 365))).isoformat() + "Z",
                "type": random.choice(["HVAC Service", "Plumbing Repair", "Roof Maintenance", "Appliance Replacement"]),
                "cost": random.randint(150, 2500),
                "vendor": random.choice(["ABC Maintenance", "Pro Services Inc", "Quick Fix LLC"])
            } for _ in range(random.randint(0, 5))
        ]
    }

# Sort properties by latest report
dashboard_data["properties"].sort(key=lambda x: x["latest_report_at"], reverse=True)

# Create mock portal data file
mock_data = {
    "token": test_token,
    "dashboard_data": dashboard_data,
    "property_details": property_details,
    "generated_at": datetime.now().isoformat() + "Z"
}

# Save the mock data
with open("mock_portal_data.json", "w") as f:
    json.dump(mock_data, f, indent=2)

print("\n" + "="*60)
print("MOCK PORTAL DATA CREATED")
print("="*60)
print(f"\nToken: {test_token}")
print(f"Properties: {len(dashboard_data['properties'])}")
print(f"Total Reports: {sum(p['report_count'] for p in dashboard_data['properties'])}")
print("\nProperty Types:")
for prop in dashboard_data['properties'][:5]:
    print(f"  - {prop['label']}: {prop['type']} ({prop['report_count']} reports)")
print("\n" + "="*60)