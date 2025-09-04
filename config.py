"""
Unified Configuration System for Inspection Agent
Central configuration management for all components
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)


class Config:
    """Central configuration class"""
    
    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Application
    APP_NAME = "Inspection Agent"
    APP_VERSION = "1.0.0"
    
    # Paths
    BASE_DIR = Path(__file__).parent
    WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace"))
    OUTPUTS_DIR = WORKSPACE_DIR / "outputs"
    INCOMING_DIR = WORKSPACE_DIR / "incoming"
    CACHE_DIR = Path(".cache")
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///inspection_portal.db")
    DB_PATH = WORKSPACE_DIR / "inspection_portal.db"
    
    # API Configuration
    BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
    PORTAL_EXTERNAL_BASE_URL = os.getenv("PORTAL_EXTERNAL_BASE_URL", "http://localhost:8000")
    API_KEY = os.getenv("API_KEY", "")
    
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-use-secrets-token-hex-32")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7
    
    # Token TTL
    TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "720"))  # 30 days default
    UPLOAD_TOKEN_TTL_HOURS = int(os.getenv("UPLOAD_TOKEN_TTL_HOURS", "48"))
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "500"))
    
    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", None)  # For S3-compatible services
    USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
    
    # Email Configuration
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
    ENABLE_EMAIL_NOTIFICATIONS = os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "false").lower() == "true"
    
    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
    
    # Feature Flags
    ENABLE_AI_ANALYSIS = os.getenv("ENABLE_AI_ANALYSIS", "true").lower() == "true"
    ENABLE_PDF_GENERATION = os.getenv("ENABLE_PDF_GENERATION", "true").lower() == "true"
    ENABLE_PARALLEL_PROCESSING = os.getenv("ENABLE_PARALLEL_PROCESSING", "true").lower() == "true"
    
    # Processing Configuration
    JOB_CONCURRENCY = int(os.getenv("JOB_CONCURRENCY", "1"))
    ANALYSIS_CONCURRENCY = int(os.getenv("ANALYSIS_CONCURRENCY", "3"))
    MAX_IMAGE_SIZE_MB = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))
    SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE = WORKSPACE_DIR / "inspection_agent.log"
    
    # Server Configuration
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
    WORKERS = int(os.getenv("WORKERS", "4"))
    
    # Gallery Server
    GALLERY_HOST = os.getenv("GALLERY_HOST", "0.0.0.0")
    GALLERY_PORT = int(os.getenv("GALLERY_PORT", "8005"))
    
    # Employee Settings
    DEFAULT_EMPLOYEE_ID = os.getenv("DEFAULT_EMPLOYEE_ID", "employee_001")
    REQUIRE_EMPLOYEE_AUTH = os.getenv("REQUIRE_EMPLOYEE_AUTH", "false").lower() == "true"
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist"""
        for dir_path in [cls.WORKSPACE_DIR, cls.OUTPUTS_DIR, cls.INCOMING_DIR, cls.CACHE_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_database_url(cls) -> str:
        """Get properly formatted database URL"""
        if cls.DATABASE_URL.startswith("sqlite"):
            return cls.DATABASE_URL
        # Add any PostgreSQL or MySQL specific formatting here
        return cls.DATABASE_URL
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production mode"""
        return cls.ENVIRONMENT.lower() == "production"
    
    @classmethod
    def is_development(cls) -> bool:
        """Check if running in development mode"""
        return cls.ENVIRONMENT.lower() == "development"
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        errors = []
        
        if cls.ENABLE_AI_ANALYSIS and not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when AI analysis is enabled")
        
        if cls.USE_S3 and not (cls.AWS_ACCESS_KEY_ID and cls.AWS_SECRET_ACCESS_KEY):
            errors.append("AWS credentials required when S3 is enabled")
        
        if cls.ENABLE_EMAIL_NOTIFICATIONS and not (cls.SMTP_USER and cls.SMTP_PASSWORD):
            errors.append("SMTP credentials required when email notifications are enabled")
        
        if cls.is_production() and cls.SECRET_KEY == "change-this-in-production-use-secrets-token-hex-32":
            errors.append("SECRET_KEY must be changed in production")
        
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True
    
    @classmethod
    def to_dict(cls) -> dict:
        """Export configuration as dictionary (excluding sensitive values)"""
        return {
            "environment": cls.ENVIRONMENT,
            "debug": cls.DEBUG,
            "app_name": cls.APP_NAME,
            "app_version": cls.APP_VERSION,
            "enable_ai_analysis": cls.ENABLE_AI_ANALYSIS,
            "enable_pdf_generation": cls.ENABLE_PDF_GENERATION,
            "enable_email_notifications": cls.ENABLE_EMAIL_NOTIFICATIONS,
            "use_s3": cls.USE_S3,
            "cors_origins": cls.CORS_ORIGINS,
            "host": cls.HOST,
            "port": cls.PORT,
            "gallery_port": cls.GALLERY_PORT,
        }


# Create convenience instance
config = Config()

# Ensure directories on import
config.ensure_directories()


if __name__ == "__main__":
    # Test configuration
    print("Configuration Status:")
    print("-" * 40)
    
    if config.validate():
        print("✓ Configuration is valid")
    else:
        print("✗ Configuration has errors")
    
    print("\nCurrent Settings:")
    for key, value in config.to_dict().items():
        print(f"  {key}: {value}")