#!/usr/bin/env python3
"""Demo script to show settings being saved and loaded in the UI"""

import json
from pathlib import Path
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SETTINGS_FILE = Path.home() / ".checkmyrental_inspector.json"

# Create demo settings
demo_settings = {
    'owner_name': 'ABC Property Management',
    'owner_id': 'abc123',
    'gallery_name': 'March Inspections',
    'inspector_name': 'John Inspector',
    'job_concurrency': 2,
    'analysis_concurrency': 4
}

print("=" * 60)
print("CheckMyRental Inspector - Settings Persistence Demo")
print("=" * 60)
print()
print("Creating demo settings file...")
print(f"Location: {SETTINGS_FILE}")
print()

# Save demo settings
with open(SETTINGS_FILE, 'w') as f:
    json.dump(demo_settings, f, indent=2)

print("✅ Demo settings saved!")
print()
print("Settings that will be restored on next app launch:")
print("-" * 40)
print(f"  Owner Name:         {demo_settings['owner_name']}")
print(f"  Owner ID:           {demo_settings['owner_id']}")
print(f"  Gallery:            {demo_settings['gallery_name']}")
print(f"  Inspector Name:     {demo_settings['inspector_name']}")
print(f"  Parallel Jobs:      {demo_settings['job_concurrency']}")
print(f"  Images per Job:     {demo_settings['analysis_concurrency']}")
print("-" * 40)
print()
print("When you launch the app (python frontend.py), these values")
print("will be automatically loaded into the form fields.")
print()
print("The settings are saved:")
print("  • When you click the 'Generate Reports' button")
print("  • When you close the application window")
print()
print("=" * 60)