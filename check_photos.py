import sqlite3
from pathlib import Path

conn = sqlite3.connect('workspace/inspection_portal.db')
cur = conn.cursor()

# Check which reports have photos for 904 marshal st
cur.execute('''
    SELECT r.id, r.web_dir, r.created_at, p.address
    FROM reports r
    JOIN properties p ON r.property_id = p.id
    WHERE p.address = "904 marshal st"
    ORDER BY r.created_at DESC
''')

for report_id, web_dir, created_at, address in cur.fetchall():
    print(f'Report {report_id[:8]}... from {created_at}:')
    photos_dir = Path('workspace') / web_dir.replace('\\', '/').replace('workspace/', '') / 'photos'
    if photos_dir.exists():
        photos = list(photos_dir.glob('*.jpg'))
        print(f'  Has {len(photos)} photos in {photos_dir}')
    else:
        print(f'  No photos directory at {photos_dir}')
    print()

conn.close()