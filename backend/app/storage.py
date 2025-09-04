# S3 storage service
from __future__ import annotations
import json
from typing import Optional, Dict
import boto3
from botocore.exceptions import ClientError


class StorageService:
    """
    Thin wrapper around an S3-compatible client (AWS S3, Cloudflare R2, Backblaze B2, MinIO).
    """

    def __init__(self, access_key: str, secret_key: str, bucket_name: str, endpoint_url: Optional[str] = None):
        self.bucket = bucket_name
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url or None,
        )

    # ---------- Upload helpers ----------

    def upload_file(
        self,
        file_path: str,
        key: str,
        content_type: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        extra: Dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        if tags:
            extra["Tagging"] = "&".join([f"{k}={v}" for k, v in tags.items()])

        self.s3.upload_file(file_path, self.bucket, key, ExtraArgs=extra if extra else None)
        return self.get_public_url(key)

    def upload_bytes(self, data: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return self.get_public_url(key)

    def upload_json(self, obj: dict, key: str) -> str:
        return self.upload_bytes(json.dumps(obj, indent=2).encode("utf-8"), key, "application/json")

    # ---------- Access helpers ----------

    def get_signed_url(self, key: str, expiration: int = 3600) -> str:
        try:
            return self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expiration,
            )
        except ClientError as e:
            raise RuntimeError(f"Failed to presign s3://{self.bucket}/{key}: {e}")

    def get_public_url(self, key: str) -> str:
        """
        Returns a URL that works for public buckets or S3-compatible endpoints.
        For private buckets, prefer get_signed_url().
        """
        endpoint = self.s3._endpoint.host.rstrip("/")
        return f"{endpoint}/{self.bucket}/{key}"

    # ---------- Optional: lifecycle (HQ PDF expiry) ----------

    def ensure_lifecycle_rule_expire_90d(self):
        """
        Adds a lifecycle rule that expires objects tagged lifecycle=expire-90-days in 90 days.
        Safe to call repeatedly.
        """
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
            self.s3.put_bucket_lifecycle_configuration(
                Bucket=self.bucket,
                LifecycleConfiguration=rules,
            )
        except ClientError as e:
            # Don't crash the app if lifecycle cannot be set (insufficient perms etc.)
            print(f"[storage] lifecycle setup warning: {e}")

