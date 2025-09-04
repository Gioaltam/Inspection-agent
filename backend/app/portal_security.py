from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .portal_models import SessionLocal, PortalClient


PORTAL_JWT_SECRET = os.getenv("PORTAL_JWT_SECRET", "dev-secret-change-me")
ALGO = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(client_id: int, email: str) -> str:
    now = datetime.utcnow()
    exp = now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(client_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, PORTAL_JWT_SECRET, algorithm=ALGO)


def get_current_portal_client(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> PortalClient:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization",
        )

    token = creds.credentials
    try:
        payload = jwt.decode(token, PORTAL_JWT_SECRET, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        client_id_raw = payload.get("sub", "0")
        client_id = int(client_id_raw)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    db = SessionLocal()
    try:
        # Prefer SA 2.0 style session.get
        client = db.get(PortalClient, client_id)
        if not client or not client.is_active:
            raise HTTPException(status_code=401, detail="Account disabled or not found")
        return client
    finally:
        db.close()

