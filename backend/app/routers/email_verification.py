"""Email verification (soft): a link confirms the address. Unverified accounts keep
working; confirming is what makes password reset by email trustworthy."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
import jwt
from sqlalchemy.orm import Session

from .. import models, notify, rate_limit, schemas
from ..database import get_db
from ..rate_limit import limiter
from ..security import ALGORITHM, SECRET_KEY, get_current_user
from .password_reset import _app_url

router = APIRouter(prefix="/verify-email", tags=["Auth"])

LINK_LIFETIME = timedelta(days=7)
PURPOSE = "verify-email"
INVALID_LINK = "This confirmation link is invalid or has expired. Sign in and send a new one."


def make_token(user: models.User) -> str:
    """Signed, not stored. It names the email, so changing the address kills old links."""
    claims = {"sub": str(user.id), "email": user.email, "purpose": PURPOSE, "exp": datetime.now(timezone.utc) + LINK_LIFETIME}
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


def send_verification(user: models.User, background: BackgroundTasks) -> None:
    link = f"{_app_url()}/verify-email/{make_token(user)}"
    name = user.full_name or user.email
    text = (
        f"Hi {name},\n\n"
        f"Confirm that {user.email} is your email address:\n{link}\n\n"
        "The link works for 7 days. Confirming lets you reset your password by email if you forget it.\n\n"
        "If you didn't create a Fairpaper account, ignore this email.\n"
    )
    background.add_task(notify.send_email, user.email, "Confirm your email for Fairpaper", text)


@router.post("")
def verify_email(data: schemas.EmailVerification, db: Session = Depends(get_db)):
    """Confirm an address from the emailed link. Works signed in or not; repeat clicks are fine."""
    try:
        claims = jwt.decode(data.token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = UUID(claims.get("sub", ""))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # A sign-in token has no purpose claim, so it can't be used as a confirmation link
    if claims.get("purpose") != PURPOSE or not user or claims.get("email") != user.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
    return {"message": "Email confirmed.", "email": user.email}


@router.post("/resend")
def resend_verification(
    background: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
):
    """Send the confirmation link again to the signed-in user."""
    if current_user.email_verified_at is not None:
        return {"message": "Your email is already confirmed."}
    limiter.hit(f"verify-resend:{current_user.id}", rate_limit.VERIFY_RESEND_PER_USER, rate_limit.TOO_MANY)
    send_verification(current_user, background)
    return {"message": "Confirmation link sent."}
