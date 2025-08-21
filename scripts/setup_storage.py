# S3 lifecycle rules
"""
One-time helper to create/configure your S3-style bucket with:
- CORS (so the web viewer can GET files)
- A lifecycle rule to expire HQ PDFs (tagged lifecycle=expire-90-days) after 90 days

Usage:
    python scripts/setup_storage.py
Requires env vars in backend/.env (S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_NAME, S3_ENDPOINT_URL?)
"""
from __future__ import annotations
import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

def main():
    # load env (supports running from project root or backend/)
    load_dotenv(dotenv_path=os.path.join("backend", ".env"))
    load_dotenv()  # fall back

    access = os.getenv("S3_ACCESS_KEY") or ""
    secret = os.getenv("S3_SECRET_KEY") or ""
    bucket = os.getenv("S3_BUCKET_NAME") or ""
    endpoint = os.getenv("S3_ENDPOINT_URL") or None

    if not (access and secret and bucket):
        raise SystemExit("Missing S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET_NAME in backend/.env")

    s3 = boto3.client("s3", aws_access_key_id=access, aws_secret_access_key=secret, endpoint_url=endpoint or None)

    # Ensure bucket exists
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"Bucket '{bucket}' exists.")
    except ClientError:
        try:
            s3.create_bucket(Bucket=bucket)
            print(f"Created bucket '{bucket}'.")
        except ClientError as e:
            raise SystemExit(f"Failed to create bucket: {e}")

    # Lifecycle: expire HQ PDFs
    rules = {
        "Rules": [
            {
                "ID": "expire-hq-pdfs",
                "Status": "Enabled",
                "Filter": {"Tag": {"Key": "lifecycle", "Value": "expire-90-days"}},
                "Expiration": {"Days": 90},
            }
        ]
    }
    try:
        s3.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration=rules)
        print("Lifecycle rule applied.")
    except ClientError as e:
        print(f"Warning: could not set lifecycle: {e}")

    # CORS: allow web access
    cors = {
        "CORSRules": [
            {
                "AllowedHeaders": ["*"],
                "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
                "AllowedOrigins": ["*"],  # tighten for production
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3000,
            }
        ]
    }
    try:
        s3.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors)
        print("CORS configuration applied.")
    except ClientError as e:
        print(f"Warning: could not set CORS: {e}")

if __name__ == "__main__":
    main()
