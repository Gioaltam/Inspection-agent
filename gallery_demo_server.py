"""
Gallery demo server to showcase the inspection report gallery
"""
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from datetime import datetime
import base64
from PIL import Image, ImageDraw, ImageFont
import io

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sample report data
SAMPLE_REPORT = {
    "property_address": "456 Broadway E #204, Seattle, WA 98102",
    "client_name": "Sarah Johnson",
    "inspection_date": datetime.now().isoformat(),
    "inspector": "John Doe",
    "items": [
        {
            "location": "Kitchen: Under Sink",
            "severity": "critical",
            "observations": [
                "Active water leak detected under kitchen sink",
                "Water damage visible on cabinet floor",
                "Mold growth beginning on back wall"
            ],
            "potential_issues": [
                "Structural damage to cabinet",
                "Mold health hazard",
                "Increased water bills"
            ],
            "recommendations": [
                "Immediate plumber consultation required",
                "Replace damaged cabinet flooring",
                "Professional mold remediation"
            ]
        },
        {
            "location": "Master Bathroom: Shower",
            "severity": "important",
            "observations": [
                "Cracked grout lines in shower",
                "Caulking deteriorated around shower base",
                "Minor water staining on adjacent wall"
            ],
            "potential_issues": [
                "Water intrusion behind tiles",
                "Potential for mold growth",
                "Tile loosening over time"
            ],
            "recommendations": [
                "Re-grout shower tiles",
                "Replace shower caulking",
                "Monitor for water damage progression"
            ]
        },
        {
            "location": "Living Room: Windows",
            "severity": "minor",
            "observations": [
                "Window seals showing age",
                "Minor condensation between panes",
                "Hardware slightly loose"
            ],
            "potential_issues": [
                "Reduced energy efficiency",
                "Potential for seal failure"
            ],
            "recommendations": [
                "Schedule window maintenance",
                "Consider seal replacement within 6 months"
            ]
        },
        {
            "location": "HVAC System: Furnace",
            "severity": "important",
            "observations": [
                "Furnace filter extremely dirty",
                "Unusual noise during operation",
                "Last service date unknown"
            ],
            "potential_issues": [
                "Reduced heating efficiency",
                "Premature system failure",
                "Poor air quality"
            ],
            "recommendations": [
                "Immediate filter replacement",
                "Schedule HVAC service inspection",
                "Establish regular maintenance schedule"
            ]
        },
        {
            "location": "Roof: North Side",
            "severity": "critical",
            "observations": [
                "Multiple missing shingles",
                "Visible water staining in attic",
                "Gutters detached in section"
            ],
            "potential_issues": [
                "Active roof leak",
                "Structural damage to roof decking",
                "Interior water damage"
            ],
            "recommendations": [
                "Emergency roof repair required",
                "Full roof inspection by professional",
                "Gutter reattachment and cleaning"
            ]
        },
        {
            "location": "Electrical Panel: Main",
            "severity": "important",
            "observations": [
                "Several circuits not properly labeled",
                "Evidence of amateur modifications",
                "Slight burning smell near panel"
            ],
            "potential_issues": [
                "Fire hazard",
                "Code violations",
                "Insurance liability"
            ],
            "recommendations": [
                "Professional electrical inspection",
                "Update circuit labeling",
                "Remove unauthorized modifications"
            ]
        },
        {
            "location": "Basement: Foundation Wall",
            "severity": "minor",
            "observations": [
                "Minor hairline cracks in foundation",
                "Slight efflorescence on walls",
                "Humidity levels elevated"
            ],
            "potential_issues": [
                "Potential water seepage",
                "Foundation settling"
            ],
            "recommendations": [
                "Monitor crack progression",
                "Improve basement ventilation",
                "Consider dehumidifier installation"
            ]
        },
        {
            "location": "Garage: Door System",
            "severity": "minor",
            "observations": [
                "Garage door tracks need lubrication",
                "Weather stripping worn",
                "Remote sensor alignment off"
            ],
            "potential_issues": [
                "Premature wear of door system",
                "Energy loss",
                "Safety sensor malfunction"
            ],
            "recommendations": [
                "Lubricate door tracks and rollers",
                "Replace weather stripping",
                "Realign safety sensors"
            ]
        },
        {
            "location": "Exterior: Siding",
            "severity": "important",
            "observations": [
                "Paint peeling on south side",
                "Wood rot beginning near ground level",
                "Caulking gaps around windows"
            ],
            "potential_issues": [
                "Water damage to siding",
                "Structural deterioration",
                "Pest entry points"
            ],
            "recommendations": [
                "Scrape and repaint affected areas",
                "Replace rotted wood sections",
                "Re-caulk all window perimeters"
            ]
        },
        {
            "location": "Plumbing: Water Heater",
            "severity": "critical",
            "observations": [
                "Water heater is 15+ years old",
                "Rust visible on tank bottom",
                "Temperature pressure relief valve corroded"
            ],
            "potential_issues": [
                "Imminent tank failure",
                "Water damage risk",
                "Safety valve malfunction"
            ],
            "recommendations": [
                "Replace water heater immediately",
                "Install water sensor alarm",
                "Consider tankless upgrade"
            ]
        }
    ],
    "statistics": {
        "total_photos": 10,
        "critical_count": 3,
        "important_count": 4,
        "minor_count": 3
    }
}

def generate_test_image(index, item):
    """Generate a test image with issue information"""
    # Create a new image with a gradient background
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Draw gradient background
    for i in range(600):
        color_val = int(255 - (i * 0.2))
        draw.rectangle([0, i, 800, i+1], fill=(color_val, color_val, color_val))
    
    # Add severity color bar
    severity_colors = {
        'critical': (231, 76, 60),
        'important': (243, 156, 18),
        'minor': (39, 174, 96)
    }
    color = severity_colors.get(item['severity'], (100, 100, 100))
    draw.rectangle([0, 0, 800, 40], fill=color)
    
    # Add text
    try:
        # Try to use a better font if available
        from PIL import ImageFont
        font_large = ImageFont.truetype("arial.ttf", 36)
        font_medium = ImageFont.truetype("arial.ttf", 24)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except:
        # Fallback to default font
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Photo number
    draw.text((20, 60), f"Photo #{index}", fill=(50, 50, 50), font=font_large)
    
    # Location
    draw.text((20, 120), item['location'], fill=(30, 30, 30), font=font_medium)
    
    # Severity badge
    draw.text((20, 10), item['severity'].upper(), fill=(255, 255, 255), font=font_medium)
    
    # Observations
    y_pos = 180
    draw.text((20, y_pos), "Observations:", fill=(50, 50, 50), font=font_medium)
    y_pos += 40
    for obs in item.get('observations', [])[:3]:
        # Wrap long text
        words = obs.split()
        line = ""
        for word in words:
            if len(line + word) < 60:
                line += word + " "
            else:
                draw.text((40, y_pos), "• " + line.strip(), fill=(80, 80, 80), font=font_small)
                y_pos += 30
                line = word + " "
        if line:
            draw.text((40, y_pos), "• " + line.strip(), fill=(80, 80, 80), font=font_small)
            y_pos += 30
    
    # Add a watermark pattern
    for x in range(0, 800, 150):
        for y in range(300, 600, 100):
            draw.text((x, y), "SAMPLE", fill=(220, 220, 220), font=font_small)
    
    # Convert to bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=85)
    img_byte_arr.seek(0)
    
    return img_byte_arr.getvalue()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the gallery template
@app.get("/")
async def serve_gallery():
    return FileResponse("static/gallery-template.html")

# Serve the multi-property gallery
@app.get("/multi")
async def serve_multi_gallery():
    return FileResponse("static/multi-property-gallery.html")

# Serve the enhanced owner dashboard
@app.get("/dashboard")
async def serve_dashboard():
    return FileResponse("static/owner-dashboard-enhanced.html")

# Serve the viewer
@app.get("/viewer")
async def serve_viewer():
    return FileResponse("static/gallery-viewer.html")

# API endpoint for report data
@app.get("/api/reports/{report_id}/data.json")
async def get_report_data(report_id: str):
    return JSONResponse(SAMPLE_REPORT)

# API endpoint for portal report data
@app.get("/api/portal/reports/{report_id}/json")
async def get_portal_report_data(report_id: str, token: str = Query(None)):
    return JSONResponse(SAMPLE_REPORT)

# Serve test photos
@app.get("/photos/photo_{photo_id}.jpg")
async def get_photo(photo_id: str):
    # Extract index from photo_id (e.g., "001" -> 1)
    try:
        index = int(photo_id)
        if 1 <= index <= len(SAMPLE_REPORT['items']):
            item = SAMPLE_REPORT['items'][index - 1]
            image_data = generate_test_image(index, item)
            return Response(content=image_data, media_type="image/jpeg")
    except:
        pass
    
    # Return a default image if not found
    img = Image.new('RGB', (800, 600), color='gray')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    return Response(content=img_byte_arr.getvalue(), media_type="image/jpeg")

# API endpoint for portal photos
@app.get("/api/portal/reports/{report_id}/photos/photo_{photo_id}.jpg")
async def get_portal_photo(report_id: str, photo_id: str, token: str = Query(None)):
    return await get_photo(photo_id)

if __name__ == "__main__":
    import uvicorn
    
    print(f"\n{'='*70}")
    print("INSPECTION GALLERY DEMO SERVER")
    print(f"{'='*70}")
    print(f"\nThe gallery is now running with sample report data!")
    print(f"\nAccess the interfaces at:")
    print(f"\n  [DASHBOARD] Owner Dashboard:       http://localhost:8006/dashboard")
    print(f"  [GALLERY]   Multi-Property Gallery: http://localhost:8006/multi")
    print(f"  [TEMPLATE]  Template Gallery:       http://localhost:8006/")
    print(f"  [VIEWER]    Viewer Gallery:         http://localhost:8006/viewer?id=sample&token=demo")
    print(f"\n{'='*70}")
    print(f"\nOwner Dashboard Features:")
    print(f"  * Complete property portfolio overview")
    print(f"  * Integrated inspection gallery for each property")
    print(f"  * Multiple inspections per property with date selection")
    print(f"  * Quarterly and custom date range filtering")
    print(f"  * Real-time issue severity statistics")
    print(f"  * Direct access to photo galleries from property cards")
    print(f"  * Filter by property type, date, and search")
    print(f"\n{'='*70}\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8006)