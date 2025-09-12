#!/usr/bin/env python
"""
Add password_hash column to clients table if it doesn't exist
"""

import sqlite3
import os

def add_password_hash_column():
    """Add password_hash column to clients table if it doesn't exist"""
    
    # Path to the database
    db_path = "inspection_reports.db"
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found. It will be created when the app runs.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(clients)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'password_hash' not in column_names:
            print("Adding password_hash column to clients table...")
            cursor.execute("ALTER TABLE clients ADD COLUMN password_hash TEXT")
            conn.commit()
            print("✅ password_hash column added successfully")
        else:
            print("✅ password_hash column already exists")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_password_hash_column()