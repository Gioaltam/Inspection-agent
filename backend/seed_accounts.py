"""
Seed script to create initial accounts including Juliana's demo account
"""
import json
from datetime import datetime
from app.portal_models import SessionLocal, PortalClient, ClientPortalToken, init_portal_tables
from app.portal_security import hash_password

def seed_accounts():
    """Create initial accounts with proper setup"""
    init_portal_tables()
    db = SessionLocal()
    
    try:
        # Check if Juliana's account already exists
        juliana = db.query(PortalClient).filter(PortalClient.email == "juliana@checkmyrental.com").first()
        
        if not juliana:
            print("Creating Juliana's demo account...")
            
            # Juliana's properties data
            properties_data = json.dumps([
                {
                    "id": "p1",
                    "name": "Harborview 12B",
                    "address": "4155 Key Thatch Dr, Tampa, FL",
                    "lastInspection": "2024-08-02",
                    "criticalIssues": 0,
                    "importantIssues": 2
                },
                {
                    "id": "p2", 
                    "name": "Seaside Cottage",
                    "address": "308 Lookout Dr, Apollo Beach",
                    "lastInspection": "2024-08-20",
                    "criticalIssues": 0,
                    "importantIssues": 0
                },
                {
                    "id": "p3",
                    "name": "Palm Grove 3C",
                    "address": "Pinellas Park",
                    "lastInspection": "2024-07-11",
                    "criticalIssues": 1,
                    "importantIssues": 1
                }
            ])
            
            # Create Juliana's account
            juliana = PortalClient(
                email="juliana@checkmyrental.com",
                password_hash=hash_password("owner2024"),
                full_name="Juliana Shewmaker",
                is_active=True,
                is_paid=True,  # Demo account is pre-paid
                payment_date=datetime.utcnow(),
                payment_amount="Demo Account",
                properties_data=properties_data
            )
            db.add(juliana)
            db.commit()
            db.refresh(juliana)
            
            # Add demo token for Juliana
            demo_token = ClientPortalToken(
                client_id=juliana.id,
                portal_token="DEMO1234"
            )
            db.add(demo_token)
            db.commit()
            
            print(f"Created Juliana's account (ID: {juliana.id})")
            print("  Email: juliana@checkmyrental.com")
            print("  Password: owner2024")
            print("  Status: Paid (Demo)")
            print("  Properties: 3")
        else:
            print("Juliana's account already exists")
            
            # Update payment status if needed
            if not juliana.is_paid:
                juliana.is_paid = True
                juliana.payment_date = datetime.utcnow()
                juliana.payment_amount = "Demo Account"
                db.commit()
                print("  Updated payment status to paid")
        
        # You can add more default accounts here if needed
        
    except Exception as e:
        print(f"Error seeding accounts: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_accounts()