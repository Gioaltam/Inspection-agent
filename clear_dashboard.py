#!/usr/bin/env python3
"""
Clear all reports and data from the dashboard database
"""

import sqlite3
import os
import shutil
from pathlib import Path

def clear_dashboard():
    """Clear all reports and associated data"""
    
    # Database path - try multiple locations
    possible_paths = [
        Path("workspace/inspection_portal.db"),
        Path("backend/inspection_portal.db"),
        Path("inspection_portal.db")
    ]
    
    db_path = None
    for path in possible_paths:
        if path.exists():
            db_path = path
            print(f"Found database at: {db_path}")
            break
    
    if not db_path:
        print("Database not found. Nothing to clear.")
        return
    
    try:
        # Connect to database
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        # Get all report web directories before deleting
        cur.execute("SELECT web_dir FROM reports")
        web_dirs = cur.fetchall()
        
        # Clear all tables
        tables_to_clear = ['reports', 'assets']
        for table in tables_to_clear:
            try:
                cur.execute(f"DELETE FROM {table}")
                print(f"Cleared {table} table")
            except sqlite3.OperationalError:
                print(f"Table {table} not found, skipping...")
        
        # Commit changes
        conn.commit()
        
        # Get deletion count
        cur.execute("SELECT changes()")
        changes = cur.fetchone()[0]
        
        conn.close()
        
        print(f"Database cleared successfully!")
        
        # Clear physical files - try multiple workspace locations
        possible_workspace = [
            Path("workspace"),
            Path("backend/workspace"),
            Path("../workspace")
        ]
        
        workspace_dir = None
        for ws in possible_workspace:
            if ws.exists():
                workspace_dir = ws
                break
        
        if workspace_dir and workspace_dir.exists():
            # Remove all report directories
            for web_dir_tuple in web_dirs:
                web_dir = web_dir_tuple[0]
                if web_dir:
                    dir_path = workspace_dir / web_dir.replace("\\", "/")
                    if dir_path.exists():
                        shutil.rmtree(dir_path, ignore_errors=True)
                        print(f"Removed directory: {dir_path}")
        
        # Clear cache if it exists
        cache_dir = Path(".cache")
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
            print("Cleared cache directory")
        
        # Clear any uploaded files in backend
        uploads_dir = Path("backend/uploads")
        if uploads_dir.exists():
            shutil.rmtree(uploads_dir, ignore_errors=True)
            uploads_dir.mkdir(exist_ok=True)
            print("Cleared uploads directory")
            
        print("\n[SUCCESS] Dashboard completely cleared!")
        print("You can now upload fresh reports without duplicates.")
        
    except Exception as e:
        print(f"Error clearing dashboard: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    response = input("This will DELETE all reports and photos from the dashboard. Are you sure? (yes/no): ")
    if response.lower() == 'yes':
        clear_dashboard()
    else:
        print("Cancelled.")