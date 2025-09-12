"""
Migration script to add new payment columns to existing database
"""
import sqlite3
import os

def migrate_database():
    """Add new columns to portal_clients table"""
    db_path = "./app.db"
    
    if not os.path.exists(db_path):
        print("Database doesn't exist yet. Will be created on first run.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(portal_clients)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add missing columns
        if 'is_paid' not in columns:
            print("Adding is_paid column...")
            cursor.execute("ALTER TABLE portal_clients ADD COLUMN is_paid BOOLEAN DEFAULT 0")
        
        if 'payment_date' not in columns:
            print("Adding payment_date column...")
            cursor.execute("ALTER TABLE portal_clients ADD COLUMN payment_date DATETIME")
        
        if 'payment_amount' not in columns:
            print("Adding payment_amount column...")
            cursor.execute("ALTER TABLE portal_clients ADD COLUMN payment_amount VARCHAR(50)")
        
        if 'stripe_customer_id' not in columns:
            print("Adding stripe_customer_id column...")
            cursor.execute("ALTER TABLE portal_clients ADD COLUMN stripe_customer_id VARCHAR(255)")
        
        if 'properties_data' not in columns:
            print("Adding properties_data column...")
            cursor.execute("ALTER TABLE portal_clients ADD COLUMN properties_data TEXT")
        
        conn.commit()
        print("Database migration completed successfully")
        
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()