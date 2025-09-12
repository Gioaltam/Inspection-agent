#!/usr/bin/env python3
"""Test script to verify settings persistence functionality"""

import json
from pathlib import Path
import tempfile
import shutil
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Settings file path
SETTINGS_FILE = Path.home() / ".checkmyrental_inspector.json"

def test_settings_persistence():
    """Test that settings are saved and loaded correctly"""
    
    # Backup existing settings if they exist
    backup_file = None
    if SETTINGS_FILE.exists():
        backup_file = SETTINGS_FILE.with_suffix('.json.backup')
        shutil.copy2(SETTINGS_FILE, backup_file)
        print(f"✅ Backed up existing settings to {backup_file}")
    
    try:
        # Test data
        test_settings = {
            'owner_name': 'Test Owner',
            'owner_id': 'test123',
            'gallery_name': 'Test Gallery',
            'inspector_name': 'Test Inspector',
            'job_concurrency': 4,
            'analysis_concurrency': 6
        }
        
        # Save test settings
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(test_settings, f, indent=2)
        print(f"✅ Saved test settings to {SETTINGS_FILE}")
        
        # Read settings back
        with open(SETTINGS_FILE, 'r') as f:
            loaded_settings = json.load(f)
        print(f"✅ Loaded settings from {SETTINGS_FILE}")
        
        # Verify all fields
        all_match = True
        for key, expected_value in test_settings.items():
            actual_value = loaded_settings.get(key)
            if actual_value == expected_value:
                print(f"✅ {key}: {actual_value} (matches)")
            else:
                print(f"❌ {key}: expected {expected_value}, got {actual_value}")
                all_match = False
        
        if all_match:
            print("\n🎉 All settings persisted correctly!")
        else:
            print("\n⚠️ Some settings did not persist correctly")
        
        # Display the settings file location
        print(f"\n📁 Settings file location: {SETTINGS_FILE}")
        print(f"📋 Settings file contents:")
        print(json.dumps(loaded_settings, indent=2))
        
    finally:
        # Restore backup if it existed
        if backup_file and backup_file.exists():
            shutil.copy2(backup_file, SETTINGS_FILE)
            backup_file.unlink()
            print(f"\n✅ Restored original settings from backup")
        elif SETTINGS_FILE.exists():
            # Clean up test file if no backup existed
            SETTINGS_FILE.unlink()
            print(f"\n✅ Cleaned up test settings file")

if __name__ == "__main__":
    print("=" * 50)
    print("Testing CheckMyRental Inspector Settings Persistence")
    print("=" * 50)
    test_settings_persistence()
    print("=" * 50)
    print("Test completed!")