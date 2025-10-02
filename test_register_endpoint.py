#!/usr/bin/env python
"""Test the register-owner endpoint"""
import requests
import json
import uuid
from backend.app.database import SessionLocal
from backend.app.models import Client

def test_register_owner_endpoint():
    """Test the /api/client/register-owner endpoint"""

    # Generate unique test data
    test_id = f"test_{uuid.uuid4().hex[:8]}"
    test_data = {
        "full_name": "Test Owner",
        "email": f"{test_id}@example.com",
        "owner_id": test_id,
        "password": "TestPassword123!",
        "phone": "555-0123"
    }

    print("Testing /api/portal/register-owner endpoint...")
    print("-" * 50)
    print(f"Test data: {json.dumps(test_data, indent=2)}")

    # Make request to the endpoint (backend runs on port 5000)
    url = "http://localhost:5000/api/portal/register-owner"

    try:
        response = requests.post(url, json=test_data)

        print(f"\nResponse status: {response.status_code}")

        if response.status_code == 200:
            response_data = response.json()
            print(f"Response data: {json.dumps(response_data, indent=2)}")

            # Verify the client was created in the database
            db = SessionLocal()
            try:
                client = db.query(Client).filter(Client.email == test_data["email"]).first()
                if client:
                    print("\n[SUCCESS] Client created in database:")
                    print(f"  - ID: {client.id}")
                    print(f"  - Email: {client.email}")
                    print(f"  - Name: {client.name}")
                    print(f"  - Portal Token: {client.portal_token}")
                    print(f"  - Password hash exists: {bool(client.password_hash)}")

                    # Clean up test data
                    db.delete(client)
                    db.commit()
                    print("\n[INFO] Test client cleaned up")
                else:
                    print("\n[WARNING] Client not found in database after registration")
            finally:
                db.close()

            return True
        else:
            print(f"Error response: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Could not connect to the server. Make sure it's running on http://localhost:5000")
        return False
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False

if __name__ == "__main__":
    success = test_register_owner_endpoint()
    print("\n" + "=" * 50)
    if success:
        print("[PASSED] Registration endpoint test successful!")
    else:
        print("[FAILED] Registration endpoint test failed!")
        print("\nTo test the endpoint manually, ensure the backend is running:")
        print("  python backend/app/main.py")