"""
Test script for cloud storage functionality
Run this after setting up AWS credentials in .env
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from backend.app.cloud_storage import CloudStorageService
from PIL import Image
import io

def create_test_image():
    """Create a simple test image"""
    img = Image.new('RGB', (800, 600), color='blue')
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def test_cloud_storage():
    """Test cloud storage operations"""
    print("=" * 60)
    print("CLOUD STORAGE TEST")
    print("=" * 60)
    
    # Check environment variables
    print("\n1. Checking environment variables...")
    aws_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
    bucket = os.getenv('S3_BUCKET_NAME')
    
    if not aws_key or aws_key == 'YOUR_ACCESS_KEY_HERE':
        print("❌ AWS_ACCESS_KEY_ID not configured in .env")
        print("   Please add your AWS credentials to the .env file")
        return False
    
    if not aws_secret or aws_secret == 'YOUR_SECRET_KEY_HERE':
        print("❌ AWS_SECRET_ACCESS_KEY not configured in .env")
        print("   Please add your AWS credentials to the .env file")
        return False
    
    print(f"✅ AWS credentials found")
    print(f"✅ Bucket name: {bucket}")
    
    try:
        # Initialize cloud storage
        print("\n2. Initializing cloud storage service...")
        storage = CloudStorageService()
        print("✅ Cloud storage service initialized")
        
        # Test connection
        print("\n3. Testing S3 connection...")
        if storage.test_connection():
            print("✅ Successfully connected to S3 bucket")
        else:
            print("❌ Failed to connect to S3 bucket")
            print("   Please check your AWS credentials and bucket name")
            return False
        
        # Upload test image
        print("\n4. Uploading test image...")
        test_image = create_test_image()
        result = storage.upload_photo(
            test_image,
            report_id="test_report_001",
            photo_index=1,
            create_thumbnail=True
        )
        
        print(f"✅ Photo uploaded successfully!")
        print(f"   Full URL: {result['full_url']}")
        print(f"   Thumbnail URL: {result['thumbnail_url']}")
        
        # Upload test JSON
        print("\n5. Uploading test JSON...")
        test_data = {
            "report_id": "test_report_001",
            "property": "123 Test Street",
            "date": "2024-01-01",
            "items": ["test1", "test2"]
        }
        json_url = storage.upload_json(test_data, "test_report_001")
        print(f"✅ JSON uploaded successfully!")
        print(f"   URL: {json_url}")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nYour cloud storage is configured correctly.")
        print("You can now view your uploaded files at:")
        print(f"  {result['full_url']}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nPlease check:")
        print("1. Your AWS credentials are correct")
        print("2. Your S3 bucket exists and is accessible")
        print("3. Your bucket has the correct permissions")
        return False

if __name__ == "__main__":
    success = test_cloud_storage()
    sys.exit(0 if success else 1)