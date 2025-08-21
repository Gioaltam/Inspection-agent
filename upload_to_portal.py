#!/usr/bin/env python3
"""
Upload inspection reports to the client portal.
This script takes existing PDF and JSON files and uploads them to the portal API.
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any
import argparse

# Portal configuration
PORTAL_URL = "http://localhost:8002"
INGEST_ENDPOINT = f"{PORTAL_URL}/api/ingest"

def load_credentials(creds_file: str = "juliana_demo_credentials.json") -> Dict[str, Any]:
    """Load portal credentials from JSON file."""
    creds_path = Path(creds_file)
    if not creds_path.exists():
        print(f"Error: Credentials file {creds_file} not found")
        sys.exit(1)
    
    with open(creds_path, 'r') as f:
        return json.load(f)

def upload_report(
    pdf_path: str,
    json_path: Optional[str],
    property_address: str,
    client_name: str,
    token: str
) -> Dict[str, Any]:
    """
    Upload a report to the portal.
    
    Args:
        pdf_path: Path to the PDF file
        json_path: Optional path to the JSON file
        property_address: Address of the property
        client_name: Name of the client/property owner
        token: Portal authentication token
    
    Returns:
        Response from the API
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Prepare the files for upload
    files = {
        'pdf': ('report.pdf', open(pdf_file, 'rb'), 'application/pdf')
    }
    
    if json_path:
        json_file = Path(json_path)
        if json_file.exists():
            files['json_report'] = ('report.json', open(json_file, 'rb'), 'application/json')
    
    # Prepare form data
    data = {
        'property_address': property_address,
        'client_name': client_name
    }
    
    # Add token to URL params
    params = {'token': token}
    
    try:
        print(f"Uploading report for {property_address}...")
        response = requests.post(
            INGEST_ENDPOINT,
            files=files,
            data=data,
            params=params
        )
        response.raise_for_status()
        
        result = response.json()
        print(f"[SUCCESS] Report uploaded successfully!")
        print(f"  Report ID: {result['report']['id']}")
        print(f"  Property ID: {result['report']['property_id']}")
        print(f"  PDF URL: {result['report']['pdf_url']}")
        if result['report'].get('json_url'):
            print(f"  JSON URL: {result['report']['json_url']}")
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"[FAILED] Failed to upload report: {e}")
        if hasattr(e.response, 'text'):
            print(f"  Error details: {e.response.text}")
        raise
    finally:
        # Close file handles
        for key, (filename, file_obj, content_type) in files.items():
            file_obj.close()

def extract_address_from_json(json_path: str) -> Optional[str]:
    """Extract property address from report JSON."""
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
            return data.get('address') or data.get('property_info', {}).get('address')
    except:
        return None

def extract_address_from_filename(filename: str) -> str:
    """Extract address from filename (removes .pdf/.json extension)."""
    name = Path(filename).stem
    # Remove report ID if present (UUID pattern)
    import re
    uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
    name = re.sub(uuid_pattern, '', name).strip('_- ')
    return name if name else "Unknown Property"

def process_output_directory(output_dir: str = "output", credentials_file: str = "juliana_demo_credentials.json"):
    """
    Process all reports in the output directory and upload them to the portal.
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"Error: Output directory {output_dir} not found")
        return
    
    # Load credentials
    creds = load_credentials(credentials_file)
    token = creds['portal_token']
    owner_name = creds['owner']['name']
    
    print(f"Uploading reports for {owner_name}")
    print(f"Portal URL: {PORTAL_URL}")
    print("-" * 50)
    
    # Find all PDF files
    pdf_files = list(output_path.glob("*.pdf"))
    
    if not pdf_files:
        print("No PDF files found in output directory")
        return
    
    uploaded_count = 0
    failed_count = 0
    
    for pdf_path in pdf_files:
        # Skip if filename contains "_hq" or "_original" (duplicates)
        if "_hq" in pdf_path.name or "_original" in pdf_path.name:
            continue
        
        # Look for corresponding JSON file
        json_path = pdf_path.with_suffix('.json')
        
        # Determine property address
        address = None
        if json_path.exists():
            address = extract_address_from_json(str(json_path))
        
        if not address:
            address = extract_address_from_filename(pdf_path.name)
        
        # Upload the report
        try:
            upload_report(
                pdf_path=str(pdf_path),
                json_path=str(json_path) if json_path.exists() else None,
                property_address=address,
                client_name=owner_name,
                token=token
            )
            uploaded_count += 1
        except Exception as e:
            print(f"Failed to upload {pdf_path.name}: {e}")
            failed_count += 1
        
        print()  # Add blank line between uploads
    
    print("-" * 50)
    print(f"Upload complete: {uploaded_count} successful, {failed_count} failed")
    
    if uploaded_count > 0:
        dashboard_url = f"{PORTAL_URL}/api/v2/portal/dashboard"
        print(f"\nView dashboard at: {dashboard_url}")
        print(f"(Include token in header: X-Session-Token: {token})")

def main():
    parser = argparse.ArgumentParser(description="Upload inspection reports to the client portal")
    parser.add_argument(
        '--pdf',
        help='Path to a specific PDF file to upload'
    )
    parser.add_argument(
        '--json',
        help='Path to the corresponding JSON file (optional)'
    )
    parser.add_argument(
        '--address',
        help='Property address (required if uploading specific file)'
    )
    parser.add_argument(
        '--client',
        default='Juliana Gomes',
        help='Client name (default: Juliana Gomes)'
    )
    parser.add_argument(
        '--token',
        help='Portal authentication token (or use credentials file)'
    )
    parser.add_argument(
        '--credentials',
        default='juliana_demo_credentials.json',
        help='Path to credentials JSON file'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Upload all reports in the output directory'
    )
    
    args = parser.parse_args()
    
    if args.all:
        # Process all files in output directory
        process_output_directory(credentials_file=args.credentials)
    elif args.pdf:
        # Upload specific file
        if not args.address:
            print("Error: --address is required when uploading a specific file")
            sys.exit(1)
        
        # Load token from credentials if not provided
        token = args.token
        if not token:
            creds = load_credentials(args.credentials)
            token = creds['portal_token']
        
        try:
            upload_report(
                pdf_path=args.pdf,
                json_path=args.json,
                property_address=args.address,
                client_name=args.client,
                token=token
            )
        except Exception as e:
            print(f"Upload failed: {e}")
            sys.exit(1)
    else:
        print("Usage: python upload_to_portal.py --all")
        print("   or: python upload_to_portal.py --pdf <file> --address <address>")
        parser.print_help()

if __name__ == "__main__":
    main()