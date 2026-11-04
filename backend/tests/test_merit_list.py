"""Merit list (task 4.4, PRD AC17): ranked by score (higher first), then time taken (shorter first);
candidates level on both share a rank."""
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from tests.test_organizations import headers_for, make_org, make_user


def setup(db, show_rank=False):
    org = make_org(db, f"Merit {uuid.uuid4().hex[:6]}")
    owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@merit.com", org, models.ROLE_OWNER)
    now = datetime.now(timezone.utc)
    exam = models.Exam(organization_id=org.id, title="Admission mock", start_time=now - timedelta(hours=3),
                       end_time=now - timedelta(minutes=1), duration_minutes=60, is_published=True, show_rank=show_rank)
    db.add(exam)
    db.commit()
    return org, owner, exam


def submitted(db, org, exam, name, score, minutes):
    student = make_user(db, f"{name}-{uuid.uuid4().hex[:4]}@merit.com", org, models.ROLE_CANDIDATE)
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    db.add(models.ExamAttempt(exam_id=exam.id, student_id=student.id, start_time=start, end_time=start + timedelta(minutes=minutes),
                              score=score, total_possible_score=10, submit_reason=models.SUBMIT_STUDENT))
    db.commit()
    return student


def test_ac17_score_then_time_with_shared_ranks(client, test_db):
    org, owner, exam = setup(test_db)
    submitted(test_db, org, exam, "slow-top", 9, 50)
    submitted(test_db, org, exam, "fast-top", 9, 30)
    submitted(test_db, org, exam, "tie-a", 7, 40)
    submitted(test_db, org, exam, "tie-b", 7, 40)
    submitted(test_db, org, exam, "last", 3, 20)

    data = client.get(f"/admin/exams/{exam.id}/merit", headers=headers_for(owner, org)).json()

    assert data["closed"] is True
    order = [(r["student"]["email"].split("-")[0], r["rank"], r["tied"]) for r in data["rows"]]
    assert [o[0] for o in order] == ["fast", "slow", "tie", "tie", "last"]
    assert [o[1] for o in order] == [1, 2, 3, 3, 5]
    assert [o[2] for o in order] == [False, False, True, True, False]
    assert data["rows"][0]["time_taken_seconds"] == 1800 and data["rows"][0]["percentage"] == 90


def test_unfinished_attempts_are_left_out(client, test_db):
    org, owner, exam = setup(test_db)
    submitted(test_db, org, exam, "done", 5, 10)
    writer = make_user(test_db, "writing@merit.com", org, models.ROLE_CANDIDATE)
    test_db.add(models.ExamAttempt(exam_id=exam.id, student_id=writer.id, start_time=datetime.now(timezone.utc)))
    test_db.commit()

    rows = client.get(f"/admin/exams/{exam.id}/merit", headers=headers_for(owner, org)).json()["rows"]
    assert len(rows) == 1


def test_candidates_see_their_rank_only_when_the_exam_shows_it(client, test_db):
    org, owner, exam = setup(test_db, show_rank=True)
    first = submitted(test_db, org, exam, "first", 9, 30)
    second = submitted(test_db, org, exam, "second", 5, 30)
    attempt = test_db.query(models.ExamAttempt).filter_by(student_id=second.id).one()

    res = client.get(f"/student/attempts/{attempt.id}/evaluated-results", headers=headers_for(second, org)).json()
    assert res["rank"] == {"position": 2, "of": 2, "tied": False}

    exam.show_rank = False
    test_db.commit()
    res = client.get(f"/student/attempts/{attempt.id}/evaluated-results", headers=headers_for(second, org)).json()
    assert res["rank"] is None


def test_merit_list_is_staff_only_and_scoped(client, test_db):
    org, owner, exam = setup(test_db)
    kid = submitted(test_db, org, exam, "kid", 5, 10)
    other_org, other_owner, _ = setup(test_db)

    assert client.get(f"/admin/exams/{exam.id}/merit", headers=headers_for(kid, org)).status_code == 403
    assert client.get(f"/admin/exams/{exam.id}/merit", headers=headers_for(other_owner, other_org)).status_code == 404
