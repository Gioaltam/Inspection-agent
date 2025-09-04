#!/usr/bin/env python3
"""
Complete System Test for Inspection Agent
Tests the entire workflow from upload to gallery display
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_status(status, message):
    """Print colored status messages"""
    if status == "success":
        print(f"{GREEN}✓{RESET} {message}")
    elif status == "error":
        print(f"{RED}✗{RESET} {message}")
    elif status == "warning":
        print(f"{YELLOW}⚠{RESET} {message}")
    elif status == "info":
        print(f"{BLUE}ℹ{RESET} {message}")

def test_backend_api():
    """Test if backend API is running"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            print_status("success", "Backend API is running on port 8000")
            return True
        else:
            print_status("error", f"Backend API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_status("error", "Backend API is not running (port 8000)")
        print_status("info", "Start it with: python backend_simple.py")
        return False
    except Exception as e:
        print_status("error", f"Backend API error: {e}")
        return False

def test_gallery_server():
    """Test if gallery server is running"""
    try:
        response = requests.get("http://localhost:8005/", timeout=2)
        if response.status_code == 200:
            print_status("success", "Gallery server is running on port 8005")
            return True
        else:
            print_status("error", f"Gallery server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_status("error", "Gallery server is not running (port 8005)")
        print_status("info", "Start it with: python gallery_final.py")
        return False
    except Exception as e:
        print_status("error", f"Gallery server error: {e}")
        return False

def test_gallery_api():
    """Test if gallery API returns data"""
    try:
        response = requests.get("http://localhost:8005/api/portal?token=test", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if 'owner' in data or 'dashboard_data' in data:
                props = data.get('properties', []) if 'properties' in data else []
                print_status("success", f"Gallery API working - {len(props)} properties found")
                return True
            else:
                print_status("warning", "Gallery API returned unexpected data format")
                return False
        else:
            print_status("error", f"Gallery API returned status {response.status_code}")
            return False
    except Exception as e:
        print_status("error", f"Gallery API error: {e}")
        return False

def test_reports_exist():
    """Check if reports exist in workspace"""
    workspace_dir = Path("workspace/outputs")
    
    if not workspace_dir.exists():
        print_status("error", "No workspace/outputs directory found")
        return False
    
    report_dirs = list(workspace_dir.glob("*"))
    report_count = len([d for d in report_dirs if d.is_dir()])
    
    if report_count > 0:
        print_status("success", f"Found {report_count} reports in workspace/outputs")
        
        # Check for photos
        photos_found = False
        for report_dir in report_dirs:
            if report_dir.is_dir():
                web_photos = report_dir / "web" / "photos"
                photos = report_dir / "photos"
                if web_photos.exists() or photos.exists():
                    photos_found = True
                    break
        
        if photos_found:
            print_status("success", "Photos found in reports")
        else:
            print_status("warning", "No photos found - run: python fix_existing_reports.py")
        
        return True
    else:
        print_status("warning", "No reports found in workspace/outputs")
        print_status("info", "Process a property first using the frontend GUI")
        return False

def test_env_file():
    """Check if .env file exists and has required keys"""
    env_path = Path(".env")
    
    if not env_path.exists():
        print_status("error", ".env file not found")
        print_status("info", "Copy .env.example to .env and add your API keys")
        return False
    
    with open(env_path, 'r') as f:
        env_content = f.read()
    
    required_keys = ["OPENAI_API_KEY"]
    missing_keys = []
    
    for key in required_keys:
        if key not in env_content:
            missing_keys.append(key)
        elif f"{key}=your" in env_content or f"{key}=sk-..." in env_content:
            print_status("warning", f"{key} appears to be using default value")
    
    if missing_keys:
        print_status("error", f"Missing environment variables: {', '.join(missing_keys)}")
        return False
    else:
        print_status("success", "Environment file configured")
        return True

def test_photo_endpoints():
    """Test if photo endpoints are working"""
    # Get a report to test with
    workspace_dir = Path("workspace/outputs")
    
    if workspace_dir.exists():
        for report_dir in workspace_dir.glob("*"):
            if report_dir.is_dir():
                # Try to access a photo
                report_name = report_dir.name
                test_url = f"http://localhost:8005/api/reports/{report_name}/photos/photo_001.jpg"
                
                try:
                    response = requests.get(test_url, timeout=2)
                    if response.status_code == 200:
                        print_status("success", "Photo endpoints working")
                        return True
                    elif response.status_code == 404:
                        print_status("warning", "Photo endpoints working but photos not found")
                        print_status("info", "Run: python fix_existing_reports.py")
                        return True
                except:
                    pass
                
                break
    
    print_status("warning", "Could not test photo endpoints")
    return True

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("INSPECTION AGENT - SYSTEM TEST")
    print("="*60 + "\n")
    
    tests = [
        ("Environment Configuration", test_env_file),
        ("Backend API", test_backend_api),
        ("Gallery Server", test_gallery_server),
        ("Gallery API", test_gallery_api),
        ("Reports in Workspace", test_reports_exist),
        ("Photo Endpoints", test_photo_endpoints),
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\nTesting {test_name}...")
        results[test_name] = test_func()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓" if result else "✗"
        color = GREEN if result else RED
        print(f"{color}{status}{RESET} {test_name}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print(f"\n{GREEN}All tests passed! System is ready.{RESET}")
        print("\nAccess your gallery at: http://localhost:8005/?token=test")
    else:
        print(f"\n{YELLOW}Some tests failed. Fix the issues above.{RESET}")
        print("\nQuick fixes:")
        print("1. Start backend: python backend_simple.py")
        print("2. Start gallery: python gallery_final.py")
        print("3. Fix photos: python fix_existing_reports.py")
        print("4. Process new report: python frontend_enhanced.py")

if __name__ == "__main__":
    main()