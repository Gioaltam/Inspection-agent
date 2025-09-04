#!/usr/bin/env python3
"""
Fix existing reports by creating placeholder photos or copying from source
This script ensures all reports have photos in the correct location
"""

import os
import json
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def create_placeholder_image(output_path, text="Inspection Photo", size=(800, 600)):
    """Create a placeholder image with text"""
    # Create image with gradient background
    img = Image.new('RGB', size, color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    
    # Draw a camera icon shape
    icon_size = 100
    x_center = size[0] // 2
    y_center = size[1] // 2 - 50
    
    # Camera body
    draw.rectangle(
        [x_center - icon_size//2, y_center - icon_size//3, 
         x_center + icon_size//2, y_center + icon_size//3],
        fill=(150, 150, 150)
    )
    
    # Camera lens
    draw.ellipse(
        [x_center - 30, y_center - 30, x_center + 30, y_center + 30],
        fill=(100, 100, 100)
    )
    
    # Add text
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_x = (size[0] - text_width) // 2
    draw.text((text_x, y_center + 80), text, fill=(100, 100, 100), font=font)
    
    # Save image
    img.save(output_path, 'JPEG', quality=85)
    print(f"Created placeholder: {output_path}")

def fix_report_photos(report_dir):
    """Fix photos for a single report"""
    report_path = Path(report_dir)
    
    # Load report data
    json_file = report_path / "report_data.json"
    if not json_file.exists():
        json_file = report_path / "web" / "report.json"
    
    if not json_file.exists():
        print(f"No JSON data found for {report_path.name}")
        return False
    
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON for {report_path.name}: {e}")
        return False
    
    # Create photo directories
    photos_dir = report_path / "photos"
    web_photos_dir = report_path / "web" / "photos"
    photos_dir.mkdir(exist_ok=True)
    web_photos_dir.mkdir(parents=True, exist_ok=True)
    
    items = data.get('items', [])
    if not items:
        print(f"No items found in {report_path.name}")
        return False
    
    print(f"\nProcessing {report_path.name}:")
    print(f"  Found {len(items)} items")
    
    # Create photos for each item
    for i, item in enumerate(items, 1):
        # Generate photo filenames
        photo_name = f"photo_{i:03d}.jpg"
        archive_name = f"{i:03d}_photo.jpg"
        
        # Paths for both directories
        web_photo_path = web_photos_dir / photo_name
        archive_photo_path = photos_dir / archive_name
        
        # Skip if photos already exist
        if web_photo_path.exists() and archive_photo_path.exists():
            print(f"  ✓ Photo {i} already exists")
            continue
        
        # Try to find original photo from the image_path
        original_found = False
        if 'image_path' in item:
            original_path = Path(item['image_path'])
            if original_path.exists():
                # Copy original photo
                shutil.copy2(original_path, web_photo_path)
                shutil.copy2(original_path, archive_photo_path)
                print(f"  ✓ Copied original photo {i}")
                original_found = True
        
        if not original_found:
            # Create placeholder with location information
            location = item.get('location', f'Area {i}')
            severity = item.get('severity', 'Unknown')
            placeholder_text = f"{location}\n{severity}"
            
            # Create placeholder for web
            if not web_photo_path.exists():
                create_placeholder_image(web_photo_path, placeholder_text)
            
            # Copy to archive
            if not archive_photo_path.exists():
                shutil.copy2(web_photo_path, archive_photo_path)
            
            print(f"  ✓ Created placeholder for photo {i} ({location})")
    
    print(f"  Completed fixing {report_path.name}")
    return True

def main():
    """Fix all existing reports"""
    workspace_dir = Path("workspace/outputs")
    
    if not workspace_dir.exists():
        print("No workspace/outputs directory found")
        return
    
    # Get all report directories
    report_dirs = [d for d in workspace_dir.iterdir() if d.is_dir()]
    
    if not report_dirs:
        print("No reports found in workspace/outputs")
        return
    
    print(f"Found {len(report_dirs)} reports to fix")
    print("="*60)
    
    success_count = 0
    for report_dir in report_dirs:
        if fix_report_photos(report_dir):
            success_count += 1
    
    print("\n" + "="*60)
    print(f"Fixed {success_count}/{len(report_dirs)} reports")
    print("\nReports are now ready to display in the gallery!")
    print("Restart the gallery server to see the photos.")

if __name__ == "__main__":
    main()