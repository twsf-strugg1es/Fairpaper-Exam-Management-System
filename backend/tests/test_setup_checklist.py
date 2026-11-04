"""The "Get started" checklist (task 3.10): four steps, each done once the organization has one."""
from app import models
from tests.test_organizations import headers_for, make_exam, make_org, make_user


def progress(client, h):
    res = client.get("/org/setup", headers=h)
    assert res.status_code == 200, res.text
    return res.json()


def test_a_new_organization_has_everything_left_to_do(client, test_db):
    org = make_org(test_db, "Brand New School")
    owner = make_user(test_db, "owner@new.edu", org, models.ROLE_OWNER)

    data = progress(client, headers_for(owner, org))

    assert data["steps"] == {"students": False, "groups": False, "questions": False, "exams": False}
    assert data["done"] is False


def test_steps_tick_off_as_the_organization_fills_up(client, test_db):
    org = make_org(test_db, "Growing School")
    owner = make_user(test_db, "owner@grow.edu", org, models.ROLE_OWNER)
    h = headers_for(owner, org)

    make_user(test_db, "kid@grow.edu", org, models.ROLE_CANDIDATE)
    assert progress(client, h)["steps"]["students"] is True

    test_db.add(models.Group(organization_id=org.id, name="Class 9"))
    test_db.commit()
    make_exam(test_db, org, "First test")  # brings its own questions

    data = progress(client, h)
    assert data["steps"] == {"students": True, "groups": True, "questions": True, "exams": True}
    assert data["done"] is True and data["counts"]["students"] == 1


def test_counts_stay_inside_the_organization(client, test_db):
    busy = make_org(test_db, "Busy School")
    make_user(test_db, "kid@busy.edu", busy, models.ROLE_CANDIDATE)
    make_exam(test_db, busy, "Busy test")
    empty = make_org(test_db, "Empty School")
    owner = make_user(test_db, "owner@empty.edu", empty, models.ROLE_OWNER)

    assert progress(client, headers_for(owner, empty))["counts"] == {"students": 0, "groups": 0, "questions": 0, "exams": 0}


def test_staff_only(client, test_db):
    org = make_org(test_db, "Staff Only School")
    examiner = make_user(test_db, "ex@staff.edu", org, models.ROLE_EXAMINER)
    student = make_user(test_db, "kid@staff.edu", org, models.ROLE_CANDIDATE)

    assert client.get("/org/setup", headers=headers_for(examiner, org)).status_code == 200
    assert client.get("/org/setup", headers=headers_for(student, org)).status_code == 403
