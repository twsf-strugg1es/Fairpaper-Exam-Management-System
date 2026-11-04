"""Organizations: joining, the current organization's settings, members and groups."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from .. import crud, invites, models, notify, schemas
from ..permissions import get_current_membership, require_manager, require_staff
from ..security import get_current_user
from .. import rate_limit
from ..rate_limit import limiter

router = APIRouter(tags=["Organizations"])


@router.post("/organizations", response_model=schemas.MembershipOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    data: schemas.OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a new organization owned by the current user."""
    org = crud.create_organization(db, data.name.strip(), current_user)
    return crud.membership_out(crud.get_membership(db, current_user.id, org.id))


@router.post("/organizations/join", response_model=schemas.MembershipOut)
def join_organization(
    data: schemas.JoinRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Join an organization as a candidate with an organization or group join code."""
    limiter.hit(f"join:{current_user.id}", rate_limit.JOIN_PER_USER, rate_limit.TOO_MANY)
    try:
        membership = crud.join_with_code(db, current_user, data.join_code.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud.membership_out(membership)


# --- The current organization (selected with the X-Organization-Id header) ---

def _locale(org: models.Organization) -> dict:
    return {
        "country": org.country,
        "default_language": org.default_language,
        "timezone": org.timezone,
        "currency": org.currency,
    }


@router.get("/org")
def get_current_organization(membership: models.Membership = Depends(get_current_membership)):
    """The current organization; managers also get its join code."""
    org = membership.organization
    result = {"id": str(org.id), "name": org.name, "role": membership.role, **_locale(org)}
    if membership.role in models.MANAGER_ROLES:
        result["join_code"] = org.join_code
    return result


@router.get("/org/setup")
def setup_progress(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """The four "Get started" steps for a new organization, and whether each is done."""
    org_id = membership.organization_id
    counts = {
        "students": db.query(models.Membership).filter(
            models.Membership.organization_id == org_id, models.Membership.role == models.ROLE_CANDIDATE
        ).count(),
        "groups": db.query(models.Group).filter(models.Group.organization_id == org_id).count(),
        "questions": db.query(models.Question).filter(models.Question.organization_id == org_id).count(),
        "exams": db.query(models.Exam).filter(models.Exam.organization_id == org_id).count(),
    }
    steps = {name: count > 0 for name, count in counts.items()}
    return {"steps": steps, "counts": counts, "done": all(steps.values())}


@router.patch("/org")
def update_organization(
    data: schemas.OrganizationUpdate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Rename the organization or change its locale. Only the fields sent change."""
    org = membership.organization
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name") is not None:
        org.name = changes["name"].strip()
    for field in ("default_language", "timezone"):  # required columns: null means "leave it"
        if changes.get(field) is not None:
            setattr(org, field, changes[field])
    for field in ("country", "currency"):  # optional columns: empty clears
        if field in changes:
            setattr(org, field, changes[field])
    db.commit()
    return {"id": str(org.id), "name": org.name, **_locale(org)}


@router.post("/org/join-code/regenerate")
def regenerate_org_join_code(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Issue a new join code; the old one stops working."""
    membership.organization.join_code = models.generate_join_code()
    db.commit()
    return {"join_code": membership.organization.join_code}


# --- Members ---

INVITE_ACCEPTED = "They've already set a password. If they forgot it, they can use “Forgot password?” on the sign-in page."

def _get_org_member(db: Session, user_id: UUID, membership: models.Membership) -> models.Membership:
    member = crud.get_membership(db, user_id, membership.organization_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


def _check_role_change(actor: models.Membership, target: models.Membership | None, new_role: str | None) -> None:
    """Only owners can grant, change or remove the owner role."""
    if new_role is not None and new_role not in models.ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(models.ROLES)}")
    touches_owner = new_role == models.ROLE_OWNER or (target is not None and target.role == models.ROLE_OWNER)
    if touches_owner and actor.role != models.ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Only owners can manage owners")


def _ensure_another_owner(db: Session, target: models.Membership) -> None:
    """An organization must always keep at least one owner."""
    if target.role != models.ROLE_OWNER:
        return
    owners = (
        db.query(models.Membership)
        .filter(
            models.Membership.organization_id == target.organization_id,
            models.Membership.role == models.ROLE_OWNER,
        )
        .count()
    )
    if owners <= 1:
        raise HTTPException(status_code=400, detail="The organization must keep at least one owner")


@router.get("/org/members")
def list_members(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Everyone in the organization, staff and candidates."""
    members = (
        db.query(models.Membership)
        .options(joinedload(models.Membership.user), joinedload(models.Membership.groups))
        .filter(models.Membership.organization_id == membership.organization_id)
        .all()
    )
    pending = invites.pending_invites(db, [m.user_id for m in members])
    return [
        {
            "user_id": str(m.user_id),
            "email": m.user.email,
            "full_name": m.user.full_name,
            "role": m.role,
            "groups": [{"id": str(g.id), "name": g.name} for g in m.groups],
            "joined_at": crud.iso(m.created_at),
            "invite_pending": m.user_id in pending,
        }
        for m in sorted(members, key=lambda m: (models.ROLES.index(m.role), m.user.email))
    ]


@router.post("/org/members", status_code=status.HTTP_201_CREATED)
def add_member(
    data: schemas.MemberAdd,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Add someone by email, e.g. to make them an examiner. Without an account, they're invited."""
    _check_role_change(membership, None, data.role)
    org_name = membership.organization.name
    user = crud.get_user_by_email(db, data.email)
    invited = user is None
    if invited:
        user, link = invites.create_invited_user(db, data.email.strip().lower(), data.full_name, datetime.now(timezone.utc))
        email = invites.invite_email(org_name, user, link, data.role)
    elif crud.get_membership(db, user.id, membership.organization_id):
        raise HTTPException(status_code=400, detail="Already a member of this organization")
    else:
        email = invites.added_email(org_name, user, data.role)
    db.add(models.Membership(user_id=user.id, organization_id=membership.organization_id, role=data.role))
    db.commit()
    background.add_task(notify.send_email, *email)
    return {"user_id": str(user.id), "email": user.email, "role": data.role, "invited": invited}


@router.post("/org/members/{user_id}/invite")
def resend_invite(
    user_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Send a new invite link to someone who hasn't set a password yet. Older links stop working."""
    target = _get_org_member(db, user_id, membership)
    _check_role_change(membership, target, None)
    if target.user_id not in invites.pending_invites(db, [target.user_id]):
        raise HTTPException(status_code=400, detail=INVITE_ACCEPTED)
    limiter.hit(f"invite-email:{target.user_id}", rate_limit.INVITE_RESEND_PER_USER, rate_limit.TOO_MANY_INVITES)
    link = invites.reissue_invite(db, target.user, datetime.now(timezone.utc))
    db.commit()
    background.add_task(notify.send_email, *invites.invite_email(membership.organization.name, target.user, link, target.role))
    return {"status": "success", "email": target.user.email}


@router.patch("/org/members/{user_id}")
def change_member_role(
    user_id: UUID,
    data: schemas.MemberUpdate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    target = _get_org_member(db, user_id, membership)
    _check_role_change(membership, target, data.role)
    if data.role != models.ROLE_OWNER:
        _ensure_another_owner(db, target)
    target.role = data.role
    if data.role != models.ROLE_CANDIDATE:
        target.groups = []  # groups are for candidates
    db.commit()
    return {"user_id": str(user_id), "role": target.role}


@router.delete("/org/members/{user_id}")
def remove_member(
    user_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Remove someone from the organization. Their account and past results are kept."""
    target = _get_org_member(db, user_id, membership)
    _check_role_change(membership, target, None)
    _ensure_another_owner(db, target)
    db.delete(target)
    db.commit()
    return {"status": "success"}


# --- Groups ---

def _get_org_group(db: Session, group_id: UUID, membership: models.Membership) -> models.Group:
    group = (
        db.query(models.Group)
        .filter(models.Group.id == group_id, models.Group.organization_id == membership.organization_id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def _group_out(group: models.Group) -> schemas.GroupOut:
    return schemas.GroupOut(id=group.id, name=group.name, join_code=group.join_code, member_count=len(group.members))


def _save_group(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="A group with that name already exists")


@router.get("/org/groups", response_model=list[schemas.GroupOut])
def list_groups(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    groups = (
        db.query(models.Group)
        .options(joinedload(models.Group.members))
        .filter(models.Group.organization_id == membership.organization_id)
        .order_by(models.Group.name)
        .all()
    )
    return [_group_out(g) for g in groups]


@router.post("/org/groups", response_model=schemas.GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    data: schemas.GroupCreate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    group = models.Group(organization_id=membership.organization_id, name=data.name.strip())
    db.add(group)
    _save_group(db)
    db.refresh(group)
    return _group_out(group)


@router.patch("/org/groups/{group_id}", response_model=schemas.GroupOut)
def rename_group(
    group_id: UUID,
    data: schemas.GroupCreate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    group = _get_org_group(db, group_id, membership)
    group.name = data.name.strip()
    _save_group(db)
    return _group_out(group)


@router.delete("/org/groups/{group_id}")
def delete_group(
    group_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Delete a group. Exams that targeted only this group become open to the whole organization."""
    db.delete(_get_org_group(db, group_id, membership))
    db.commit()
    return {"status": "success"}


@router.post("/org/groups/{group_id}/join-code/regenerate", response_model=schemas.GroupOut)
def regenerate_group_join_code(
    group_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    group = _get_org_group(db, group_id, membership)
    group.join_code = models.generate_join_code()
    db.commit()
    return _group_out(group)


@router.post("/org/groups/{group_id}/members", response_model=schemas.GroupOut)
def add_group_members(
    group_id: UUID,
    data: schemas.GroupMembersUpdate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Put existing candidates of the organization into a group."""
    group = _get_org_group(db, group_id, membership)
    for user_id in data.user_ids:
        candidate = crud.get_membership(db, user_id, membership.organization_id)
        if not candidate or candidate.role != models.ROLE_CANDIDATE:
            raise HTTPException(status_code=400, detail=f"{user_id} is not a candidate in this organization")
        if candidate not in group.members:
            group.members.append(candidate)
    db.commit()
    return _group_out(group)


@router.delete("/org/groups/{group_id}/members/{user_id}", response_model=schemas.GroupOut)
def remove_group_member(
    group_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    group = _get_org_group(db, group_id, membership)
    candidate = crud.get_membership(db, user_id, membership.organization_id)
    if candidate in group.members:
        group.members.remove(candidate)
        db.commit()
    return _group_out(group)
