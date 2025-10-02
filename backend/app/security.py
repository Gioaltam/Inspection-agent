# backend/app/security.py
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain password against a hash"""
    return pwd_context.verify(plain_password, password_hash)