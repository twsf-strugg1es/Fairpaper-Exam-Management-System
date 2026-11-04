"""Grading written and image answers (task 4.9): partial marks from 0 to what the question is worth, one question
across every submitted paper, one grade per answer however many staff grade at once."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app import crud, models
from tests.test_organizations import headers_for, make_org, make_user


def question(db, org, title, qtype="text", marks=4, **extra):
    q = models.Question(organization_id=org.id, title=title, complexity="medium", type=qtype, max_score=marks,
                        options=extra.get("options"), correct_answers=extra.get("correct_answers"))
    db.add(q)
    db.commit()
    return q


@pytest.fixture
def setup(client, test_db):
    org = make_org(test_db, f"Grading {uuid.uuid4().hex[:6]}")
    owner = make_user(test_db, f"owner-{uuid.uuid4().hex[:6]}@grading.com", org, models.ROLE_OWNER)
    examiner = make_user(test_db, f"examiner-{uuid.uuid4().hex[:6]}@grading.com", org, models.ROLE_EXAMINER)
    essay = question(test_db, org, "Explain photosynthesis.")
    photo = question(test_db, org, "Upload your diagram.", qtype="image_upload", marks=2)
    choice = question(test_db, org, "2 + 2?", qtype="single_choice", marks=1, options=["3", "4"], correct_answers="4")
    now = datetime.now(timezone.utc)
    exam = client.post("/admin/exams/", headers=headers_for(owner, org), json={
        "title": "Biology", "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 30,
        "question_ids": [str(essay.id), str(photo.id), str(choice.id)], "require_fullscreen": False}).json()
    assert client.post(f"/admin/exams/{exam['id']}/publish", headers=headers_for(owner, org)).status_code == 200
    return {"org": org, "owner": owner, "examiner": examiner, "exam": exam, "essay": essay, "photo": photo, "choice": choice}


def sit(client, db, s, answers, submit=True):
    kid = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@grading.com", s["org"], models.ROLE_CANDIDATE)
    h = headers_for(kid, s["org"])
    attempt_id = client.post(f"/student/exams/{s['exam']['id']}/start", headers=h).json()["attempt"]["id"]
    for q, value in answers.items():
        res = client.post(f"/student/attempts/{attempt_id}/save-answer", headers=h,
                          json={"question_id": str(s[q].id), "answer_data": value})
        assert res.status_code == 200, res.text
    if submit:
        client.post(f"/student/attempts/{attempt_id}/submit", headers=h)
    return uuid.UUID(attempt_id)


def answer_id(db, attempt_id, q):
    return str(db.query(models.Answer).filter_by(attempt_id=attempt_id, question_id=q.id).one().id)


def grade(client, user, org, answer, **body):
    return client.post(f"/admin/evaluations/answers/{answer}/submit", headers=headers_for(user, org), json=body)


def test_one_question_across_every_submitted_paper(client, test_db, setup):
    s = setup
    first = sit(client, test_db, s, {"essay": "Plants make sugar from light.", "choice": "4"})
    second = sit(client, test_db, s, {"essay": "Light, water and CO2 become glucose and oxygen."})
    sit(client, test_db, s, {"essay": "   "})  # typed nothing in the end
    sit(client, test_db, s, {})  # never touched it
    sit(client, test_db, s, {"essay": "Still writing"}, submit=False)
    h = headers_for(s["examiner"], s["org"])

    overview = client.get(f"/admin/exams/{s['exam']['id']}/grading", headers=h).json()
    assert overview["submitted"] == 4
    essay = next(q for q in overview["questions"] if q["id"] == str(s["essay"].id))
    assert (essay["papers"], essay["answered"], essay["graded"], essay["worth"]) == (4, 2, 0, 4)
    assert {q["type"] for q in overview["questions"]} == {"text", "image_upload"}  # the choice question grades itself

    sheet = client.get(f"/admin/exams/{s['exam']['id']}/grading/{s['essay'].id}", headers=h).json()
    assert [a["attempt_id"] for a in sheet["answers"]] == [str(first), str(second)]  # in the order they submitted
    assert sheet["blank"] == 2 and sheet["question"]["worth"] == 4
    assert sheet["answers"][0]["text"] == "Plants make sugar from light." and sheet["answers"][0]["score_awarded"] is None

    res = grade(client, s["examiner"], s["org"], sheet["answers"][0]["answer_id"], score_awarded=2.5, comment="Name the products.")
    assert res.status_code == 200 and res.json()["score_awarded"] == 2.5
    sheet = client.get(f"/admin/exams/{s['exam']['id']}/grading/{s['essay'].id}", headers=h).json()
    assert sheet["answers"][0]["comment"] == "Name the products." and sheet["answers"][0]["graded_by"]
    attempt = test_db.get(models.ExamAttempt, first)
    test_db.refresh(attempt)
    assert crud.final_score(test_db, attempt) == 1 + 2.5  # the choice question, plus the partial mark


def test_marks_stay_between_zero_and_what_the_question_is_worth(client, test_db, setup):
    s = setup
    attempt = sit(client, test_db, s, {"essay": "An answer", "choice": "3"})
    essay = answer_id(test_db, attempt, s["essay"])
    assert grade(client, s["owner"], s["org"], essay, score_awarded=4.5).json()["detail"] == "Give a mark from 0 to 4."
    assert grade(client, s["owner"], s["org"], essay, score_awarded=-1).status_code == 422
    assert grade(client, s["owner"], s["org"], essay, comment="no mark").status_code == 422
    assert grade(client, s["owner"], s["org"], essay, score_awarded=1, comment="x" * 101).status_code == 422
    assert grade(client, s["owner"], s["org"], essay, score_awarded=3.333).json()["score_awarded"] == 3.33
    assert grade(client, s["owner"], s["org"], essay, is_correct=True).json()["score_awarded"] == 4  # older pages
    choice = answer_id(test_db, attempt, s["choice"])
    assert grade(client, s["owner"], s["org"], choice, score_awarded=1).json()["detail"] == "This question is graded automatically."


def test_an_answer_is_graded_only_after_the_student_submits(client, test_db, setup):
    s = setup
    writing = sit(client, test_db, s, {"essay": "Half done"}, submit=False)
    res = grade(client, s["owner"], s["org"], answer_id(test_db, writing, s["essay"]), score_awarded=1)
    assert res.status_code == 400 and res.json()["detail"] == "This answer can be graded once the student submits."


def test_two_graders_leave_one_grade(client, test_db, setup):
    s = setup
    attempt = sit(client, test_db, s, {"essay": "An answer"})
    essay = answer_id(test_db, attempt, s["essay"])
    grade(client, s["owner"], s["org"], essay, score_awarded=1)
    grade(client, s["examiner"], s["org"], essay, score_awarded=3)
    grades = test_db.query(models.Evaluation).filter_by(answer_id=uuid.UUID(essay)).all()
    assert len(grades) == 1 and grades[0].score_awarded == 3 and grades[0].evaluated_by == s["examiner"].id
    test_db.add(models.Evaluation(answer_id=uuid.UUID(essay), evaluated_by=s["owner"].id, score_awarded=4))
    with pytest.raises(IntegrityError):  # the database refuses a second grade too
        test_db.commit()
    test_db.rollback()


def test_a_blank_written_answer_earns_nothing_without_grading(client, test_db, setup):
    s = setup
    attempt = sit(client, test_db, s, {"essay": "  ", "choice": "4"})
    exam = test_db.get(models.Exam, uuid.UUID(s["exam"]["id"]))
    row = next(r for r in crud.breakdowns(test_db, exam, [test_db.get(models.ExamAttempt, attempt)])[attempt]
               if r["question"].id == s["essay"].id)
    assert row["earned"] == 0 and row["answered"] is False


def test_another_organization_cannot_see_or_grade(client, test_db, setup):
    s = setup
    attempt = sit(client, test_db, s, {"essay": "An answer"})
    other = make_org(test_db, f"Other {uuid.uuid4().hex[:6]}")
    outsider = make_user(test_db, f"outsider-{uuid.uuid4().hex[:6]}@other.com", other, models.ROLE_OWNER)
    h = headers_for(outsider, other)
    assert client.get(f"/admin/exams/{s['exam']['id']}/grading", headers=h).status_code == 404
    assert client.get(f"/admin/exams/{s['exam']['id']}/grading/{s['essay'].id}", headers=h).status_code == 404
    assert grade(client, outsider, other, answer_id(test_db, attempt, s["essay"]), score_awarded=1).status_code == 404
    student = make_user(test_db, f"s-{uuid.uuid4().hex[:6]}@grading.com", s["org"], models.ROLE_CANDIDATE)
    assert client.get(f"/admin/exams/{s['exam']['id']}/grading", headers=headers_for(student, s["org"])).status_code == 403
