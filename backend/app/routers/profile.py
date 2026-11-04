from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from ..database import get_db
from ..security import end_sessions, get_current_user, get_password_hash, issue_token, verify_password
from .. import models, rate_limit, schemas, crud
from ..permissions import require_staff
from ..rate_limit import limiter

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/student")
def get_student_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get the current user's profile details."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return schemas.UserProfile.model_validate(user)


@router.get("/student/{student_id}")
def get_student_profile_by_id(
    student_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Get the profile of a candidate in the staff member's organization."""
    candidate = crud.get_membership(db, student_id, membership.organization_id)
    if not candidate or candidate.role != models.ROLE_CANDIDATE:
        raise HTTPException(status_code=404, detail="Student not found")

    return schemas.UserProfile.model_validate(candidate.user)


@router.put("/student")
def update_student_profile(
    profile_update: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Update the current user's profile (full_name, date_of_birth, gender, language)."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only the fields sent change; language null means "use the organization's"
    for field, value in profile_update.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return schemas.UserProfile.model_validate(user)


TOO_MANY_PASSWORD_TRIES = "Too many wrong passwords. Wait 15 minutes, or sign out and reset your password."


@router.post("/change-password")
def change_student_password(
    password_change: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Change the current user's password. Every other session is signed out; this one gets a fresh token."""
    # Someone holding a stolen session must not be able to guess the password and keep the account
    failures = f"password-change-failed:{current_user.id}"
    limiter.check(failures, rate_limit.PASSWORD_CHANGE_FAILURES_PER_USER, TOO_MANY_PASSWORD_TRIES)

    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(password_change.old_password, user.hashed_password):
        limiter.add(failures)
        raise HTTPException(status_code=400, detail="Incorrect old password")
    limiter.clear(failures)

    user.hashed_password = get_password_hash(password_change.new_password)
    end_sessions(user)
    db.commit()

    return {"message": "Password updated successfully", **issue_token(user)}
