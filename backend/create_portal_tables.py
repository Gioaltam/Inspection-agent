#!/usr/bin/env python3
"""Create portal_clients and related tables"""

import sqlite3
from datetime import datetime

def create_portal_tables():
    conn = sqlite3.connect('inspection_portal.db')
    cur = conn.cursor()
    
    # Create portal_clients table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS portal_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT,
            company_name TEXT,
            phone TEXT,
            is_paid BOOLEAN DEFAULT 0,
            payment_date TIMESTAMP,
            payment_amount TEXT,
            stripe_customer_id TEXT,
            properties_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create client_portal_tokens table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS client_portal_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            portal_token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES portal_clients(id)
        )
    ''')
    
    # Insert Juliana's demo account
    cur.execute('''
        INSERT OR IGNORE INTO portal_clients (email, full_name, is_paid, properties_data)
        VALUES (?, ?, ?, ?)
    ''', (
        'juliana@checkmyrental.com',
        'Juliana Shewmaker',
        1,
        '''[
            {"name": "Harborview 12B", "address": "4155 Key Thatch Dr, Tampa, FL"},
            {"name": "Seaside Cottage", "address": "308 Lookout Dr, Apollo Beach"},
            {"name": "Palm Grove 3C", "address": "Pinellas Park"}
        ]'''
    ))
    
    # Get Juliana's client ID
    cur.execute('SELECT id FROM portal_clients WHERE email = ?', ('juliana@checkmyrental.com',))
    client_id = cur.fetchone()
    
    if client_id:
        # Create portal token for Juliana
        cur.execute('''
            INSERT OR IGNORE INTO client_portal_tokens (client_id, portal_token)
            VALUES (?, ?)
        ''', (client_id[0], 'DEMO1234'))
    
    conn.commit()
    conn.close()
    print("Portal tables created successfully!")
    
    # Show what was created
    conn = sqlite3.connect('inspection_portal.db')
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print("\nTables in database:", [t[0] for t in tables])
    
    cur.execute("SELECT * FROM portal_clients")
    clients = cur.fetchall()
    print("\nPortal clients:", clients)
    
    cur.execute("SELECT * FROM client_portal_tokens")
    tokens = cur.fetchall()
    print("\nPortal tokens:", tokens)
    
    conn.close()

if __name__ == "__main__":
    create_portal_tables()