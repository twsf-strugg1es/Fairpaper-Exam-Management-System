"""Password reset by email: request a link, then set a new password with it."""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, notify, rate_limit, schemas
from ..database import get_db
from ..rate_limit import limiter, per_ip
from ..security import end_sessions, get_password_hash

router = APIRouter(prefix="/password-reset", tags=["Auth"])

TOKEN_LIFETIME = timedelta(minutes=30)
REQUESTED = "If an account exists for that email, we've sent a link to reset the password."
INVALID_LINK = "This reset link is invalid or has expired. Ask for a new one."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


def _reset_email(user: models.User, link: str) -> tuple[str, str]:
    name = user.full_name or user.email
    text = (
        f"Hi {name},\n\n"
        f"Someone asked to reset the password for your Fairpaper account ({user.email}).\n\n"
        f"Set a new password here. The link works once, for the next 30 minutes:\n{link}\n\n"
        "If you didn't ask for this, ignore this email. Your password stays the same.\n"
    )
    return "Reset your Fairpaper password", text


@router.post("/request", dependencies=[Depends(per_ip("reset-request", rate_limit.RESET_REQUEST_PER_IP))])
def request_reset(data: schemas.PasswordResetRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Email a reset link. The answer is the same whether or not the account exists."""
    user = crud.get_user_by_email(db, data.email)
    account_key = f"reset-email:{data.email.lower()}"
    # Past the per-account limit nothing is sent, but the answer doesn't change: no flooding
    # an inbox, and no hint about which emails have accounts
    allowed = limiter.retry_after(account_key, rate_limit.RESET_EMAILS_PER_ACCOUNT) == 0
    if user and allowed:
        limiter.add(account_key)
        now = datetime.now(timezone.utc)
        # Only the newest link works
        db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.user_id == user.id, models.PasswordResetToken.used_at.is_(None)
        ).update({models.PasswordResetToken.used_at: now})
        token = secrets.token_urlsafe(32)
        db.add(models.PasswordResetToken(user_id=user.id, token_hash=_hash(token), expires_at=now + TOKEN_LIFETIME))
        db.commit()
        subject, text = _reset_email(user, f"{_app_url()}/reset-password/{token}")
        background.add_task(notify.send_email, user.email, subject, text)
    return {"message": REQUESTED}


@router.post("/confirm", dependencies=[Depends(per_ip("reset-confirm", rate_limit.RESET_CONFIRM_PER_IP))])
def confirm_reset(data: schemas.PasswordResetConfirm, db: Session = Depends(get_db)):
    """Set a new password with a link from the email. Each link works once."""
    now = datetime.now(timezone.utc)
    record = db.query(models.PasswordResetToken).filter(models.PasswordResetToken.token_hash == _hash(data.token)).first()
    expires_at = record.expires_at if record else None
    if expires_at is not None and expires_at.tzinfo is None:  # SQLite returns naive datetimes
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not record or record.used_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)

    user = record.user
    user.hashed_password = get_password_hash(data.new_password)
    end_sessions(user)  # whoever had the old password is signed out everywhere
    if user.email_verified_at is None:
        user.email_verified_at = now  # the link arrived at this inbox, so the address works
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user.id, models.PasswordResetToken.used_at.is_(None)
    ).update({models.PasswordResetToken.used_at: now})
    db.commit()
    limiter.clear(f"login-failed:{user.email.lower()}")  # a locked-out user can sign in straight away
    return {"message": "Password changed. Sign in with your new password."}
