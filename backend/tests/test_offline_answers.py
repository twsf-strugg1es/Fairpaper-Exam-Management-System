"""Offline-tolerant saving (task 3.8): the exam page numbers every save with `client_seq`, and the
server ignores a save older than the one it already has, so a retry delayed by a bad connection
can never overwrite a newer answer."""
from app import models
from tests.test_unique_answers import start


def save(client, h, attempt, q, value, seq=None):
    body = {"question_id": str(q.id), "answer_data": value}
    if seq is not None:
        body["client_seq"] = seq
    return client.post(f"/student/attempts/{attempt['id']}/save-answer", headers=h, json=body)


def stored(db, q):
    db.expire_all()
    return db.query(models.Answer).filter_by(question_id=q.id).one()


def test_a_late_retry_does_not_overwrite_a_newer_answer(client, test_db):
    student, exam, attempt, h = start(client, test_db)
    q = exam.questions[0]

    assert save(client, h, attempt, q, "B", seq=2).json() == {"status": "saved"}
    late = save(client, h, attempt, q, "A", seq=1)  # sent first, arrived last

    assert late.status_code == 200 and late.json() == {"status": "stale"}
    assert stored(test_db, q).answer_data == "B" and stored(test_db, q).client_seq == 2


def test_newer_saves_win_and_repeats_are_harmless(client, test_db):
    student, exam, attempt, h = start(client, test_db)
    q = exam.questions[0]

    save(client, h, attempt, q, "A", seq=1700000000001)
    assert save(client, h, attempt, q, "C", seq=1700000000005).json()["status"] == "saved"
    assert save(client, h, attempt, q, "C", seq=1700000000005).json()["status"] == "stale"  # the same retry twice
    assert stored(test_db, q).answer_data == "C"


def test_saves_without_a_number_still_work(client, test_db):
    student, exam, attempt, h = start(client, test_db)
    q = exam.questions[0]

    assert save(client, h, attempt, q, "A").json()["status"] == "saved"
    assert save(client, h, attempt, q, "B").json()["status"] == "saved"
    assert stored(test_db, q).answer_data == "B"


def test_the_number_is_checked(client, test_db):
    student, exam, attempt, h = start(client, test_db)
    q = exam.questions[0]

    assert save(client, h, attempt, q, "A", seq=-1).status_code == 422
    assert save(client, h, attempt, q, "A", seq=2**60).status_code == 422
    assert save(client, h, attempt, q, "A", seq="soon").status_code == 422


def test_stale_saves_still_respect_ownership(client, test_db):
    student, exam, attempt, h = start(client, test_db)
    from tests.test_organizations import headers_for, make_org, make_user
    other = make_user(test_db, "other@answers.com", make_org(test_db, "Other"), models.ROLE_CANDIDATE)
    res = client.post(f"/student/attempts/{attempt['id']}/save-answer", headers=headers_for(other, other.memberships[0].organization),
                      json={"question_id": str(exam.questions[0].id), "answer_data": "x", "client_seq": 9})
    assert res.status_code in (403, 404)
