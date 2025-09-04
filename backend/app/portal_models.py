from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey,
    UniqueConstraint, Text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class PortalClient(Base):
    __tablename__ = "portal_clients"
    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
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


def init_portal_tables():
    Base.metadata.create_all(bind=engine)

