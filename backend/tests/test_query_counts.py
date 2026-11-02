"""Exam-day requests stay cheap as an organization grows (task 5.2). The candidate's exam list, starting an exam,
saving an answer, the clock and submitting run as many SQL statements for an organization with 2 exams of 3
questions as for one with 12 exams of 30, so 500 candidates at once cost what the load test measures."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from app import models
from tests.test_organizations import headers_for, make_org, make_user


def _counts(client, db, exams, questions):
    org = make_org(db, f"Size {uuid.uuid4().hex[:6]}")
    staff = headers_for(make_user(db, f"owner-{uuid.uuid4().hex[:6]}@counts.com", org, models.ROLE_OWNER), org)
    ids = [client.post("/admin/questions/", headers=staff, json={
        "title": f"Question {i}", "complexity": "easy", "type": ("single_choice", "text")[i % 2], "max_score": 1,
        **({"options": ["a", "b"], "correct_answers": "a"} if i % 2 == 0 else {})}).json()["id"] for i in range(questions)]
    now = datetime.now(timezone.utc)
    made = []
    for n in range(exams):
        exam = client.post("/admin/exams/", headers=staff, json={
            "title": f"Exam {n}", "start_time": (now - timedelta(minutes=5)).isoformat(),
            "end_time": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 30, "question_ids": ids,
            "require_fullscreen": False, **({"sections": [{"title": "Part A"}], "question_sections": {i: 0 for i in ids}}
                                            if n % 2 else {})}).json()
        assert client.post(f"/admin/exams/{exam['id']}/publish", headers=staff).status_code == 200
        made.append(exam["id"])
    kid = headers_for(make_user(db, f"kid-{uuid.uuid4().hex[:6]}@counts.com", org, models.ROLE_CANDIDATE), org)

    statements = []
    listener = lambda *args, **kwargs: statements.append(1)  # noqa: E731
    event.listen(db.bind, "before_cursor_execute", listener)

    def run(method, url, **kwargs):
        statements.clear()
        res = client.request(method, url, headers=kid, **kwargs)
        assert res.status_code < 300, (url, res.text)
        return len(statements), res

    try:
        counts = {"exam list": run("GET", "/student/exams/")[0]}
        counts["start"], started = run("POST", f"/student/exams/{made[0]}/start")
        attempt = started.json()["attempt"]["id"]
        counts["save"] = run("POST", f"/student/attempts/{attempt}/save-answer",
                             json={"question_id": ids[0], "answer_data": "a", "client_seq": 1})[0]
        for i, qid in enumerate(ids[1:], start=2):  # a full paper, for grading at submit
            client.post(f"/student/attempts/{attempt}/save-answer", headers=kid,
                        json={"question_id": qid, "answer_data": "a" if i % 2 else "An answer.", "client_seq": i})
        counts["clock"] = run("GET", f"/student/attempts/{attempt}/clock")[0]
        counts["submit"] = run("POST", f"/student/attempts/{attempt}/submit")[0]
    finally:
        event.remove(db.bind, "before_cursor_execute", listener)
    return counts


def test_exam_day_requests_dont_grow_with_the_organization(client, test_db):
    small = _counts(client, test_db, exams=2, questions=3)
    large = _counts(client, test_db, exams=12, questions=30)
    assert large == small, f"small organization {small}, large organization {large}"
