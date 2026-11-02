"""Launch waitlist (PRD F27): visitors leave an email and get one message when Fairpaper opens.

The API only ever accepts emails; it never returns them, and the answer is the same whether
an address is new, already listed or caught by the honeypot. Reading and mailing the list is
`manage_waitlist.py`, run by the Fairpaper team.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, rate_limit, schemas
from ..database import get_db
from ..rate_limit import per_ip
from ..security import ALGORITHM, SECRET_KEY
from .password_reset import _app_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/waitlist", tags=["Waitlist"])

PURPOSE = "waitlist-unsubscribe"
JOINED = "You're on the list. We'll email you once, when Fairpaper opens."
UNSUBSCRIBED = "You're off the list. We won't email you about the launch."
INVALID_LINK = "This unsubscribe link isn't valid. Copy the whole link from the email and try again."


def unsubscribe_link(signup: models.WaitlistSignup) -> str:
    """Signed, not stored, and without an expiry: the link in a launch email must keep working."""
    token = jwt.encode({"sub": str(signup.id), "purpose": PURPOSE}, SECRET_KEY, algorithm=ALGORITHM)
    return f"{_app_url()}/waitlist/unsubscribe/{token}"


@router.post("", dependencies=[Depends(per_ip("waitlist", rate_limit.WAITLIST_PER_IP))])
def join_waitlist(data: schemas.WaitlistJoin, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if data.website:
        logger.info("Waitlist honeypot filled", extra={"fields": {"source": data.source}})
        return {"message": JOINED}
    existing = db.query(models.WaitlistSignup).filter(models.WaitlistSignup.email == email).first()
    if existing is None:
        db.add(models.WaitlistSignup(email=email, source=data.source, locale=data.locale))
        try:
            db.commit()
        except IntegrityError:  # the same email sent twice at once
            db.rollback()
    elif existing.unsubscribed_at is not None:
        existing.unsubscribed_at = None  # joining again after unsubscribing
        db.commit()
    return {"message": JOINED}


@router.post("/unsubscribe", dependencies=[Depends(per_ip("waitlist-unsubscribe", rate_limit.WAITLIST_PER_IP))])
def unsubscribe(data: schemas.WaitlistUnsubscribe, db: Session = Depends(get_db)):
    """A POST from the /waitlist/unsubscribe page, not a GET on the emailed link: mail
    scanners open links in advance, and that mustn't unsubscribe anyone."""
    try:
        claims = jwt.decode(data.token, SECRET_KEY, algorithms=[ALGORITHM])
        signup_id = UUID(claims.get("sub", ""))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    if claims.get("purpose") != PURPOSE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    signup = db.get(models.WaitlistSignup, signup_id)
    if signup and signup.unsubscribed_at is None:
        signup.unsubscribed_at = datetime.now(timezone.utc)
        db.commit()
    return {"message": UNSUBSCRIBED}
