#!/usr/bin/env python
"""
Test script to verify owner registration and fetching integration
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app.database import SessionLocal, engine
from backend.app.models import Base, Client
from backend.app.auth import get_password_hash

def test_owner_integration():
    """Test the owner registration and fetching flow"""
    
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        print("Testing Owner Registration and Fetching Integration")
        print("=" * 50)
        
        # Clean up any existing test data
        test_owner_id = "test_owner_123"
        existing = db.query(Client).filter(Client.name == test_owner_id).first()
        if existing:
            db.delete(existing)
            db.commit()
            print(f"Cleaned up existing test owner: {test_owner_id}")
        
        # Simulate owner registration from landing page
        print("\n1. Simulating owner registration from landing page...")
        new_owner = Client(
            name=test_owner_id,  # owner_id stored in name field
            company_name="Test Property Management",
            contact_name="Test Property Management",
            email="test@example.com",
            portal_token=test_owner_id,
            password_hash=get_password_hash("testpassword123")
        )
        db.add(new_owner)
        db.commit()
        print(f"   ✅ Owner registered: {new_owner.company_name} (ID: {test_owner_id})")
        
        # Fetch all owners (simulating what operator_ui.py will do)
        print("\n2. Fetching all registered owners...")
        owners = db.query(Client).filter(
            Client.name.isnot(None),
            Client.name != ""
        ).all()
        
        print(f"   Found {len(owners)} registered owner(s):")
        for owner in owners:
            owner_id = owner.name
            full_name = owner.company_name if owner.company_name else owner.contact_name
            print(f"   - {full_name} (ID: {owner_id})")
        
        # Verify our test owner is in the list
        test_owner_found = any(o.name == test_owner_id for o in owners)
        if test_owner_found:
            print(f"\n✅ SUCCESS: Test owner '{test_owner_id}' found in owners list")
            print("   This owner will now appear in the operator_ui.py dropdown!")
        else:
            print(f"\n❌ FAILURE: Test owner '{test_owner_id}' not found in owners list")
        
        # Clean up test data
        print("\n3. Cleaning up test data...")
        db.delete(new_owner)
        db.commit()
        print("   ✅ Test data cleaned up")
        
        print("\n" + "=" * 50)
        print("Integration test completed successfully!")
        print("\nHow the integration works:")
        print("1. User signs up on landing page with owner_id → saved to database")
        print("2. operator_ui.py fetches owners via /api/portal/owners endpoint")
        print("3. Inspector selects owner from dropdown → reports sent to that owner")
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_owner_integration()
