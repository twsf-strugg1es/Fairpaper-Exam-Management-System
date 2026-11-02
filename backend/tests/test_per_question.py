"""Per-question time limits (task 4.11b, PRD F29, AC25-AC28): one question at a time, each with its own countdown
on the server; Next or the time running out locks it for good, and the exam's own deadline still applies."""
import io
import uuid
from datetime import datetime, timedelta, timezone

import openpyxl

from app import crud, models
from tests.test_organizations import headers_for, make_org, make_user

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def question(db, org, title, seconds=None):
    q = models.Question(organization_id=org.id, title=title, complexity="easy", type="single_choice",
                        options=["right", "wrong"], correct_answers="right", max_score=1, default_time_limit_seconds=seconds)
    db.add(q)
    db.commit()
    return q


def setup(db):
    org = make_org(db, f"Rapid {uuid.uuid4().hex[:6]}")
    owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@rapid.com", org, models.ROLE_OWNER)
    q1 = question(db, org, "First", seconds=20)  # the exam gives it 30
    q2 = question(db, org, "Second", seconds=45)  # the bank's 45
    q3 = question(db, org, "Third")  # no limit: waits for Next
    return org, owner, [q1, q2, q3]


def body(qs, **extra):
    now = datetime.now(timezone.utc)
    return {"title": "Rapid fire", "start_time": (now - timedelta(minutes=5)).isoformat(),
            "end_time": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 30, "require_fullscreen": False,
            "shuffle_questions": False, "question_ids": [str(q.id) for q in qs], "timing_mode": "per_question",
            "question_time_limits": {str(qs[0].id): 30}, **extra}


def create(client, owner, org, data):
    res = client.post("/admin/exams/", json=data, headers=headers_for(owner, org))
    assert res.status_code == 200, res.text
    assert client.post(f"/admin/exams/{res.json()['id']}/publish", headers=headers_for(owner, org)).status_code == 200
    return res.json()


def start(client, db, org, exam):
    kid = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@rapid.com", org, models.ROLE_CANDIDATE)
    h = headers_for(kid, org)
    return h, client.post(f"/student/exams/{exam['id']}/start", headers=h).json()


def save(client, h, attempt_id, q):
    return client.post(f"/student/attempts/{attempt_id}/save-answer", headers=h,
                       json={"question_id": str(q.id), "answer_data": "right"})


def shift(db, attempt_id, seconds):
    """Move the attempt and its question clocks back in time, as if the student had been away."""
    attempt = db.get(models.ExamAttempt, uuid.UUID(attempt_id))
    attempt.start_time = crud.as_utc(attempt.start_time) - timedelta(seconds=seconds)
    for row in db.query(models.AttemptQuestionTiming).filter_by(attempt_id=attempt.id):
        row.opened_at = crud.as_utc(row.opened_at) - timedelta(seconds=seconds)
        row.closes_at = crud.as_utc(row.closes_at) - timedelta(seconds=seconds) if row.closes_at else None
        row.closed_at = crud.as_utc(row.closed_at) - timedelta(seconds=seconds) if row.closed_at else None
    db.commit()


def test_ac25_an_exam_timed_as_a_whole_is_unchanged(client, test_db):
    org, owner, qs = setup(test_db)
    exam = create(client, owner, org, body(qs, timing_mode="exam"))
    assert exam["timing_mode"] == "exam"
    _, session = start(client, test_db, org, exam)
    assert session["exam"]["progress"] is None and len(session["exam"]["questions"]) == 3


def test_ac26_each_question_opens_on_its_own_clock_and_locks_behind_the_student(client, test_db):
    org, owner, (q1, q2, q3) = setup(test_db)
    exam = create(client, owner, org, body([q1, q2, q3]))
    assert [(q["id"], q["time_limit_seconds"]) for q in exam["questions"]] == [(str(q1.id), 30), (str(q2.id), 45), (str(q3.id), None)]
    h, session = start(client, test_db, org, exam)
    attempt = session["attempt"]["id"]
    progress = session["exam"]["progress"]
    assert [q["id"] for q in session["exam"]["questions"]] == [str(q1.id)]  # the others aren't sent
    assert (progress["position"], progress["total"], progress["states"]) == (0, 3, ["open", "upcoming", "upcoming"])
    assert progress["limit_seconds"] == 30 and 28 <= progress["seconds_left"] <= 30

    assert save(client, h, attempt, q1).status_code == 200
    early = save(client, h, attempt, q2)
    assert early.status_code == 403 and early.json()["detail"] == "This question hasn't opened yet."

    after = client.post(f"/student/attempts/{attempt}/questions/{q1.id}/next", headers=h).json()
    assert [q["id"] for q in after["exam"]["questions"]] == [str(q2.id)]
    assert after["exam"]["progress"]["states"] == ["closed", "open", "upcoming"]
    assert 43 <= after["exam"]["progress"]["seconds_left"] <= 45  # its own 45 seconds, from now
    back = save(client, h, attempt, q1)  # pressing Next locked it at once: no grace
    assert back.status_code == 403 and back.json()["detail"] == "This question is closed, so its answer can't change."
    again = client.post(f"/student/attempts/{attempt}/questions/{q1.id}/next", headers=h).json()  # a double click
    assert again["exam"]["progress"]["states"] == ["closed", "open", "upcoming"]


def test_ac26_time_running_out_moves_on_and_keeps_an_answer_sent_as_it_ended(client, test_db):
    org, owner, (q1, q2, q3) = setup(test_db)
    exam = create(client, owner, org, body([q1, q2, q3]))
    h, session = start(client, test_db, org, exam)
    attempt = session["attempt"]["id"]
    shift(test_db, attempt, 32)  # question 1's 30 seconds ended 2 seconds ago
    assert save(client, h, attempt, q1).status_code == 200  # sent as the time ran out: within the grace
    resumed = client.post(f"/student/attempts/{attempt}/resume", headers=h).json()
    assert resumed["exam"]["progress"]["states"] == ["closed", "open", "upcoming"]
    assert 42 <= resumed["exam"]["progress"]["seconds_left"] <= 43  # question 2 opened when question 1 ended
    shift(test_db, attempt, crud.TIMEOUT_GRACE_SECONDS)
    late = save(client, h, attempt, q1)
    assert late.status_code == 403


def test_ac27_a_reload_returns_to_the_same_question_with_the_time_that_is_left(client, test_db):
    org, owner, qs = setup(test_db)
    exam = create(client, owner, org, body(qs))
    h, session = start(client, test_db, org, exam)
    shift(test_db, session["attempt"]["id"], 10)
    again = client.post(f"/student/attempts/{session['attempt']['id']}/resume", headers=h).json()
    assert [q["id"] for q in again["exam"]["questions"]] == [str(qs[0].id)]
    assert 18 <= again["exam"]["progress"]["seconds_left"] <= 20  # never a fresh 30


def test_ac28_the_exam_deadline_still_applies_and_a_question_without_a_limit_waits(client, test_db):
    org, owner, (q1, q2, q3) = setup(test_db)
    exam = create(client, owner, org, body([q3, q1], duration_minutes=1, question_time_limits={str(q1.id): 600}))
    h, session = start(client, test_db, org, exam)
    attempt = session["attempt"]["id"]
    assert session["exam"]["progress"]["seconds_left"] is None  # no limit: it waits for Next
    shift(test_db, attempt, 20)
    assert client.post(f"/student/attempts/{attempt}/resume", headers=h).json()["exam"]["progress"]["states"] == ["open", "upcoming"]
    moved = client.post(f"/student/attempts/{attempt}/questions/{q3.id}/next", headers=h).json()
    assert moved["exam"]["progress"]["seconds_left"] <= 40  # 600 seconds, but the exam ends sooner
    last = client.post(f"/student/attempts/{attempt}/questions/{q1.id}/next", headers=h)
    assert last.status_code == 409 and last.json()["detail"] == "This is the last question. Submit the exam to finish."


def test_ac28_the_last_question_running_out_submits_the_exam(client, test_db):
    org, owner, (q1, q2, _) = setup(test_db)
    exam = create(client, owner, org, body([q1, q2]))
    h, session = start(client, test_db, org, exam)
    attempt = session["attempt"]["id"]
    shift(test_db, attempt, 30 + 45 + 1)
    gone = client.post(f"/student/attempts/{attempt}/resume", headers=h).json()
    assert gone["exam"]["auto_submitted"] is True and gone["attempt"]["submit_reason"] == models.SUBMIT_TIME_UP
    stored = test_db.get(models.ExamAttempt, uuid.UUID(attempt))
    test_db.refresh(stored)
    ended = max(crud.as_utc(r.closes_at) for r in test_db.query(models.AttemptQuestionTiming).filter_by(attempt_id=stored.id))
    assert crud.as_utc(stored.end_time) == ended


def test_the_timing_is_checked(client, test_db):
    org, owner, qs = setup(test_db)
    h = headers_for(owner, org)
    assert client.post("/admin/exams/", headers=h, json=body(qs, timing_mode="by the minute")).status_code == 422
    assert client.post("/admin/exams/", headers=h, json=body(qs, question_time_limits={str(qs[0].id): 5})).status_code == 422
    sections = {"sections": [{"title": "A", "time_limit_minutes": 5}], "question_sections": {str(q.id): 0 for q in qs}}
    mixed = client.post("/admin/exams/", headers=h, json=body(qs, **sections))
    assert mixed.status_code == 422 and "sections that have their own time" in mixed.text
    whole = client.post("/admin/exams/", headers=h, json=body(qs, timing_mode="exam")).json()
    assert [q["time_limit_seconds"] for q in whole["questions"]] == [20, 45, None]  # the bank's, nothing stored


def test_a_question_carries_its_own_default_time(client, test_db):
    org, owner, _ = setup(test_db)
    h = headers_for(owner, org)
    base = {"title": "Quick one", "complexity": "easy", "type": "true_false", "correct_answers": "true", "max_score": 1}
    assert client.post("/admin/questions/", headers=h, json={**base, "default_time_limit_seconds": 5}).status_code == 422
    made = client.post("/admin/questions/", headers=h, json={**base, "default_time_limit_seconds": 15})
    assert made.status_code == 201 and made.json()["default_time_limit_seconds"] == 15

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["title", "complexity", "type", "options", "correct_answers", "max_score", "time_limit_seconds"])
    ws.append(["Sky is blue", "easy", "true_false", None, "true", 1, 20])
    ws.append(["No limit here", "easy", "true_false", None, "false", 1, None])
    stream = io.BytesIO()
    wb.save(stream)
    res = client.post("/admin/upload-questions/", headers=h, files={"file": ("q.xlsx", io.BytesIO(stream.getvalue()), XLSX)})
    assert res.status_code == 200, res.text
    stored = {q.title: q.default_time_limit_seconds for q in test_db.query(models.Question).filter_by(organization_id=org.id)}
    assert stored["Sky is blue"] == 20 and stored["No limit here"] is None
    ws.append(["Too quick", "easy", "true_false", None, "true", 1, 3])
    stream = io.BytesIO()
    wb.save(stream)
    bad = client.post("/admin/upload-questions/", headers=h, files={"file": ("q.xlsx", io.BytesIO(stream.getvalue()), XLSX)})
    assert bad.status_code == 400 and bad.json()["detail"].startswith("Row 4: time_limit_seconds")


def test_an_abandoned_attempt_ends_when_its_last_question_ran_out(client, test_db):
    from app import jobs
    org, owner, (q1, q2, _) = setup(test_db)
    exam = create(client, owner, org, body([q1, q2]))
    _, session = start(client, test_db, org, exam)
    attempt = session["attempt"]["id"]
    shift(test_db, attempt, 30 + 45 + crud.ANSWER_GRACE_SECONDS + 5)  # gone long enough, the exam itself still open
    assert jobs.finalize_overdue_attempts(test_db) == 1
    stored = test_db.get(models.ExamAttempt, uuid.UUID(attempt))
    test_db.refresh(stored)
    last = max(crud.as_utc(r.closes_at) for r in test_db.query(models.AttemptQuestionTiming).filter_by(attempt_id=stored.id))
    assert stored.submit_reason == models.SUBMIT_TIME_UP and crud.as_utc(stored.end_time) == last
