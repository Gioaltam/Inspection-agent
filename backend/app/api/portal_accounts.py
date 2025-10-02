from __future__ import annotations
import os
import secrets
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from pydantic import BaseModel, EmailStr, Field

from ..portal_models import SessionLocal, init_portal_tables, PortalClient, ClientPortalToken, PortalCode
from ..portal_security import hash_password, verify_password, create_access_token, get_current_portal_client

router = APIRouter()

# ensure tables exist at import time (safe for SQLite dev)
init_portal_tables()

# ---------- Schemas ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CreateCodeIn(BaseModel):
    portal_token: str = Field(..., description="Your existing portal token for that property/gallery")
    expires_in_days: int = Field(14, ge=1, le=365)
    note: str | None = Field(None, description="Optional note, e.g., property address")


class CreateCodeOut(BaseModel):
    code: str
    expires_at: datetime
    note: str | None = None


class LinkCodeIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=32)


class TokensOut(BaseModel):
    tokens: List[str]


# ---------- Helpers ----------
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no O/0/I/1 confusions


def new_code(n: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def get_admin_guard(request: Request):
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key:
        # Dev convenience: allow if not configured
        return
    provided = request.headers.get("x-admin-key")
    if provided != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden (admin key required)")


# ---------- Routes (Client) ----------
@router.post("/register", response_model=AuthOut)
def portal_register(payload: RegisterIn):
    db = SessionLocal()
    try:
        email_clean = payload.email.strip().lower()
        
        exists = db.query(PortalClient).filter(PortalClient.email == email_clean).first()
        if exists:
            raise HTTPException(status_code=409, detail="Email already registered")
        
        # Create new portal client
        client = PortalClient(
            email=email_clean,
            password_hash=hash_password(payload.password.strip()),
            full_name=payload.full_name or "",
            is_active=True,
            is_paid=False
        )
        
        db.add(client)
        db.commit()
        db.refresh(client)
        return AuthOut(access_token=create_access_token(client.id, client.email))
    finally:
        db.close()


@router.post("/login", response_model=AuthOut)
def portal_login(payload: LoginIn):
    db = SessionLocal()
    try:
        # Trim spaces from email for consistency
        email_clean = payload.email.strip().lower()
        client = db.query(PortalClient).filter(PortalClient.email == email_clean).first()
        
        # Try password as-is first, then with trimmed spaces if that fails
        password_valid = False
        if client:
            # First try with exact password
            password_valid = verify_password(payload.password, client.password_hash)
            
            # If that fails, try with trimmed password
            if not password_valid:
                password_valid = verify_password(payload.password.strip(), client.password_hash)
        
        if not client or not password_valid:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        return AuthOut(access_token=create_access_token(client.id, client.email))
    finally:
        db.close()


@router.get("/my-tokens", response_model=TokensOut)
def my_tokens(current=Depends(get_current_portal_client)):
    db = SessionLocal()
    try:
        rows = db.query(ClientPortalToken).filter(ClientPortalToken.client_id == current.id).all()
        return TokensOut(tokens=[r.portal_token for r in rows])
    finally:
        db.close()


@router.post("/link-code")
def link_code(payload: LinkCodeIn, current=Depends(get_current_portal_client)):
    db = SessionLocal()
    try:
        code = db.query(PortalCode).filter(PortalCode.code == payload.code.upper()).first()
        if not code:
            raise HTTPException(status_code=404, detail="Code not found")
        if code.expires_at and datetime.utcnow() > code.expires_at:
            raise HTTPException(status_code=410, detail="Code expired")
        # Single-use by default; allow re-link by same client
        if code.used_by_client_id and code.used_by_client_id != current.id:
            raise HTTPException(status_code=409, detail="Code already used")

        # Link token to client (upsert)
        existing = (
            db.query(ClientPortalToken)
            .filter(ClientPortalToken.client_id == current.id, ClientPortalToken.portal_token == code.portal_token)
            .first()
        )
        if not existing:
            db.add(ClientPortalToken(client_id=current.id, portal_token=code.portal_token))

        # Mark code as used by this client for audit
        code.used_by_client_id = current.id
        db.commit()
        return {"status": "linked", "portal_token": code.portal_token}
    finally:
        db.close()


# ---------- Routes (Admin) ----------
@router.post("/admin/portal-codes", response_model=CreateCodeOut)
def admin_create_portal_code(payload: CreateCodeIn, request: Request):
    get_admin_guard(request)

    db = SessionLocal()
    try:
        # make a unique 8-char code
        for _ in range(6):
            candidate = new_code(8)
            if not db.query(PortalCode).filter(PortalCode.code == candidate).first():
                code_str = candidate
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate a unique code")

        expires_at = datetime.utcnow() + timedelta(days=payload.expires_in_days)
        row = PortalCode(code=code_str, portal_token=payload.portal_token, note=payload.note, expires_at=expires_at)
        db.add(row)
        db.commit()
        return CreateCodeOut(code=code_str, expires_at=expires_at, note=payload.note)
    finally:
        db.close()
