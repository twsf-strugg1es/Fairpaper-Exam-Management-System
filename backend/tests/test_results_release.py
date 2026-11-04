"""Result publishing control (task 4.3): students see nothing about their score until the exam's
results are released: right after submitting (default), when the exam closes, or by hand."""
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from tests.test_organizations import headers_for, make_org, make_user


def setup(db, release, ends_in=timedelta(hours=1)):
    org = make_org(db, f"Release {release} {uuid.uuid4().hex[:6]}")
    owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@release.com", org, models.ROLE_OWNER)
    student = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@release.com", org, models.ROLE_CANDIDATE)
    q = models.Question(organization_id=org.id, title="1 + 1", complexity="easy", type="single_choice",
                        options=["2", "3"], correct_answers="2", max_score=1)
    now = datetime.now(timezone.utc)
    exam = models.Exam(organization_id=org.id, title="Quiz", start_time=now - timedelta(minutes=5), end_time=now + ends_in,
                       duration_minutes=30, is_published=True, results_release=release)
    exam.questions.append(q)
    db.add(exam)
    db.commit()
    return headers_for(owner, org), headers_for(student, org), exam, q


def take(client, hs, exam, q):
    attempt = client.post(f"/student/exams/{exam.id}/start", headers=hs).json()["attempt"]["id"]
    client.post(f"/student/attempts/{attempt}/save-answer", headers=hs, json={"question_id": str(q.id), "answer_data": "2"})
    return attempt, client.post(f"/student/attempts/{attempt}/submit", headers=hs).json()


def everything_a_student_sees(client, hs, attempt):
    return {
        "results": client.get(f"/student/attempts/{attempt}/results", headers=hs).json(),
        "completed": client.get("/student/completed-exams/", headers=hs).json(),
        "evaluated": client.get(f"/student/attempts/{attempt}/evaluated-results", headers=hs).json(),
    }


def test_immediate_is_the_default_and_shows_the_score(client, test_db):
    ho, hs, exam, q = setup(test_db, models.RESULTS_IMMEDIATE)
    attempt, submitted = take(client, hs, exam, q)

    assert submitted["score"] == 1 and submitted["results_released"] is True
    seen = everything_a_student_sees(client, hs, attempt)
    assert seen["completed"][0]["percentage"] == 100 and seen["evaluated"]["score"] == 1


def test_manual_hides_every_score_until_released(client, test_db):
    ho, hs, exam, q = setup(test_db, models.RESULTS_MANUAL)
    attempt, submitted = take(client, hs, exam, q)

    assert submitted["score"] is None and submitted["total_possible_score"] is None and submitted["results_released"] is False
    seen = everything_a_student_sees(client, hs, attempt)
    assert seen["results"]["attempt"]["score"] is None and seen["results"]["exam"]["answers_revealed"] is False
    assert seen["completed"][0]["score"] is None and seen["completed"][0]["percentage"] is None
    assert seen["evaluated"]["score"] is None and seen["evaluated"]["answers_with_evaluations"] == []
    assert '"score": 1' not in str(seen)

    released = client.post(f"/admin/exams/{exam.id}/results/release", headers=ho)
    assert released.status_code == 200 and released.json()["results_visible"] is True
    seen = everything_a_student_sees(client, hs, attempt)
    assert seen["completed"][0]["score"] == 1 and seen["evaluated"]["results_released"] is True

    # Released by mistake: take it back
    assert client.delete(f"/admin/exams/{exam.id}/results/release", headers=ho).json()["results_visible"] is False
    assert client.get("/student/completed-exams/", headers=hs).json()[0]["score"] is None


def test_on_close_waits_for_the_window_to_end(client, test_db):
    ho, hs, exam, q = setup(test_db, models.RESULTS_ON_CLOSE)
    attempt, submitted = take(client, hs, exam, q)
    assert submitted["score"] is None

    exam.end_time = datetime.now(timezone.utc) - timedelta(minutes=1)  # the window closes
    test_db.commit()
    seen = everything_a_student_sees(client, hs, attempt)
    assert seen["results"]["attempt"]["score"] == 1 and seen["results"]["exam"]["answers_revealed"] is True


def test_staff_always_see_scores_and_set_the_mode(client, test_db):
    ho, hs, exam, q = setup(test_db, models.RESULTS_MANUAL)
    take(client, hs, exam, q)
    attempts = client.get(f"/admin/exams/{exam.id}/attempts", headers=ho)
    assert attempts.status_code == 200 and attempts.json()[0]["score"] == 1

    payload = client.get(f"/admin/exams/{exam.id}", headers=ho).json()
    assert payload["results_release"] == "manual" and payload["results_visible"] is False


def test_release_is_scoped_and_checked(client, test_db):
    ho, hs, exam, q = setup(test_db, models.RESULTS_MANUAL)
    other_owner, _, _, _ = setup(test_db, models.RESULTS_MANUAL)

    assert client.post(f"/admin/exams/{exam.id}/results/release", headers=other_owner).status_code == 404
    assert client.post(f"/admin/exams/{exam.id}/results/release", headers=hs).status_code == 403
    start = datetime.now(timezone.utc) + timedelta(days=1)
    bad = {"title": "X", "start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat(),
           "duration_minutes": 30, "question_ids": [str(q.id)], "results_release": "sometimes"}
    assert client.post("/admin/exams/", headers=ho, json=bad).status_code == 422
