"""
Authentication and security utilities for the inspection portal.
Includes signed URLs, magic links, and email functionality.
"""

import os
import secrets
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration from environment
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
MAGIC_LINK_EXPIRY_MINUTES = int(os.getenv("MAGIC_LINK_EXPIRY_MINUTES", "30"))
SIGNED_URL_EXPIRY_HOURS = int(os.getenv("SIGNED_URL_EXPIRY_HOURS", "24"))

# Email configuration (using environment variables)
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@inspection-portal.com")
PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "http://localhost:8000")


class SignedURLGenerator:
    """Generate and validate signed, time-limited URLs for S3 or local files."""
    
    @staticmethod
    def generate_signed_url(resource_path: str, expiry_hours: int = None) -> str:
        """
        Generate a signed URL with expiration.
        
        Args:
            resource_path: Path to the resource (file)
            expiry_hours: Hours until expiration (default from env)
        
        Returns:
            Signed URL with expiration timestamp
        """
        if expiry_hours is None:
            expiry_hours = SIGNED_URL_EXPIRY_HOURS
        
        expiry = datetime.utcnow() + timedelta(hours=expiry_hours)
        expiry_timestamp = int(expiry.timestamp())
        
        # Create signature payload
        payload = f"{resource_path}:{expiry_timestamp}"
        signature = hmac.new(
            SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Build URL with signature
        params = {
            "expires": expiry_timestamp,
            "signature": signature
        }
        
        # For S3, you would construct the S3 URL here
        # For now, using local file serving
        base_url = f"{PORTAL_BASE_URL}/api/portal/signed/{resource_path}"
        return f"{base_url}?{urlencode(params)}"
    
    @staticmethod
    def validate_signed_url(resource_path: str, expires: str, signature: str) -> bool:
        """
        Validate a signed URL.
        
        Args:
            resource_path: Path to the resource
            expires: Expiration timestamp
            signature: URL signature
        
        Returns:
            True if valid and not expired, False otherwise
        """
        try:
            expiry_timestamp = int(expires)
            
            # Check if expired
            if datetime.utcnow().timestamp() > expiry_timestamp:
                return False
            
            # Validate signature
            payload = f"{resource_path}:{expiry_timestamp}"
            expected_signature = hmac.new(
                SECRET_KEY.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except (ValueError, TypeError):
            return False


class MagicLinkAuth:
    """Handle magic link authentication for email-based login."""
    
    @staticmethod
    def generate_magic_link(email: str, owner_id: str) -> tuple[str, str]:
        """
        Generate a magic link for email authentication.
        
        Args:
            email: User's email address
            owner_id: Owner ID in database
        
        Returns:
            Tuple of (magic_token, magic_link_url)
        """
        # Generate secure random token
        magic_token = secrets.token_urlsafe(32)
        
        # Create expiry timestamp
        expiry = datetime.utcnow() + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)
        
        # Store token data (in production, use Redis or database)
        token_data = {
            "email": email,
            "owner_id": owner_id,
            "expires": expiry.isoformat(),
            "token": magic_token
        }
        
        # Create signature for the token
        payload = json.dumps(token_data, sort_keys=True)
        signature = hmac.new(
            SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Build magic link URL
        params = {
            "token": magic_token,
            "sig": signature[:16]  # Short signature for URL
        }
        
        magic_link = f"{PORTAL_BASE_URL}/auth/verify?{urlencode(params)}"
        
        return magic_token, magic_link
    
    @staticmethod
    def validate_magic_token(token: str, stored_data: Dict[str, Any]) -> bool:
        """
        Validate a magic link token.
        
        Args:
            token: The magic token from URL
            stored_data: Stored token data from cache/database
        
        Returns:
            True if valid and not expired, False otherwise
        """
        try:
            # Check expiry
            expiry = datetime.fromisoformat(stored_data["expires"])
            if datetime.utcnow() > expiry:
                return False
            
            # Validate token matches
            return secrets.compare_digest(token, stored_data["token"])
            
        except (KeyError, ValueError):
            return False


class EmailService:
    """Send emails for magic links and notifications."""
    
    @staticmethod
    def send_magic_link_email(to_email: str, name: str, magic_link: str) -> bool:
        """
        Send magic link login email.
        
        Args:
            to_email: Recipient email
            name: Recipient name
            magic_link: The magic link URL
        
        Returns:
            True if sent successfully, False otherwise
        """
        subject = "Your Inspection Portal Login Link"
        
        # HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Hello {name},</h2>
            <p>You requested access to your Inspection Portal dashboard.</p>
            <p>Click the button below to log in securely:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{magic_link}" 
                   style="background-color: #007bff; color: white; padding: 12px 30px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    Access Your Portal
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">
                This link will expire in {MAGIC_LINK_EXPIRY_MINUTES} minutes for security reasons.
            </p>
            <p style="color: #666; font-size: 14px;">
                If you didn't request this login, please ignore this email.
            </p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="color: #999; font-size: 12px;">
                Or copy and paste this link: {magic_link}
            </p>
        </body>
        </html>
        """
        
        # Plain text fallback
        text_body = f"""
        Hello {name},
        
        You requested access to your Inspection Portal dashboard.
        
        Click this link to log in securely:
        {magic_link}
        
        This link will expire in {MAGIC_LINK_EXPIRY_MINUTES} minutes for security reasons.
        
        If you didn't request this login, please ignore this email.
        """
        
        return EmailService._send_email(to_email, subject, text_body, html_body)
    
    @staticmethod
    def send_report_notification(to_email: str, name: str, property_address: str, report_id: str) -> bool:
        """
        Send notification when a new report is available.
        
        Args:
            to_email: Recipient email
            name: Recipient name
            property_address: Property address
            report_id: Report ID
        
        Returns:
            True if sent successfully, False otherwise
        """
        subject = f"New Inspection Report Available - {property_address}"
        
        # Generate login link
        login_url = f"{PORTAL_BASE_URL}/login"
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Hello {name},</h2>
            <p>A new inspection report is available for your property:</p>
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <strong>Property:</strong> {property_address}<br>
                <strong>Report ID:</strong> {report_id}<br>
                <strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}
            </div>
            <p>
                <a href="{login_url}" 
                   style="background-color: #28a745; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Report
                </a>
            </p>
        </body>
        </html>
        """
        
        text_body = f"""
        Hello {name},
        
        A new inspection report is available for your property:
        
        Property: {property_address}
        Report ID: {report_id}
        Date: {datetime.now().strftime('%B %d, %Y')}
        
        Log in to view your report: {login_url}
        """
        
        return EmailService._send_email(to_email, subject, text_body, html_body)
    
    @staticmethod
    def _send_email(to_email: str, subject: str, text_body: str, html_body: str = None) -> bool:
        """
        Internal method to send email via SMTP.
        
        Args:
            to_email: Recipient email
            subject: Email subject
            text_body: Plain text body
            html_body: Optional HTML body
        
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = FROM_EMAIL
            msg['To'] = to_email
            
            # Add text part
            text_part = MIMEText(text_body, 'plain')
            msg.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, 'html')
                msg.attach(html_part)
            
            # Send email
            if SMTP_HOST and SMTP_HOST != "localhost":
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                    if SMTP_PORT == 587:
                        server.starttls()
                    if SMTP_USER and SMTP_PASSWORD:
                        server.login(SMTP_USER, SMTP_PASSWORD)
                    server.send_message(msg)
                return True
            else:
                # For development, just print the email
                print(f"[EMAIL] To: {to_email}")
                print(f"[EMAIL] Subject: {subject}")
                print(f"[EMAIL] Body: {text_body[:200]}...")
                return True
                
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False


# Pagination utilities
class PaginationParams:
    """Helper class for pagination parameters."""
    
    def __init__(self, page: int = 1, page_size: int = 20, max_page_size: int = 100):
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), max_page_size)
        self.offset = (self.page - 1) * self.page_size
        self.limit = self.page_size
    
    def paginate_query(self, query):
        """Apply pagination to a SQLAlchemy query."""
        return query.offset(self.offset).limit(self.limit)
    
    def get_pagination_metadata(self, total_count: int) -> dict:
        """Generate pagination metadata for response."""
        total_pages = (total_count + self.page_size - 1) // self.page_size
        
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": self.page < total_pages,
            "has_prev": self.page > 1
        }