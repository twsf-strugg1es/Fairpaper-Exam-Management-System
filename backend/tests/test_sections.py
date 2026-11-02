"""Exam sections (task 4.10): parts with their own title, instructions and time. With time limits, students take
them in order, one open at a time; a section locks when its time ends or they finish it, and the server refuses
answers to closed and upcoming sections."""
import uuid
from datetime import datetime, timedelta, timezone

from app import crud, models
from tests.test_organizations import headers_for, make_org, make_user


def question(db, org, title, tags=("physics",)):
    q = models.Question(organization_id=org.id, title=title, complexity="easy", type="single_choice",
                        options=["right", "wrong"], correct_answers="right", max_score=1, tags=list(tags))
    db.add(q)
    db.commit()
    return q


def setup(db):
    org = make_org(db, f"Sections {uuid.uuid4().hex[:6]}")
    owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@sections.com", org, models.ROLE_OWNER)
    a = [question(db, org, f"Part A question {i}", tags=("mechanics",)) for i in range(3)]
    b = [question(db, org, f"Part B question {i}", tags=("mechanics",)) for i in range(2)]
    pool = [question(db, org, f"Optics question {i}", tags=("optics",)) for i in range(4)]
    return org, owner, a, b, pool


def body(a, b, sections, rules=(), **extra):
    now = datetime.now(timezone.utc)
    return {
        "title": "Physics in two parts", "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=3)).isoformat(), "duration_minutes": 60, "require_fullscreen": False,
        "question_ids": [str(q.id) for q in a + b], "pool_rules": list(rules), "sections": sections,
        "question_sections": {**{str(q.id): 0 for q in a}, **{str(q.id): 1 for q in b}}, **extra,
    }


def create(client, owner, org, data):
    res = client.post("/admin/exams/", json=data, headers=headers_for(owner, org))
    assert res.status_code == 200, res.text
    assert client.post(f"/admin/exams/{res.json()['id']}/publish", headers=headers_for(owner, org)).status_code == 200
    return res.json()


def student(client, db, org, exam):
    kid = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@sections.com", org, models.ROLE_CANDIDATE)
    h = headers_for(kid, org)
    return h, client.post(f"/student/exams/{exam['id']}/start", headers=h).json()


def save(client, h, session, question_id):
    return client.post(f"/student/attempts/{session['attempt']['id']}/save-answer", headers=h,
                       json={"question_id": str(question_id), "answer_data": "right"})


TIMED = [{"title": "Part A: mechanics", "instructions": "Answer all three.", "time_limit_minutes": 10},
         {"title": "Part B: optics", "time_limit_minutes": 15}]


def test_sections_keep_their_questions_together_and_in_order(client, test_db):
    org, owner, a, b, pool = setup(test_db)
    exam = create(client, owner, org, body(a, b, [{"title": "Part A"}, {"title": "Part B"}],
                                           rules=[{"count": 2, "tag": "optics", "section": 1}], shuffle_questions=True))
    assert [s["title"] for s in exam["sections"]] == ["Part A", "Part B"] and exam["timed_sections"] is False
    assert {q["section"] for q in exam["questions"]} == {0, 1} and exam["pool_rules"][0]["section"] == 1

    for _ in range(3):  # whatever the shuffle, part A's questions come first and drawn questions sit in part B
        h, session = student(client, test_db, org, exam)
        sections = session["exam"]["sections"]
        assert [s["question_count"] for s in sections] == [3, 4] and all(s["state"] is None for s in sections)
        order = [q["section_id"] for q in session["exam"]["questions"]]
        assert order == [sections[0]["id"]] * 3 + [sections[1]["id"]] * 4
        drawn = {q["id"] for q in session["exam"]["questions"][3:]} - {str(q.id) for q in b}
        assert drawn <= {str(q.id) for q in pool} and len(drawn) == 2
        assert save(client, h, session, b[0].id).status_code == 200  # untimed: any section, any time


def test_every_question_needs_a_section(client, test_db):
    org, owner, a, b, _ = setup(test_db)
    h = headers_for(owner, org)
    loose = body(a, b, [{"title": "Part A"}, {"title": "Part B"}])
    del loose["question_sections"][str(b[0].id)]
    assert client.post("/admin/exams/", json=loose, headers=h).json()["detail"][0]["msg"].endswith(
        "Put every question and every random-question rule in a section.")
    empty = body(a, b, [{"title": "Part A"}, {"title": "Part B"}, {"title": "Part C"}])
    assert "Part C" in client.post("/admin/exams/", json=empty, headers=h).json()["detail"][0]["msg"]
    rule_left_out = body(a, b, [{"title": "Part A"}, {"title": "Part B"}], rules=[{"count": 1, "tag": "optics"}])
    assert client.post("/admin/exams/", json=rule_left_out, headers=h).status_code == 422
    untitled = body(a, b, [{"title": "  "}, {"title": "Part B"}])
    assert client.post("/admin/exams/", json=untitled, headers=h).status_code == 422


def test_sections_can_be_changed_until_someone_starts(client, test_db):
    org, owner, a, b, _ = setup(test_db)
    h = headers_for(owner, org)
    exam = client.post("/admin/exams/", json=body(a, b, TIMED), headers=h).json()
    one_part = body(a, b, [])
    res = client.put(f"/admin/exams/{exam['id']}", json=one_part, headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["sections"] == [] and all(q["section"] is None for q in res.json()["questions"])
    assert test_db.query(models.ExamSection).filter_by(exam_id=uuid.UUID(exam["id"])).count() == 0


def test_timed_sections_open_one_at_a_time_and_lock_behind_the_student(client, test_db):
    org, owner, a, b, _ = setup(test_db)
    exam = create(client, owner, org, body(a, b, TIMED))
    h, session = student(client, test_db, org, exam)
    first, second = session["exam"]["sections"]
    assert session["exam"]["timed_sections"] is True
    assert (first["state"], second["state"]) == ("open", "upcoming") and first["instructions"] == "Answer all three."
    assert 595 <= first["seconds_left"] <= 600 and second["seconds_left"] is None
    assert {q["id"] for q in session["exam"]["questions"]} == {str(q.id) for q in a}  # part B isn't sent yet

    assert save(client, h, session, a[0].id).status_code == 200
    early = save(client, h, session, b[0].id)
    assert early.status_code == 403 and early.json()["detail"] == "This section hasn't started yet."

    finish = f"/student/attempts/{session['attempt']['id']}/sections/{first['id']}/finish"
    after = client.post(finish, headers=h).json()
    assert [s["state"] for s in after["exam"]["sections"]] == ["closed", "open"]
    assert {q["id"] for q in after["exam"]["questions"]} == {str(q.id) for q in b}
    assert 895 <= after["exam"]["sections"][1]["seconds_left"] <= 900  # part B's own 15 minutes, from now
    again = client.post(finish, headers=h).json()  # a double click
    assert [s["state"] for s in again["exam"]["sections"]] == ["closed", "open"]

    row = test_db.query(models.AttemptSection).filter_by(section_id=uuid.UUID(first["id"])).one()
    row.closed_at = datetime.now(timezone.utc) - timedelta(seconds=crud.TIMEOUT_GRACE_SECONDS + 1)
    test_db.commit()
    late = save(client, h, session, a[1].id)
    assert late.status_code == 403 and late.json()["detail"] == "This section is closed, so its answers can't change."
    last = client.post(f"/student/attempts/{session['attempt']['id']}/sections/{second['id']}/finish", headers=h)
    assert last.status_code == 409 and last.json()["detail"] == "This is the last section. Submit the exam to finish."

    assert save(client, h, session, b[0].id).status_code == 200
    submitted = client.post(f"/student/attempts/{session['attempt']['id']}/submit", headers=h).json()
    assert submitted["submit_reason"] == models.SUBMIT_STUDENT and submitted["score"] == 2
    assert test_db.query(models.AttemptSection).filter(models.AttemptSection.closed_at.is_(None)).count() == 0


def test_the_clock_keeps_running_while_the_student_is_away(client, test_db):
    org, owner, a, b, _ = setup(test_db)
    exam = create(client, owner, org, body(a, b, TIMED))
    h, session = student(client, test_db, org, exam)
    attempt = test_db.get(models.ExamAttempt, uuid.UUID(session["attempt"]["id"]))
    row = test_db.query(models.AttemptSection).filter_by(attempt_id=attempt.id).one()
    shift = timedelta(minutes=12)  # away for 12 minutes: part A (10) ended 2 minutes ago, part B opened then
    attempt.start_time = crud.as_utc(attempt.start_time) - shift
    row.opened_at, row.closes_at = crud.as_utc(row.opened_at) - shift, crud.as_utc(row.closes_at) - shift
    test_db.commit()

    back = client.post(f"/student/attempts/{attempt.id}/resume", headers=h).json()
    states = [s["state"] for s in back["exam"]["sections"]]
    assert states == ["closed", "open"] and 775 <= back["exam"]["sections"][1]["seconds_left"] <= 780

    attempt.start_time = crud.as_utc(attempt.start_time) - timedelta(minutes=20)  # and long enough for part B too
    for r in test_db.query(models.AttemptSection).filter_by(attempt_id=attempt.id):
        r.opened_at = crud.as_utc(r.opened_at) - timedelta(minutes=20)
        r.closes_at = crud.as_utc(r.closes_at) - timedelta(minutes=20)
        r.closed_at = crud.as_utc(r.closed_at) - timedelta(minutes=20) if r.closed_at else None
    test_db.commit()
    gone = client.post(f"/student/attempts/{attempt.id}/resume", headers=h).json()
    assert gone["exam"]["auto_submitted"] is True and gone["attempt"]["submit_reason"] == models.SUBMIT_TIME_UP
    test_db.refresh(attempt)
    part_b_end = max(crud.as_utc(r.closes_at) for r in test_db.query(models.AttemptSection).filter_by(attempt_id=attempt.id))
    assert crud.as_utc(attempt.end_time) == part_b_end


def test_only_the_student_can_finish_their_section(client, test_db):
    org, owner, a, b, _ = setup(test_db)
    exam = create(client, owner, org, body(a, b, TIMED))
    _, session = student(client, test_db, org, exam)
    other, _ = student(client, test_db, org, exam)
    section = session["exam"]["sections"][0]["id"]
    res = client.post(f"/student/attempts/{session['attempt']['id']}/sections/{section}/finish", headers=other)
    assert res.status_code == 404
