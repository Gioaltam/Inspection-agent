#!/usr/bin/env python3
"""
Add Juliana as a client with portal token.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.app.database import SessionLocal, engine
from backend.app.models import Base, Client

def add_juliana_client():
    """Add Juliana as a client with portal token."""
    
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Create session
    db = SessionLocal()
    
    try:
        # Check if Juliana already exists
        existing = db.query(Client).filter(Client.email == "juliana.gomes@example.com").first()
        
        if existing:
            print(f"Juliana already exists with ID: {existing.id}")
            # Update portal token if missing
            if not existing.portal_token:
                existing.portal_token = "sYZc1sPChXlob023eOUjTzVfzvwHQhtxiZoPuapFVyQ"
                db.commit()
                print("Updated portal token")
        else:
            # Create new client
            juliana = Client(
                id="4210e2c1-bd1a-4da1-bd62-fec5a404d334",
                name="Juliana Gomes",
                contact_name="Juliana Gomes",
                email="juliana.gomes@example.com",
                portal_token="sYZc1sPChXlob023eOUjTzVfzvwHQhtxiZoPuapFVyQ",
                created_at=datetime.utcnow()
            )
            
            db.add(juliana)
            db.commit()
            db.refresh(juliana)
            
            print(f"Created Juliana client with ID: {juliana.id}")
            print(f"Portal token: {juliana.portal_token}")
            print(f"Dashboard URL: http://localhost:8002/api/v2/portal/dashboard")
            print(f"(Use header: X-Session-Token: {juliana.portal_token})")
            
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_juliana_client()