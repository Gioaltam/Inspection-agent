"""
Cloud Storage Service for AWS S3
Handles all photo and document uploads to cloud storage
"""
import boto3
from botocore.exceptions import ClientError
import os
from pathlib import Path
from typing import Optional, BinaryIO, Dict, Any
from PIL import Image
import io
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class CloudStorageService:
    """Service for managing cloud storage operations with AWS S3"""
    
    def __init__(self):
        """Initialize S3 client with credentials from environment"""
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'checkmyrental-inspection-reports')
        self.base_url = os.getenv('S3_BASE_URL', f'https://{self.bucket_name}.s3.amazonaws.com')
        
        if not self.aws_access_key or not self.aws_secret_key:
            raise ValueError("AWS credentials not found in environment variables")
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.aws_region
        )
        
        logger.info(f"CloudStorageService initialized with bucket: {self.bucket_name}")
    
    def upload_photo(self, 
                    file_path_or_bytes: Any,
                    report_id: str, 
                    photo_index: int,
                    create_thumbnail: bool = True) -> Dict[str, str]:
        """
        Upload a photo to S3 and optionally create a thumbnail
        
        Args:
            file_path_or_bytes: Path to file or file-like object
            report_id: Unique report identifier
            photo_index: Index of photo in the report
            create_thumbnail: Whether to create and upload a thumbnail
            
        Returns:
            Dictionary with 'full_url' and optionally 'thumbnail_url'
        """
        try:
            # Prepare the image data
            if isinstance(file_path_or_bytes, (str, Path)):
                file_path = Path(file_path_or_bytes)
                with open(file_path, 'rb') as f:
                    image_data = f.read()
                extension = file_path.suffix.lower()
            else:
                # It's already bytes or file-like object
                image_data = file_path_or_bytes.read() if hasattr(file_path_or_bytes, 'read') else file_path_or_bytes
                extension = '.jpg'  # Default extension
            
            # Generate S3 key (path in bucket)
            photo_key = f"reports/{report_id}/photos/photo_{photo_index:03d}{extension}"
            
            # Upload full-size image
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=photo_key,
                Body=image_data,
                ContentType=self._get_content_type(extension),
                CacheControl='max-age=31536000'  # Cache for 1 year
            )
            
            full_url = f"{self.base_url}/{photo_key}"
            result = {'full_url': full_url}
            
            # Create and upload thumbnail if requested
            if create_thumbnail:
                thumbnail_data = self._create_thumbnail(image_data)
                thumbnail_key = f"reports/{report_id}/thumbnails/thumb_{photo_index:03d}.jpg"
                
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=thumbnail_key,
                    Body=thumbnail_data,
                    ContentType='image/jpeg',
                    CacheControl='max-age=31536000'
                )
                
                result['thumbnail_url'] = f"{self.base_url}/{thumbnail_key}"
            
            logger.info(f"Uploaded photo {photo_index} for report {report_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error uploading photo: {e}")
            raise
    
    def upload_pdf(self, 
                   pdf_path_or_bytes: Any,
                   report_id: str) -> str:
        """
        Upload a PDF report to S3
        
        Args:
            pdf_path_or_bytes: Path to PDF file or bytes
            report_id: Unique report identifier
            
        Returns:
            URL of uploaded PDF
        """
        try:
            # Prepare PDF data
            if isinstance(pdf_path_or_bytes, (str, Path)):
                with open(pdf_path_or_bytes, 'rb') as f:
                    pdf_data = f.read()
            else:
                pdf_data = pdf_path_or_bytes.read() if hasattr(pdf_path_or_bytes, 'read') else pdf_path_or_bytes
            
            # Generate S3 key
            pdf_key = f"reports/{report_id}/report_{report_id}.pdf"
            
            # Upload PDF
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=pdf_key,
                Body=pdf_data,
                ContentType='application/pdf',
                ContentDisposition=f'inline; filename="report_{report_id}.pdf"',
                CacheControl='max-age=31536000'
            )
            
            pdf_url = f"{self.base_url}/{pdf_key}"
            logger.info(f"Uploaded PDF for report {report_id}")
            return pdf_url
            
        except Exception as e:
            logger.error(f"Error uploading PDF: {e}")
            raise
    
    def upload_json(self, 
                    report_data: Dict[str, Any],
                    report_id: str) -> str:
        """
        Upload report JSON data to S3
        
        Args:
            report_data: Report data dictionary
            report_id: Unique report identifier
            
        Returns:
            URL of uploaded JSON
        """
        try:
            # Convert to JSON
            json_data = json.dumps(report_data, indent=2)
            
            # Generate S3 key
            json_key = f"reports/{report_id}/report_data.json"
            
            # Upload JSON
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=json_key,
                Body=json_data.encode('utf-8'),
                ContentType='application/json',
                CacheControl='max-age=3600'  # Cache for 1 hour
            )
            
            json_url = f"{self.base_url}/{json_key}"
            logger.info(f"Uploaded JSON data for report {report_id}")
            return json_url
            
        except Exception as e:
            logger.error(f"Error uploading JSON: {e}")
            raise
    
    def delete_report(self, report_id: str) -> bool:
        """
        Delete all files associated with a report
        
        Args:
            report_id: Unique report identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # List all objects with the report prefix
            prefix = f"reports/{report_id}/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            # Delete all objects
            if 'Contents' in response:
                objects = [{'Key': obj['Key']} for obj in response['Contents']]
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects}
                )
                logger.info(f"Deleted {len(objects)} files for report {report_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting report: {e}")
            return False
    
    def _create_thumbnail(self, image_data: bytes, max_size: tuple = (400, 400)) -> bytes:
        """
        Create a thumbnail from image data
        
        Args:
            image_data: Original image bytes
            max_size: Maximum dimensions for thumbnail
            
        Returns:
            Thumbnail image bytes
        """
        try:
            # Open image with PIL
            img = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            
            # Create thumbnail
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            output.seek(0)
            
            return output.read()
            
        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            # Return original if thumbnail creation fails
            return image_data
    
    def _get_content_type(self, extension: str) -> str:
        """Get appropriate content type for file extension"""
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.pdf': 'application/pdf',
            '.json': 'application/json',
            '.txt': 'text/plain'
        }
        return content_types.get(extension.lower(), 'application/octet-stream')
    
    def test_connection(self) -> bool:
        """Test S3 connection and bucket access"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("S3 connection test successful")
            return True
        except ClientError as e:
            logger.error(f"S3 connection test failed: {e}")
            return False

# Create a singleton instance
cloud_storage = None

def get_cloud_storage() -> CloudStorageService:
    """Get or create the cloud storage service instance"""
    global cloud_storage
    if cloud_storage is None:
        cloud_storage = CloudStorageService()
    return cloud_storage