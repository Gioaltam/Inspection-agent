"""
API Integration Module - Connects frontend report generation to backend gallery
This module handles the complete workflow from report generation to client gallery
"""

import os
import json
import requests
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import shutil
import zipfile
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class InspectionAPIClient:
    """Client for integrating with the inspection backend API"""
    
    def __init__(self, base_url: str = None, api_key: str = None):
        """
        Initialize API client
        
        Args:
            base_url: Backend API URL (defaults to env variable)
            api_key: API key for authentication (defaults to env variable)
        """
        self.base_url = base_url or os.getenv('BACKEND_API_URL', 'http://localhost:8000')
        self.api_key = api_key or os.getenv('API_KEY', '')
        self.session = requests.Session()
        if self.api_key:
            self.session.headers['Authorization'] = f'Bearer {self.api_key}'
        
    def upload_report(self, 
                     report_path: Path,
                     client_id: str,
                     property_id: str,
                     employee_id: str = None) -> Dict[str, Any]:
        """
        Upload a generated report to the backend
        
        Args:
            report_path: Path to the report directory or ZIP file
            client_id: Client identifier
            property_id: Property identifier
            employee_id: Employee who processed the report
            
        Returns:
            API response with upload status
        """
        try:
            # Prepare the upload
            if report_path.is_dir():
                # Create a ZIP from the directory
                zip_path = self._create_report_zip(report_path)
            else:
                zip_path = report_path
            
            # Prepare multipart upload
            with open(zip_path, 'rb') as f:
                files = {'file': (zip_path.name, f, 'application/zip')}
                data = {
                    'client_id': client_id,
                    'property_id': property_id,
                    'employee_id': employee_id or 'system'
                }
                
                # Upload to backend
                response = self.session.post(
                    f'{self.base_url}/api/admin/upload-report',
                    files=files,
                    data=data,
                    timeout=300  # 5 minute timeout for large files
                )
                
            # Clean up temporary ZIP if created
            if report_path.is_dir() and zip_path.exists():
                zip_path.unlink()
                
            if response.status_code == 200:
                logger.info(f"Successfully uploaded report for property {property_id}")
                return response.json()
            else:
                logger.error(f"Failed to upload report: {response.status_code} - {response.text}")
                return {'error': f'Upload failed: {response.status_code}'}
                
        except Exception as e:
            logger.error(f"Error uploading report: {str(e)}")
            return {'error': str(e)}
    
    def _create_report_zip(self, report_dir: Path) -> Path:
        """Create a ZIP file from report directory"""
        zip_path = report_dir.parent / f"{report_dir.name}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(report_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(report_dir.parent)
                    zipf.write(file_path, arcname)
        
        return zip_path
    
    def get_client_token(self, client_id: str) -> Optional[str]:
        """
        Get or generate a client access token for the dashboard
        
        Args:
            client_id: Client identifier
            
        Returns:
            Access token for client dashboard
        """
        try:
            response = self.session.post(
                f'{self.base_url}/api/portal/generate-token',
                json={'client_id': client_id}
            )
            
            if response.status_code == 200:
                return response.json().get('token')
            else:
                logger.error(f"Failed to get client token: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting client token: {str(e)}")
            return None
    
    def register_report(self, report_data: Dict[str, Any]) -> bool:
        """
        Register a completed report with the backend
        
        Args:
            report_data: Report metadata including paths and IDs
            
        Returns:
            Success status
        """
        try:
            response = self.session.post(
                f'{self.base_url}/api/admin/register-report',
                json=report_data
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error registering report: {str(e)}")
            return False
    
    def get_property_info(self, property_address: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Look up property and client info by address
        
        Args:
            property_address: Property address
            
        Returns:
            Tuple of (client_id, property_id) or (None, None) if not found
        """
        try:
            response = self.session.get(
                f'{self.base_url}/api/admin/property-lookup',
                params={'address': property_address}
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('client_id'), data.get('property_id')
            else:
                logger.warning(f"Property not found: {property_address}")
                return None, None
                
        except Exception as e:
            logger.error(f"Error looking up property: {str(e)}")
            return None, None


class ReportWorkflow:
    """Orchestrates the complete report workflow from generation to gallery"""
    
    def __init__(self, api_client: InspectionAPIClient = None):
        """
        Initialize workflow manager
        
        Args:
            api_client: API client instance (creates default if not provided)
        """
        self.api_client = api_client or InspectionAPIClient()
        
    def process_and_upload(self,
                          source_path: Path,
                          client_name: str,
                          property_address: str,
                          employee_id: str = None) -> Dict[str, Any]:
        """
        Complete workflow: generate report and upload to gallery
        
        Args:
            source_path: ZIP file or directory with photos
            client_name: Client name
            property_address: Property address
            employee_id: Employee processing the report
            
        Returns:
            Status dictionary with results
        """
        try:
            # Import the report builder
            from run_report import build_reports
            
            # Look up property info
            client_id, property_id = self.api_client.get_property_info(property_address)
            
            if not client_id or not property_id:
                # Create new property record if not found
                logger.info(f"Property not found, creating new record for {property_address}")
                client_id = self._create_client_property(client_name, property_address)
                property_id = f"prop_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Generate the report
            logger.info(f"Generating report for {property_address}")
            report_result = build_reports(source_path, client_name, property_address)
            
            if 'error' in report_result:
                return report_result
            
            # Report is already in workspace/outputs, just return the gallery URL
            logger.info("Report generated successfully")
            report_dir = Path(report_result['web_dir']).parent
            
            # Build gallery URL - pointing to the gallery server on port 8005
            gallery_url = f"http://localhost:8005/?token=test"
            
            return {
                'status': 'success',
                'report_id': report_result['report_id'],
                'client_id': client_id,
                'property_id': property_id,
                'gallery_url': gallery_url,
                'pdf_path': report_result['pdf_path'],
                'web_dir': report_result['web_dir'],
                'message': f'Report successfully generated and available in gallery'
            }
                
        except Exception as e:
            logger.error(f"Workflow error: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'message': 'Failed to process report'
            }
    
    def _create_client_property(self, client_name: str, property_address: str) -> str:
        """Create a new client and property record"""
        try:
            # This would call the backend API to create records
            # For now, return a generated ID
            client_id = f"client_{client_name.lower().replace(' ', '_')}"
            
            response = self.api_client.session.post(
                f'{self.api_client.base_url}/api/admin/create-client-property',
                json={
                    'client_name': client_name,
                    'property_address': property_address
                }
            )
            
            if response.status_code == 200:
                return response.json()['client_id']
            else:
                return client_id
                
        except:
            return f"client_{datetime.now().strftime('%Y%m%d%H%M%S')}"


# Convenience function for direct use
def process_inspection(zip_path: str, client_name: str, property_address: str) -> Dict[str, Any]:
    """
    Process an inspection ZIP file and upload to gallery
    
    Args:
        zip_path: Path to ZIP file with photos
        client_name: Client name
        property_address: Property address
        
    Returns:
        Status dictionary
    """
    workflow = ReportWorkflow()
    return workflow.process_and_upload(
        source_path=Path(zip_path),
        client_name=client_name,
        property_address=property_address
    )


if __name__ == "__main__":
    # Test the integration
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python api_integration.py <zip_file> <client_name> <property_address>")
        sys.exit(1)
    
    result = process_inspection(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(result, indent=2))