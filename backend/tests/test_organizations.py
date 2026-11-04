"""Tests for organizations: data isolation, roles, join codes, signup and member management."""
from datetime import datetime, timedelta, timezone

import pytest

from app import crud, models, schemas
from app.security import create_access_token


def headers_for(user, org=None):
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    if org is not None:
        headers["X-Organization-Id"] = str(org.id)
    return headers


def make_user(db, email, org=None, role=None):
    user = crud.create_user(db, schemas.UserCreate(email=email, password="Password123!"))
    if org is not None:
        db.add(models.Membership(user_id=user.id, organization_id=org.id, role=role))
        db.commit()
        db.refresh(user)
    return user


def make_org(db, name):
    org = models.Organization(name=name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def make_exam(db, org, title="Exam", groups=()):
    question = models.Question(
        organization_id=org.id, title=f"{title} question", complexity="easy",
        type="single_choice", options=["a", "b"], correct_answers="a", max_score=1,
    )
    now = datetime.now(timezone.utc)
    exam = models.Exam(
        organization_id=org.id, title=title, start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(hours=1), duration_minutes=30, is_published=True,
    )
    exam.questions.append(question)
    exam.groups.extend(groups)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@pytest.fixture
def two_orgs(test_db):
    """Two organizations, each with an owner, a candidate and an exam."""
    a, b = make_org(test_db, "Alpha Coaching"), make_org(test_db, "Beta Corp")
    return {
        "a": a, "b": b,
        "owner_a": make_user(test_db, "owner@a.com", a, models.ROLE_OWNER),
        "owner_b": make_user(test_db, "owner@b.com", b, models.ROLE_OWNER),
        "student_a": make_user(test_db, "student@a.com", a, models.ROLE_CANDIDATE),
        "student_b": make_user(test_db, "student@b.com", b, models.ROLE_CANDIDATE),
        "exam_a": make_exam(test_db, a, "Alpha exam"),
        "exam_b": make_exam(test_db, b, "Beta exam"),
    }


# --- Isolation between organizations ---

def test_staff_only_see_their_own_organizations_data(client, two_orgs):
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])

    exams = client.get("/admin/exams/", headers=h).json()
    questions = client.get("/admin/questions/", headers=h).json()
    students = client.get("/admin/students/", headers=h).json()

    assert [e["title"] for e in exams] == ["Alpha exam"]
    assert [q["title"] for q in questions] == ["Alpha exam question"]
    assert [s["email"] for s in students] == ["student@a.com"]


def test_staff_cannot_touch_another_organizations_records_by_id(client, two_orgs):
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])
    exam_b = two_orgs["exam_b"]

    assert client.post(f"/admin/exams/{exam_b.id}/publish", headers=h).status_code == 404
    assert client.delete(f"/admin/exams/{exam_b.id}", headers=h).status_code == 404
    assert client.get(f"/admin/exams/{exam_b.id}/attempts", headers=h).status_code == 404
    assert client.delete(f"/admin/questions/{exam_b.questions[0].id}", headers=h).status_code == 404
    assert client.delete(f"/admin/students/{two_orgs['student_b'].id}", headers=h).status_code == 404


def test_staff_cannot_see_attempts_in_another_organization(client, test_db, two_orgs):
    attempt = crud.create_exam_attempt(test_db, two_orgs["exam_b"].id, two_orgs["student_b"].id)
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])

    assert client.get(f"/admin/evaluations/attempts/{attempt.id}", headers=h).status_code == 404


def test_cannot_build_an_exam_from_another_organizations_questions(client, two_orgs):
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])
    now = datetime.now(timezone.utc)
    body = {
        "title": "Stolen", "start_time": now.isoformat(), "end_time": (now + timedelta(hours=1)).isoformat(),
        "duration_minutes": 30, "question_ids": [str(two_orgs["exam_b"].questions[0].id)],
    }

    assert client.post("/admin/exams/", json=body, headers=h).status_code == 404


def test_candidates_only_see_exams_of_the_selected_organization(client, two_orgs):
    h = headers_for(two_orgs["student_a"], two_orgs["a"])

    exams = client.get("/student/exams/", headers=h).json()

    assert [e["title"] for e in exams] == ["Alpha exam"]
    assert client.post(f"/student/exams/{two_orgs['exam_b'].id}/start", headers=h).status_code == 404


def test_cannot_act_in_an_organization_you_dont_belong_to(client, two_orgs):
    h = headers_for(two_orgs["owner_a"], two_orgs["b"])

    response = client.get("/admin/exams/", headers=h)

    assert response.status_code == 403


def test_organization_header_is_required(client, two_orgs):
    response = client.get("/admin/exams/", headers=headers_for(two_orgs["owner_a"]))

    assert response.status_code == 400


# --- Roles ---

def test_candidates_cannot_use_staff_endpoints(client, two_orgs):
    h = headers_for(two_orgs["student_a"], two_orgs["a"])

    assert client.get("/admin/exams/", headers=h).status_code == 403
    assert client.get("/org/members", headers=h).status_code == 403


def test_staff_cannot_take_exams(client, two_orgs):
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])

    assert client.get("/student/exams/", headers=h).status_code == 403


def test_examiners_manage_exams_but_not_members(client, test_db, two_orgs):
    examiner = make_user(test_db, "examiner@a.com", two_orgs["a"], models.ROLE_EXAMINER)
    h = headers_for(examiner, two_orgs["a"])

    assert client.get("/admin/exams/", headers=h).status_code == 200
    assert client.get("/org/members", headers=h).status_code == 403
    assert client.delete(f"/admin/students/{two_orgs['student_a'].id}", headers=h).status_code == 403


def test_admins_cannot_create_or_remove_owners(client, test_db, two_orgs):
    admin = make_user(test_db, "admin@a.com", two_orgs["a"], models.ROLE_ADMIN)
    h = headers_for(admin, two_orgs["a"])

    promote = client.patch(f"/org/members/{admin.id}", json={"role": "owner"}, headers=h)
    remove_owner = client.delete(f"/org/members/{two_orgs['owner_a'].id}", headers=h)

    assert promote.status_code == 403
    assert remove_owner.status_code == 403


def test_last_owner_cannot_leave_or_be_demoted(client, two_orgs):
    owner = two_orgs["owner_a"]
    h = headers_for(owner, two_orgs["a"])

    assert client.patch(f"/org/members/{owner.id}", json={"role": "admin"}, headers=h).status_code == 400
    assert client.delete(f"/org/members/{owner.id}", headers=h).status_code == 400


def test_add_existing_user_as_examiner(client, test_db, two_orgs):
    make_user(test_db, "teacher@x.com")
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])

    response = client.post("/org/members", json={"email": "teacher@x.com", "role": "examiner"}, headers=h)

    assert response.status_code == 201
    roles = {m["email"]: m["role"] for m in client.get("/org/members", headers=h).json()}
    assert roles["teacher@x.com"] == "examiner"


def test_removing_a_student_keeps_their_account(client, test_db, two_orgs):
    student = two_orgs["student_a"]
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])

    assert client.delete(f"/admin/students/{student.id}", headers=h).status_code == 200
    assert test_db.get(models.User, student.id) is not None
    assert client.get("/admin/students/", headers=h).json() == []


# --- Groups ---

def test_group_exams_are_only_visible_to_group_members(client, test_db, two_orgs):
    org = two_orgs["a"]
    batch = models.Group(organization_id=org.id, name="Batch 1")
    make_exam(test_db, org, "Batch exam", groups=[batch])
    h = headers_for(two_orgs["student_a"], org)
    owner_h = headers_for(two_orgs["owner_a"], org)

    assert [e["title"] for e in client.get("/student/exams/", headers=h).json()] == ["Alpha exam"]

    client.post(f"/org/groups/{batch.id}/members", json={"user_ids": [str(two_orgs["student_a"].id)]}, headers=owner_h)

    assert {e["title"] for e in client.get("/student/exams/", headers=h).json()} == {"Alpha exam", "Batch exam"}


def test_create_exam_for_a_group(client, test_db, two_orgs):
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])
    group = client.post("/org/groups", json={"name": "Morning batch"}, headers=h).json()
    now = datetime.now(timezone.utc)
    body = {
        "title": "Group exam", "start_time": now.isoformat(), "end_time": (now + timedelta(hours=1)).isoformat(),
        "duration_minutes": 30, "question_ids": [str(two_orgs["exam_a"].questions[0].id)],
        "group_ids": [group["id"]],
    }

    response = client.post("/admin/exams/", json=body, headers=h)

    assert response.status_code == 200, response.text
    assert [g["name"] for g in response.json()["groups"]] == ["Morning batch"]


def test_duplicate_group_names_are_rejected(client, two_orgs):
    h = headers_for(two_orgs["owner_a"], two_orgs["a"])
    client.post("/org/groups", json={"name": "Batch"}, headers=h)

    assert client.post("/org/groups", json={"name": "Batch"}, headers=h).status_code == 400


# --- Joining and signup ---

def test_join_with_organization_code(client, test_db, two_orgs):
    user = make_user(test_db, "new@x.com")

    # Codes are case-insensitive, so a student typing in lowercase still gets in
    response = client.post("/organizations/join", json={"join_code": two_orgs["a"].join_code.lower()},
                           headers=headers_for(user))

    assert response.status_code == 200
    assert response.json()["organization_name"] == "Alpha Coaching"
    assert response.json()["role"] == "candidate"


def test_join_with_group_code_adds_the_group(client, test_db, two_orgs):
    group = models.Group(organization_id=two_orgs["a"].id, name="Evening batch")
    test_db.add(group)
    test_db.commit()
    user = make_user(test_db, "new@x.com")

    client.post("/organizations/join", json={"join_code": group.join_code}, headers=headers_for(user))

    membership = crud.get_membership(test_db, user.id, two_orgs["a"].id)
    assert [g.name for g in membership.groups] == ["Evening batch"]


def test_invalid_join_code_is_rejected(client, test_db):
    user = make_user(test_db, "new@x.com")

    response = client.post("/organizations/join", json={"join_code": "nope"}, headers=headers_for(user))

    assert response.status_code == 400


def test_regenerated_join_code_replaces_the_old_one(client, test_db, two_orgs):
    old_code = two_orgs["a"].join_code
    client.post("/org/join-code/regenerate", headers=headers_for(two_orgs["owner_a"], two_orgs["a"]))
    user = make_user(test_db, "new@x.com")

    response = client.post("/organizations/join", json={"join_code": old_code}, headers=headers_for(user))

    assert response.status_code == 400


def test_signup_with_join_code(client, two_orgs):
    response = client.post("/signup", json={
        "email": "fresh@x.com", "password": "Password123!", "join_code": two_orgs["b"].join_code,
    })

    assert response.status_code == 201
    assert [m["organization_name"] for m in response.json()["memberships"]] == ["Beta Corp"]


def test_signup_with_bad_join_code_creates_no_account(client, test_db):
    response = client.post("/signup", json={"email": "fresh@x.com", "password": "Password123!", "join_code": "bad"})

    assert response.status_code == 400
    assert crud.get_user_by_email(test_db, "fresh@x.com") is None


def test_signup_organization_makes_an_owner(client):
    response = client.post("/signup/organization", json={
        "email": "boss@x.com", "password": "Password123!", "organization_name": "Gamma Institute",
    })

    assert response.status_code == 201
    memberships = response.json()["memberships"]
    assert [(m["organization_name"], m["role"]) for m in memberships] == [("Gamma Institute", "owner")]


def test_me_lists_all_memberships(client, test_db, two_orgs):
    user = two_orgs["student_a"]
    test_db.add(models.Membership(user_id=user.id, organization_id=two_orgs["b"].id, role=models.ROLE_EXAMINER))
    test_db.commit()

    me = client.get("/me", headers=headers_for(user)).json()

    assert [(m["organization_name"], m["role"]) for m in me["memberships"]] == [
        ("Alpha Coaching", "candidate"), ("Beta Corp", "examiner"),
    ]


def test_only_managers_see_the_join_code(client, two_orgs):
    owner_view = client.get("/org", headers=headers_for(two_orgs["owner_a"], two_orgs["a"])).json()
    student_view = client.get("/org", headers=headers_for(two_orgs["student_a"], two_orgs["a"])).json()

    assert owner_view["join_code"] == two_orgs["a"].join_code
    assert "join_code" not in student_view


def test_filter_questions_by_tag(client, test_db, two_orgs):
    org = two_orgs["a"]
    test_db.add(models.Question(organization_id=org.id, title="Tagged", complexity="easy", type="text",
                                correct_answers=None, max_score=1, tags=["history", "others"]))
    test_db.commit()

    response = client.get("/admin/questions/?tag=history", headers=headers_for(two_orgs["owner_a"], org))

    assert [q["title"] for q in response.json()] == ["Tagged"]
