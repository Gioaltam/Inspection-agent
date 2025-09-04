"""
Generate a test token for accessing the owner dashboard
"""
import secrets
import json
from datetime import datetime, timedelta

# Generate a test token
test_token = secrets.token_urlsafe(32)

# Create mock dashboard data
dashboard_data = {
    "owner": {
        "name": "Property Owner",
        "email": "owner@example.com"
    },
    "totals": {
        "properties": 3,
        "reports": 5,
        "critical": 8,
        "important": 15
    },
    "properties": [
        {
            "id": "prop1",
            "label": "904 Marshal St",
            "address": "904 Marshal St, Seattle, WA",
            "report_count": 2,
            "latest_report_at": datetime.now().isoformat()
        },
        {
            "id": "prop2",
            "label": "4666 12th Ave S",
            "address": "4666 12th Ave S, Seattle, WA",
            "report_count": 2,
            "latest_report_at": (datetime.now() - timedelta(days=15)).isoformat()
        },
        {
            "id": "prop3",
            "label": "13699 99th Ave Unit 3",
            "address": "13699 99th Ave Unit 3, Seattle, WA",
            "report_count": 1,
            "latest_report_at": (datetime.now() - timedelta(days=30)).isoformat()
        }
    ]
}

# Save the data for the test server
with open("dashboard_data.json", "w") as f:
    json.dump({
        "token": test_token,
        "dashboard_data": dashboard_data,
        "property_details": {
            "prop1": {
                "property": {
                    "id": "prop1",
                    "label": "904 Marshal St",
                    "address": "904 Marshal St, Seattle, WA"
                },
                "reports": [
                    {
                        "report_id": "eab3af62-1ce6-4086-bcf3-8be09e930e61",
                        "created_at": datetime.now().isoformat(),
                        "photos": 60,
                        "critical": 3,
                        "important": 7
                    },
                    {
                        "report_id": "report2",
                        "created_at": (datetime.now() - timedelta(days=30)).isoformat(),
                        "photos": 45,
                        "critical": 5,
                        "important": 8
                    }
                ]
            }
        }
    }, f, indent=2)

print("\n" + "="*60)
print("OWNER DASHBOARD ACCESS")
print("="*60)
print(f"\nToken: {test_token}")
print(f"\nTo access the dashboard locally:")
print(f"1. Start the test server: python simple_portal_server.py")
print(f"2. Open in browser: http://localhost:8003/?token={test_token}")
print("\n" + "="*60)