"""Photos API endpoints"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import sqlite3
import json

router = APIRouter()
# Force reload with updated photo-report mapping

@router.get("/property/{property_address}")
def get_property_photos(property_address: str):
    """Get all photos for a property from ALL reports"""
    try:
        # Connect to database
        db_path = Path("../workspace/inspection_portal.db")
        if not db_path.exists():
            return {"photos": []}
            
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        # Get ALL reports for this property
        cur.execute("""
            SELECT r.id, r.web_dir, r.created_at
            FROM reports r
            JOIN properties p ON r.property_id = p.id
            WHERE p.address = ?
            ORDER BY r.created_at DESC
        """, (property_address,))
        
        rows = cur.fetchall()
        conn.close()
        
        if not rows:
            return {"photos": []}
            
        all_photos = []
        latest_report_id = rows[0][0] if rows else None
        
        # Get photos from each report
        for report_id, web_dir, created_at in rows:
            web_path = Path("..") / web_dir.replace("\\", "/")
            photos_dir = web_path / "photos"
            
            if photos_dir.exists():
                for photo_file in sorted(photos_dir.glob("*.jpg")):
                    all_photos.append({
                        "filename": photo_file.name,
                        "url": f"/api/photos/image/{report_id}/{photo_file.name}",
                        "reportId": report_id  # Each photo linked to its specific report
                    })
        
        return {"photos": all_photos, "report_id": latest_report_id}
        
    except Exception as e:
        print(f"Error fetching photos: {e}")
        return {"photos": []}

@router.get("/image/{report_id}/{filename}")
def get_photo_image(report_id: str, filename: str):
    """Serve a specific photo file"""
    try:
        # Get report path from database
        db_path = Path("../workspace/inspection_portal.db")
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        cur.execute("SELECT web_dir FROM reports WHERE id = ?", (report_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
            
        web_dir = row[0]
        
        # Serve the photo file
        photo_path = Path("..") / web_dir.replace("\\", "/") / "photos" / filename
        
        if not photo_path.exists():
            raise HTTPException(status_code=404, detail="Photo not found")
            
        return FileResponse(str(photo_path), media_type="image/jpeg")
        
    except Exception as e:
        print(f"Error serving photo: {e}")
        raise HTTPException(status_code=500, detail=str(e))