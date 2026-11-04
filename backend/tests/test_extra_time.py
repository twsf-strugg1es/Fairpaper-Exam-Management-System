"""Extra time per student (task 4.11): set on an exam before they start, or added while they write. The deadline,
the answer cut-off and the abandoned-attempt job all follow it, even past the window's close."""
import uuid
from datetime import datetime, timedelta, timezone

from app import crud, jobs, models
from tests.test_organizations import headers_for, make_exam, make_org, make_user


def setup(db, closes_in=timedelta(hours=1)):
    org = make_org(db, f"Extra {uuid.uuid4().hex[:6]}")
    owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@extra.com", org, models.ROLE_OWNER)
    kid = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@extra.com", org, models.ROLE_CANDIDATE)
    exam = make_exam(db, org, "Chemistry")
    exam.end_time = datetime.now(timezone.utc) + closes_in
    db.commit()
    return org, owner, kid, exam


def give(client, owner, org, exam, kid, minutes):
    return client.put(f"/admin/exams/{exam.id}/extra-time/{kid.id}", headers=headers_for(owner, org), json={"minutes": minutes})


def start(client, org, exam, kid):
    return client.post(f"/student/exams/{exam.id}/start", headers=headers_for(kid, org)).json()


def back_in_time(db, attempt_id, minutes):
    attempt = db.get(models.ExamAttempt, uuid.UUID(attempt_id))
    attempt.start_time = crud.as_utc(attempt.start_time) - timedelta(minutes=minutes)
    db.commit()
    return attempt


def test_extra_time_set_before_they_start_is_on_their_clock(client, test_db):
    org, owner, kid, exam = setup(test_db)
    res = give(client, owner, org, exam, kid, 15)
    assert res.status_code == 200 and res.json()["minutes"] == 15 and res.json()["state"] == "not_started"
    listing = client.get("/student/exams/", headers=headers_for(kid, org)).json()
    assert next(e for e in listing if e["id"] == str(exam.id))["extra_minutes"] == 15
    session = start(client, org, exam, kid)
    assert session["exam"]["extra_minutes"] == 15
    assert 44 * 60 < session["exam"]["time_remaining_seconds"] <= 45 * 60  # 30 minutes plus 15


def test_time_added_while_they_write_moves_the_deadline(client, test_db):
    org, owner, kid, exam = setup(test_db)
    session = start(client, org, exam, kid)
    attempt = back_in_time(test_db, session["attempt"]["id"], 35)  # their 30 minutes ran out 5 minutes ago
    res = give(client, owner, org, exam, kid, 10)
    assert res.status_code == 200 and res.json()["state"] == "writing"
    h = headers_for(kid, org)
    clock = client.get(f"/student/attempts/{attempt.id}/clock", headers=h).json()
    assert 4 * 60 < clock["time_remaining_seconds"] <= 5 * 60 and clock["extra_minutes"] == 10
    saved = client.post(f"/student/attempts/{attempt.id}/save-answer", headers=h,
                        json={"question_id": str(exam.questions[0].id), "answer_data": "a"})
    assert saved.status_code == 200
    assert jobs.finalize_overdue_attempts(test_db) == 0  # the job waits for the new deadline
    staff_view = client.get(f"/admin/exams/{exam.id}/attempts", headers=headers_for(owner, org)).json()
    assert staff_view[0]["extra_minutes"] == 10 and staff_view[0]["deadline"]


def test_extra_time_can_run_past_the_window(client, test_db):
    org, owner, kid, exam = setup(test_db, closes_in=timedelta(minutes=5))
    session = start(client, org, exam, kid)
    assert session["exam"]["time_remaining_seconds"] <= 5 * 60  # the window ends their exam first
    give(client, owner, org, exam, kid, 20)
    clock = client.get(f"/student/attempts/{session['attempt']['id']}/clock", headers=headers_for(kid, org)).json()
    assert clock["time_remaining_seconds"] > 20 * 60


def test_a_live_exam_cant_be_cut_short_and_a_submitted_one_cant_change(client, test_db):
    org, owner, kid, exam = setup(test_db)
    session = start(client, org, exam, kid)
    give(client, owner, org, exam, kid, 10)
    back_in_time(test_db, session["attempt"]["id"], 35)
    cut = give(client, owner, org, exam, kid, 0)
    assert cut.status_code == 409 and "end the student's exam right now" in cut.json()["detail"]
    client.post(f"/student/attempts/{session['attempt']['id']}/submit", headers=headers_for(kid, org))
    late = give(client, owner, org, exam, kid, 30)
    assert late.status_code == 409 and "already submitted" in late.json()["detail"]


def test_zero_removes_it_and_the_list_shows_who_has_it(client, test_db):
    org, owner, kid, exam = setup(test_db)
    other = make_user(test_db, f"other-{uuid.uuid4().hex[:6]}@extra.com", org, models.ROLE_CANDIDATE)
    give(client, owner, org, exam, kid, 25)
    give(client, owner, org, exam, other, 10)
    listed = client.get(f"/admin/exams/{exam.id}/extra-time", headers=headers_for(owner, org)).json()
    assert {e["student"]["id"]: e["minutes"] for e in listed} == {str(kid.id): 25, str(other.id): 10}
    assert give(client, owner, org, exam, kid, 0).json()["minutes"] == 0
    assert [e["student"]["id"] for e in client.get(f"/admin/exams/{exam.id}/extra-time", headers=headers_for(owner, org)).json()] == [str(other.id)]
    assert give(client, owner, org, exam, kid, 601).status_code == 422


def test_only_this_organizations_staff_can_give_it_and_only_to_its_students(client, test_db):
    org, owner, kid, exam = setup(test_db)
    examiner = make_user(test_db, f"examiner-{uuid.uuid4().hex[:6]}@extra.com", org, models.ROLE_EXAMINER)
    assert give(client, owner, org, exam, examiner, 10).status_code == 404  # staff aren't candidates
    assert give(client, owner, org, exam, make_user(test_db, f"x-{uuid.uuid4().hex[:6]}@x.com"), 10).status_code == 404
    elsewhere = make_org(test_db, f"Elsewhere {uuid.uuid4().hex[:6]}")
    outsider = make_user(test_db, f"o-{uuid.uuid4().hex[:6]}@else.com", elsewhere, models.ROLE_OWNER)
    assert give(client, outsider, elsewhere, exam, kid, 10).status_code == 404
    assert client.put(f"/admin/exams/{exam.id}/extra-time/{kid.id}", headers=headers_for(kid, org), json={"minutes": 10}).status_code == 403
