# Database session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings

# Create database engine with proper configuration
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite configuration for development
    # Use StaticPool to properly handle threading with SQLite
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=settings.DEBUG  # Log SQL statements in debug mode
    )
else:
    # PostgreSQL/other database configuration for production
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
        echo=settings.DEBUG  # Log SQL statements in debug mode
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
