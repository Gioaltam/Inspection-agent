#!/usr/bin/env python
"""Test that Client model can now accept password_hash"""
from backend.app.database import SessionLocal
from backend.app.models import Client
from backend.app.security import get_password_hash, verify_password
import uuid

def test_client_with_password():
    """Test creating a client with password_hash"""
    db = SessionLocal()
    try:
        # Generate a test password hash
        test_password = "test_password123"
        password_hash = get_password_hash(test_password)

        # Create a new client with password_hash
        new_client = Client(
            id=str(uuid.uuid4()),
            name="Test Client",
            contact_name="John Doe",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=password_hash
        )

        db.add(new_client)
        db.commit()
        db.refresh(new_client)

        print(f"[SUCCESS] Created Client with ID: {new_client.id}")
        print(f"  Email: {new_client.email}")
        print(f"  Password hash stored: {new_client.password_hash[:20]}...")

        # Test password verification
        is_valid = verify_password(test_password, new_client.password_hash)
        print(f"  Password verification: {'PASSED' if is_valid else 'FAILED'}")

        # Test wrong password
        is_invalid = verify_password("wrong_password", new_client.password_hash)
        print(f"  Wrong password rejection: {'PASSED' if not is_invalid else 'FAILED'}")

        # Clean up test data
        db.delete(new_client)
        db.commit()
        print("[SUCCESS] Test client cleaned up")

        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = test_client_with_password()
    if success:
        print("\n[PASSED] Client model now supports password_hash!")
    else:
        print("\n[FAILED] Test failed")