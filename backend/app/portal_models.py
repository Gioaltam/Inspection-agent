from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey,
    UniqueConstraint, Text
)
from sqlalchemy.orm import relationship

# Use the same database and Base from the main models
from .database import engine, SessionLocal
from .models import Base


class PortalClient(Base):
    __tablename__ = "portal_clients"
    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    is_paid = Column(Boolean, default=False)  # Has client paid for access
    payment_date = Column(DateTime, nullable=True)  # When payment was made
    payment_amount = Column(String(50), nullable=True)  # Payment amount for records
    stripe_customer_id = Column(String(255), nullable=True)  # For Stripe integration
    properties_data = Column(Text, nullable=True)  # JSON string of properties data
    created_at = Column(DateTime, default=datetime.utcnow)

    tokens = relationship("ClientPortalToken", back_populates="client")


class ClientPortalToken(Base):
    __tablename__ = "portal_client_tokens"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("portal_clients.id"), nullable=False)
    portal_token = Column(String(255), nullable=False)  # your existing portal token string
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("PortalClient", back_populates="tokens")
    __table_args__ = (UniqueConstraint("client_id", "portal_token", name="uq_client_token"),)


class PortalCode(Base):
    """
    A short code (e.g., 8 chars) the admin generates that maps to an existing portal token.
    Client enters this code to link that token to their account.
    """
    __tablename__ = "portal_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, index=True, nullable=False)
    portal_token = Column(String(255), nullable=False)
    note = Column(Text, nullable=True)  # optional admin note (e.g., property address)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    used_by_client_id = Column(Integer, ForeignKey("portal_clients.id"), nullable=True)


# Tables are now created in main.py with all other models
def init_portal_tables():
    pass  # No longer needed - tables created in main.py

