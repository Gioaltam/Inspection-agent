# SQLAlchemy models
from __future__ import annotations
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Boolean, Text, JSON, Integer
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

# Portable Base (works with SQLite or Postgres)
Base = declarative_base()

def _uuid() -> str:
    """Store IDs as strings so it works on SQLite and Postgres without extra types."""
    return str(uuid.uuid4())

# ---------- Tables ----------

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False, default="")
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    client = relationship("Client", back_populates="user", uselist=False)


class Client(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=True)
    company_name = Column(String)
    contact_name = Column(String, nullable=False)
    name = Column(String, nullable=False)  # Added for compatibility
    email = Column(String, unique=True, nullable=False, index=True)  # Added for portal
    portal_token = Column(String, unique=True, index=True)  # Added for portal authentication
    # password_hash = Column(String)  # Commented out - column doesn't exist in database
    phone = Column(String)
    address = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="client")
    properties = relationship("Property", back_populates="client", foreign_keys="Property.client_id")


class Property(Base):
    __tablename__ = "properties"

    id = Column(String, primary_key=True, default=_uuid)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    address = Column(Text, nullable=False)
    label = Column(String)  # Display label for the property
    property_type = Column(String)        # residential, commercial, etc.
    details_json = Column(JSON)           # renamed from 'metadata' to avoid SA reserved name
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    client = relationship("Client", back_populates="properties")
    reports = relationship("Report", back_populates="property", order_by="Report.created_at.desc()")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=_uuid)
    property_id = Column(String, ForeignKey("properties.id"), nullable=False)
    address = Column(String)  # Denormalized for quick access
    inspection_date = Column(DateTime, nullable=True)
    
    # File paths
    pdf_path = Column(String)  # Local path to PDF
    json_path = Column(String)  # Local path to JSON
    photos = Column(JSON)  # Array of photo metadata

    pdf_standard_url = Column(String)
    pdf_hq_url = Column(String)               # optional; may expire
    pdf_hq_expires_at = Column(DateTime)

    json_url = Column(String) # structured report JSON for interactive viewer
    summary = Column(Text)

    critical_count = Column(Integer, default=0)
    important_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    property = relationship("Property", back_populates="reports")
    assets = relationship("Asset", back_populates="report")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True, default=_uuid)
    report_id = Column(String, ForeignKey("reports.id"), nullable=False)
    asset_type = Column(String)     # "thumbnail", "original_photo", etc.
    filename = Column(String, nullable=False)
    url = Column(String, nullable=False)
    asset_metadata = Column(JSON)   # renamed to avoid SQLAlchemy reserved name
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    report = relationship("Report", back_populates="assets")
