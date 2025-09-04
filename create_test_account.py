#!/usr/bin/env python3
"""
Create a test account for Juliana Shewmaker
Email: julianagomesfl@yahoo.com
Password: Milo2050
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Change to backend directory to use correct database path
os.chdir(Path(__file__).parent / "backend")

# Add backend directory to path
sys.path.append(str(Path(__file__).parent / "backend"))

from app.portal_security import hash_password
from app.portal_models import PortalClient, SessionLocal, ClientPortalToken, init_portal_tables
from app.storage import StorageService

# Ensure tables exist
init_portal_tables()

def create_test_account():
    """Create or update Juliana's test account"""
    
    # User details
    email = "julianagomesfl@yahoo.com"
    password = "Milo2050"
    full_name = "Juliana Shewmaker"
    
    # Hash the password
    hashed_password = hash_password(password)
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if user already exists
        existing_client = db.query(PortalClient).filter(
            PortalClient.email == email
        ).first()
        
        if existing_client:
            # Update existing user
            existing_client.full_name = full_name
            existing_client.password_hash = hashed_password
            db.commit()
            print(f"Updated existing account for {email}")
            client = existing_client
        else:
            # Create new user
            client = PortalClient(
                email=email,
                full_name=full_name,
                password_hash=hashed_password,
                is_active=True
            )
            db.add(client)
            db.commit()
            db.refresh(client)
            print(f"Created new account for {email}")
        
        # Add a sample property token for testing
        sample_token = "DEMO1234"
        
        # Check if token already linked
        existing_link = db.query(ClientPortalToken).filter(
            ClientPortalToken.client_id == client.id,
            ClientPortalToken.portal_token == sample_token
        ).first()
        
        if not existing_link:
            # Link the demo token to Juliana's account
            link = ClientPortalToken(
                client_id=client.id,
                portal_token=sample_token
            )
            db.add(link)
            db.commit()
            print(f"  Linked demo token: {sample_token}")
        
        # Create demo property data in local JSON
        import json
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        properties_file = data_dir / "properties.json"
        if properties_file.exists():
            with open(properties_file, 'r') as f:
                properties = json.load(f)
        else:
            properties = {}
        
        if sample_token not in properties:
            properties[sample_token] = {
                "portal_token": sample_token,
                "owner_name": full_name,
                "address": "123 Demo Street, Miami, FL 33101",
                "type": "single",
                "label": "Demo Property",
                "created_at": datetime.utcnow().isoformat()
            }
            with open(properties_file, 'w') as f:
                json.dump(properties, f, indent=2)
            print(f"  Created demo property data")
        
        print(f"\n✓ Test account ready for Juliana Shewmaker")
        print(f"  Email: {email}")
        print(f"  Password: {password}")
        print(f"  Full Name: {full_name}")
        print(f"  Demo Portal ID: {sample_token}")
        print(f"\n  She can now:")
        print(f"  1. Click 'Owner Portal' button on the landing page")
        print(f"  2. Log in with her credentials")
        print(f"  3. Access the owner dashboard automatically")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_account()