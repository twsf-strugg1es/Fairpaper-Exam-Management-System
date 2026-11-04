"""One answer per question per attempt, enforced by the database, not only by the upsert."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app import crud, models, schemas
from tests.test_organizations import headers_for, make_exam, make_org, make_user


def start(client, db):
    org = make_org(db, "Answers Coaching")
    student = make_user(db, "student@answers.com", org, models.ROLE_CANDIDATE)
    exam = make_exam(db, org, "Chemistry")
    h = headers_for(student, org)
    attempt = client.post(f"/student/exams/{exam.id}/start", headers=h).json()["attempt"]
    attempt["uuid"] = uuid.UUID(attempt["id"])
    return student, exam, attempt, h


def test_saving_twice_keeps_one_answer(client, test_db):
    student, exam, attempt, h = start(client, test_db)
    q = exam.questions[0]
    for value in ("a", "b"):
        res = client.post(f"/student/attempts/{attempt['id']}/save-answer", headers=h, json={"question_id": str(q.id), "answer_data": value})
        assert res.status_code == 200, res.text
    answers = test_db.query(models.Answer).filter_by(question_id=q.id).all()
    assert len(answers) == 1 and answers[0].answer_data == "b"


def test_the_database_refuses_a_second_row(client, test_db):
    student, exam, attempt, h = start(client, test_db)
    q = exam.questions[0]
    crud.save_answer(test_db, attempt["uuid"], student.id, schemas.AnswerCreate(question_id=q.id, answer_data="a"))
    test_db.add(models.Answer(attempt_id=attempt["uuid"], question_id=q.id, answer_data="b"))
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_a_save_that_loses_the_race_updates_the_winner(client, test_db, monkeypatch):
    student, exam, attempt, h = start(client, test_db)
    q = exam.questions[0]
    attempt_id = attempt["uuid"]
    # The other request's row lands between our lookup and our insert
    test_db.add(models.Answer(attempt_id=attempt_id, question_id=q.id, answer_data="from the other tab"))
    test_db.commit()

    real_query = test_db.query
    calls = {"n": 0}

    def query(*entities, **kw):
        result = real_query(*entities, **kw)
        # identity, not ==: comparing a Column with == builds a SQL expression
        if len(entities) == 1 and entities[0] is models.Answer and calls["n"] == 0:
            calls["n"] += 1

            class Miss:
                def filter(self, *a, **k):
                    return self

                def first(self):
                    return None
            return Miss()
        return result

    monkeypatch.setattr(test_db, "query", query)
    saved = crud.save_answer(test_db, attempt_id, student.id, schemas.AnswerCreate(question_id=q.id, answer_data="mine"))
    monkeypatch.undo()
    assert saved is True
    assert test_db.query(models.Answer).filter_by(question_id=q.id).one().answer_data == "mine"
    assert test_db.query(models.Answer).filter_by(question_id=q.id).count() == 1
