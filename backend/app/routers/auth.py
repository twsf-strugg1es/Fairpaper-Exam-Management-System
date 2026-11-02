from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from .. import crud, schemas, models
from ..security import get_current_user, issue_token, verify_password
from .. import rate_limit
from ..rate_limit import limiter, per_ip
from .email_verification import send_verification

router = APIRouter(tags=["Auth"])



ACCOUNT_LOCKED = "Too many failed sign-ins for this account. Wait 15 minutes or reset your password."


@router.post("/token", dependencies=[Depends(per_ip("login", rate_limit.LOGIN_PER_IP))])
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # OAuth2PasswordRequestForm uses field name "username"; we treat it as email
    account_key = f"login-failed:{form_data.username.strip().lower()}"
    limiter.check(account_key, rate_limit.LOGIN_FAILURES_PER_ACCOUNT, ACCOUNT_LOCKED)
    user = crud.get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        limiter.add(account_key)  # counted for unknown emails too, so the limit doesn't reveal which exist
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        )
    limiter.clear(account_key)
    return issue_token(user)


@router.post("/token/refresh")
def refresh_access_token(current_user: models.User = Depends(get_current_user)):
    """Swap a still-valid token for a fresh one, so long sessions (e.g. exams) don't expire mid-way."""
    return issue_token(current_user)


def _user_with_memberships(user: models.User) -> schemas.UserWithMemberships:
    return schemas.UserWithMemberships(
        **schemas.User.model_validate(user).model_dump(),
        memberships=[
            crud.membership_out(m)
            for m in sorted(user.memberships, key=lambda m: m.organization.name.lower())
        ],
    )


@router.get("/me", response_model=schemas.UserWithMemberships)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    """Get the current user and the organizations they belong to."""
    return _user_with_memberships(current_user)


def _ensure_email_free(db: Session, email: str) -> None:
    if crud.get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )


@router.post(
    "/signup", response_model=schemas.UserWithMemberships, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_ip("signup", rate_limit.SIGNUP_PER_IP))],
)
def signup(user_data: schemas.CandidateSignup, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Public signup. With a join code, the new user also becomes a candidate in that organization."""
    _ensure_email_free(db, user_data.email)

    # Check the code before creating the account, so a typo doesn't leave a half-finished signup
    if user_data.join_code and not crud.find_join_code(db, user_data.join_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid join code")

    new_user = crud.create_user(db, user_data)
    if user_data.join_code:
        crud.join_with_code(db, new_user, user_data.join_code)
        db.refresh(new_user)
    send_verification(new_user, background)
    return _user_with_memberships(new_user)


@router.post(
    "/signup/organization", response_model=schemas.UserWithMemberships, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_ip("org-signup", rate_limit.ORG_SIGNUP_PER_IP))],
)
def signup_organization(data: schemas.OrganizationSignup, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Create a new organization together with its owner's account."""
    _ensure_email_free(db, data.email)
    owner = crud.create_user(db, data, commit=False)
    crud.create_organization(db, data.organization_name.strip(), owner, locale=data)
    db.refresh(owner)
    send_verification(owner, background)
    return _user_with_memberships(owner)
