import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from passlib.context import CryptContext
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .logging_config import bind_log_context

# Load environment variables from .env file
load_dotenv()

# Password hashing context: accept legacy bcrypt hashes for verification,
# but use pbkdf2_sha256 for new hashes by default.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    default="pbkdf2_sha256",
    deprecated="auto",
)

# JWT configuration. Tokens are signed with HMAC-SHA256, so a short key can be guessed offline from one token and
# then any account forged; RFC 7518 (section 3.2) asks for at least 32 bytes.
MIN_SECRET_KEY_LENGTH = 32
SECRET_KEY = os.getenv("SECRET_KEY") or ""
if len(SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
    problem = f"must be at least {MIN_SECRET_KEY_LENGTH} characters" if SECRET_KEY else "is not set"
    raise RuntimeError(
        f"SECRET_KEY {problem}. Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRES = timedelta(minutes=60)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plain password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token. `iat` keeps the microseconds, so a token issued straight after a password
    change is told apart from one issued just before it."""
    now = datetime.now(timezone.utc)
    to_encode = data.copy()
    to_encode.update({"exp": now + (expires_delta or timedelta(minutes=15)), "iat": now.timestamp()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def issue_token(user: models.User) -> dict:
    """A sign-in token. Roles are per organization, so it only identifies the user, by ID so that changing the
    email doesn't sign them out."""
    access_token = create_access_token(data={"sub": str(user.id)}, expires_delta=ACCESS_TOKEN_EXPIRES)
    return {"access_token": access_token, "token_type": "bearer"}


def end_sessions(user: models.User) -> None:
    """Every sign-in token issued until now stops working, refreshes included. Call it when the password changes,
    so whoever held a stolen token is signed out; the caller commits."""
    user.tokens_valid_after = datetime.now(timezone.utc)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.InvalidTokenError:
        return None


# OAuth2 configuration for bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """FastAPI dependency: validate JWT and return current user model."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception
    subject = payload.get("sub")
    # Emailed links (e.g. email confirmation) are signed with the same key but carry a
    # purpose; they must never work as a sign-in token
    if not subject or payload.get("purpose"):
        raise credentials_exception
    try:
        user = db.query(models.User).filter(models.User.id == uuid.UUID(subject)).first()
    except ValueError:
        # Tokens issued before 2026-10-26 carry the email. Accepted for one release so nobody
        # is signed out by the upgrade; a refresh swaps them for an ID token, and they expire within the hour
        from . import crud  # imported here: crud imports this module, and this fallback is going away
        user = crud.get_user_by_email(db, subject) if "@" in subject else None
    if not user:
        raise credentials_exception
    cutoff = user.tokens_valid_after
    if cutoff is not None:
        cutoff = cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=timezone.utc)  # SQLite returns naive datetimes
        if float(payload.get("iat") or 0) < cutoff.timestamp():
            raise credentials_exception  # issued before the password last changed
    bind_log_context(user_id=str(user.id))
    return user
