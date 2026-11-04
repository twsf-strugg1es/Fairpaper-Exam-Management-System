"""Per-exam marks (task 4.2): a question can be worth a different number of marks in one exam,
without changing it in the question bank. Totals, grading and what students see all use it."""
from datetime import datetime, timedelta, timezone

from app import models
from tests.test_organizations import headers_for, make_org, make_user


def setup(db):
    org = make_org(db, "Marks Coaching")
    owner = make_user(db, "owner@marks.com", org, models.ROLE_OWNER)
    student = make_user(db, "kid@marks.com", org, models.ROLE_CANDIDATE)
    easy, hard = (models.Question(organization_id=org.id, title=t, complexity="easy", type="single_choice",
                                  options=["a", "b"], correct_answers="a", max_score=1) for t in ("Easy", "Hard"))
    db.add_all([easy, hard])
    db.commit()
    return org, owner, student, easy, hard


def body(questions, marks=None, open_now=False):
    start = datetime.now(timezone.utc) - timedelta(minutes=5) if open_now else datetime.now(timezone.utc) + timedelta(days=1)
    return {"title": "Weighted", "start_time": start.isoformat(), "end_time": (start + timedelta(hours=2)).isoformat(),
            "duration_minutes": 60, "question_ids": [str(q.id) for q in questions],
            "question_marks": {str(k.id): v for k, v in (marks or {}).items()}}


def test_marks_override_only_this_exam(client, test_db):
    org, owner, student, easy, hard = setup(test_db)
    h = headers_for(owner, org)

    exam = client.post("/admin/exams/", headers=h, json=body([easy, hard], {hard: 5})).json()

    by_id = {q["id"]: q for q in exam["questions"]}
    assert by_id[str(hard.id)]["max_score"] == 5 and by_id[str(hard.id)]["bank_max_score"] == 1
    assert by_id[str(easy.id)]["max_score"] == 1
    assert exam["total_marks"] == 6
    test_db.refresh(hard)
    assert hard.max_score == 1  # the bank is untouched

    other = client.post("/admin/exams/", headers=h, json=body([hard])).json()
    assert other["questions"][0]["max_score"] == 1 and other["total_marks"] == 1


def test_editing_changes_and_clears_overrides(client, test_db):
    org, owner, student, easy, hard = setup(test_db)
    h = headers_for(owner, org)
    exam_id = client.post("/admin/exams/", headers=h, json=body([easy, hard], {hard: 5})).json()["id"]

    res = client.put(f"/admin/exams/{exam_id}", headers=h, json=body([easy, hard], {easy: 3}))

    assert res.status_code == 200, res.text
    marks = {q["id"]: q["max_score"] for q in res.json()["questions"]}
    assert marks == {str(easy.id): 3, str(hard.id): 1} and res.json()["total_marks"] == 4


def test_grading_and_the_student_view_use_exam_marks(client, test_db):
    org, owner, student, easy, hard = setup(test_db)
    exam = client.post("/admin/exams/", headers=headers_for(owner, org), json=body([easy, hard], {hard: 4}, open_now=True)).json()
    client.post(f"/admin/exams/{exam['id']}/publish", headers=headers_for(owner, org))
    hs = headers_for(student, org)

    started = client.post(f"/student/exams/{exam['id']}/start", headers=hs).json()
    shown = {q["id"]: q["max_score"] for q in started["exam"]["questions"]}
    assert shown[str(hard.id)] == 4

    attempt = started["attempt"]["id"]
    client.post(f"/student/attempts/{attempt}/save-answer", headers=hs, json={"question_id": str(hard.id), "answer_data": "a"})
    client.post(f"/student/attempts/{attempt}/save-answer", headers=hs, json={"question_id": str(easy.id), "answer_data": "b"})
    result = client.post(f"/student/attempts/{attempt}/submit", headers=hs).json()

    row = test_db.get(models.ExamAttempt, __import__("uuid").UUID(attempt))
    assert row.score == 4 and row.total_possible_score == 5, result


def test_marks_are_checked(client, test_db):
    org, owner, student, easy, hard = setup(test_db)
    h = headers_for(owner, org)

    assert client.post("/admin/exams/", headers=h, json=body([easy], {easy: 0})).status_code == 422
    assert client.post("/admin/exams/", headers=h, json=body([easy], {easy: 101})).status_code == 422
    assert client.post("/admin/exams/", headers=h, json=body([easy], {hard: 3})).status_code == 422  # not in the exam
