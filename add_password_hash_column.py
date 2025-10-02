#!/usr/bin/env python
"""
Migration script to add password_hash column to clients table
"""
import sqlite3
import sys
from pathlib import Path

def add_password_hash_column():
    """Add password_hash column to clients table if it doesn't exist"""

    db_path = Path("app.db")
    if not db_path.exists():
        print(f"Database {db_path} not found. Tables will be created with the column when the app starts.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(clients)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'password_hash' in column_names:
            print("Column 'password_hash' already exists in 'clients' table")
            return

        # Add the column
        print("Adding 'password_hash' column to 'clients' table...")
        cursor.execute("""
            ALTER TABLE clients
            ADD COLUMN password_hash VARCHAR NOT NULL DEFAULT ''
        """)

        conn.commit()
        print("Successfully added 'password_hash' column to 'clients' table")

    except sqlite3.Error as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    add_password_hash_column()