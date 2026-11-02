"""Tenant isolation for every endpoint (task 5.1).

Organization B's staff and candidates call every organization-scoped endpoint with organization A's ids and are
refused (403 or 404); B's lists show nothing of A; B's own exams, groups and imports can't point at A's questions,
groups or students; and afterwards every row of A is exactly as it was, with no email sent to A's people. Inside A,
each role is refused what it may not do, and one candidate can't reach another's attempt.

test_every_endpoint_is_covered fails for an endpoint added without a case here, so new endpoints get the same check.
"""
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from openpyxl import Workbook

from app import models, notify
from app.main import app
from tests.test_organizations import headers_for, make_org, make_user

# No organization involved: signing in and up, password reset, email links, the waitlist, health
PUBLIC = {
    ("GET", "/health"), ("POST", "/token"), ("POST", "/signup"), ("POST", "/signup/organization"),
    ("POST", "/password-reset/request"), ("POST", "/password-reset/confirm"), ("POST", "/verify-email"),
    ("POST", "/waitlist"), ("POST", "/waitlist/unsubscribe"),
}
# The signed-in person's own account, with no X-Organization-Id
OWN_ACCOUNT = {
    ("GET", "/me"), ("POST", "/token/refresh"), ("POST", "/verify-email/resend"), ("POST", "/organizations"),
    ("POST", "/organizations/join"), ("GET", "/profile/student"), ("PUT", "/profile/student"),
    ("POST", "/profile/change-password"),
}

STAFF, MANAGER, CANDIDATE, MEMBER = "staff", "manager", "candidate", "member"
REFUSED, OWN, LIST = "refused", "own", "list"  # A's ids in the path or body | acts on B only | B's own rows only


def _window(**body):
    now = datetime.now(timezone.utc)
    return {"start_time": (now - timedelta(minutes=5)).isoformat(), "end_time": (now + timedelta(hours=2)).isoformat(),
            "duration_minutes": 60, "require_fullscreen": False, **body}


def _sheet(*rows):
    book = Workbook()
    for row in rows:
        book.active.append(row)
    data = io.BytesIO()
    book.save(data)
    return data.getvalue()


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
GRADE = {"json": {"score_awarded": 1, "comment": "Taken over"}}
QUESTION = {"title": "Taken over", "complexity": "easy", "type": "single_choice", "options": ["x", "y"],
            "correct_answers": "x", "max_score": 1}
IMPORT = {"files": {"file": ("students.xlsx", _sheet(["email", "name"], ["new.kid@beta.com", "New Kid"]), XLSX)}}

# One case per organization-scoped endpoint: (role, what to expect, request). Path parameters are filled with A's
# ids (`a`); a request may also use B's own (`b`). A role's caller is B's owner, or B's candidate for CANDIDATE.
CASES = {
    ("POST", "/admin/answers/{answer_id}/evaluate"): (STAFF, REFUSED, lambda a, b: GRADE),
    ("GET", "/admin/answers/{answer_id}/evaluation"): (STAFF, REFUSED, None),
    ("GET", "/admin/attempts/{attempt_id}/integrity"): (STAFF, REFUSED, None),
    ("GET", "/admin/attempts/{attempt_id}/results"): (STAFF, REFUSED, None),
    ("POST", "/admin/evaluations/answers/{answer_id}/submit"): (STAFF, REFUSED, lambda a, b: GRADE),
    ("GET", "/admin/evaluations/attempts/{attempt_id}"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/"): (STAFF, LIST, None),
    ("POST", "/admin/exams/"): (STAFF, REFUSED, lambda a, b: {"json": _window(title="Taken over", question_ids=[a["question_id"]])}),
    ("GET", "/admin/exams/attempts/{attempt_id}"): (STAFF, REFUSED, None),
    ("POST", "/admin/exams/attempts/{attempt_id}/evaluate"): (STAFF, REFUSED, lambda a, b: {"json": {"answers": [{"answer_id": a["answer_id"], "score": 1}]}}),
    ("DELETE", "/admin/exams/{exam_id}"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/{exam_id}"): (STAFF, REFUSED, None),
    ("PUT", "/admin/exams/{exam_id}"): (STAFF, REFUSED, lambda a, b: {"json": _window(title="Taken over", question_ids=[b["question_id"]])}),
    ("GET", "/admin/exams/{exam_id}/analytics"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/{exam_id}/attempts"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/{exam_id}/export.xlsx"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/{exam_id}/extra-time"): (STAFF, REFUSED, None),
    ("PUT", "/admin/exams/{exam_id}/extra-time/{student_id}"): (STAFF, REFUSED, lambda a, b: {"json": {"minutes": 30}}),
    ("GET", "/admin/exams/{exam_id}/grading"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/{exam_id}/grading/{question_id}"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/{exam_id}/merit"): (STAFF, REFUSED, None),
    ("POST", "/admin/exams/{exam_id}/publish"): (STAFF, REFUSED, None),
    ("GET", "/admin/exams/{exam_id}/result-cards"): (STAFF, REFUSED, None),
    ("DELETE", "/admin/exams/{exam_id}/results/release"): (STAFF, REFUSED, None),
    ("POST", "/admin/exams/{exam_id}/results/release"): (STAFF, REFUSED, None),
    ("POST", "/admin/exams/{exam_id}/unpublish"): (STAFF, REFUSED, None),
    ("POST", "/admin/preview-questions/"): (STAFF, OWN, lambda a, b: {"files": {"file": ("q.xlsx", b["template"], XLSX)}}),
    ("GET", "/admin/questions-template"): (STAFF, OWN, None),
    ("GET", "/admin/questions/"): (STAFF, LIST, None),
    ("POST", "/admin/questions/"): (STAFF, OWN, lambda a, b: {"json": QUESTION}),
    # Answers 200 and counts A's ids as failed: they are skipped, which the snapshot confirms
    ("POST", "/admin/questions/delete-bulk"): (STAFF, OWN, lambda a, b: {"json": {"question_ids": [a["question_id"], a["written"]]}}),
    ("DELETE", "/admin/questions/{question_id}"): (STAFF, REFUSED, None),
    ("GET", "/admin/questions/{question_id}"): (STAFF, REFUSED, None),
    ("PUT", "/admin/questions/{question_id}"): (STAFF, REFUSED, lambda a, b: {"json": QUESTION}),
    ("POST", "/admin/questions/{question_id}/duplicate"): (STAFF, REFUSED, None),
    ("GET", "/admin/students/"): (STAFF, LIST, None),
    ("DELETE", "/admin/students/{student_id}"): (MANAGER, REFUSED, None),
    ("POST", "/admin/upload-questions/"): (STAFF, OWN, lambda a, b: {"files": {"file": ("q.xlsx", b["template"], XLSX)}}),
    ("GET", "/org"): (MEMBER, OWN, None),
    ("PATCH", "/org"): (MANAGER, OWN, lambda a, b: {"json": {"name": "Beta Academy, renamed"}}),
    ("GET", "/org/groups"): (STAFF, LIST, None),
    ("POST", "/org/groups"): (MANAGER, OWN, lambda a, b: {"json": {"name": "Beta evening batch"}}),
    ("DELETE", "/org/groups/{group_id}"): (MANAGER, REFUSED, None),
    ("PATCH", "/org/groups/{group_id}"): (MANAGER, REFUSED, lambda a, b: {"json": {"name": "Taken over"}}),
    ("POST", "/org/groups/{group_id}/join-code/regenerate"): (MANAGER, REFUSED, None),
    ("POST", "/org/groups/{group_id}/members"): (MANAGER, REFUSED, lambda a, b: {"json": {"user_ids": [b["student_id"]]}}),
    ("DELETE", "/org/groups/{group_id}/members/{user_id}"): (MANAGER, REFUSED, None),
    ("POST", "/org/join-code/regenerate"): (MANAGER, OWN, None),
    ("GET", "/org/members"): (MANAGER, LIST, None),
    ("POST", "/org/members"): (MANAGER, OWN, lambda a, b: {"json": {"email": "new.teacher@beta.com", "role": "examiner"}}),
    ("DELETE", "/org/members/{user_id}"): (MANAGER, REFUSED, None),
    ("PATCH", "/org/members/{user_id}"): (MANAGER, REFUSED, lambda a, b: {"json": {"role": "examiner"}}),
    ("POST", "/org/members/{user_id}/invite"): (MANAGER, REFUSED, None),
    ("GET", "/org/setup"): (STAFF, OWN, None),
    ("POST", "/org/students/import"): (MANAGER, REFUSED, lambda a, b: {**IMPORT, "data": {"group_ids": a["group_id"]}}),
    ("POST", "/org/students/import/preview"): (MANAGER, OWN, lambda a, b: IMPORT),
    ("GET", "/profile/student/{student_id}"): (STAFF, REFUSED, None),
    ("GET", "/student/attempts/{attempt_id}/answers"): (CANDIDATE, REFUSED, None),
    ("GET", "/student/attempts/{attempt_id}/clock"): (CANDIDATE, REFUSED, None),
    ("GET", "/student/attempts/{attempt_id}/evaluated-results"): (CANDIDATE, REFUSED, None),
    ("POST", "/student/attempts/{attempt_id}/events"): (CANDIDATE, REFUSED, lambda a, b: {"json": {"events": [{"type": "focus_lost"}]}}),
    ("POST", "/student/attempts/{attempt_id}/questions/{question_id}/next"): (CANDIDATE, REFUSED, None),
    ("GET", "/student/attempts/{attempt_id}/results"): (CANDIDATE, REFUSED, None),
    ("POST", "/student/attempts/{attempt_id}/resume"): (CANDIDATE, REFUSED, None),
    ("POST", "/student/attempts/{attempt_id}/save-answer"): (CANDIDATE, REFUSED, lambda a, b: {"json": {"question_id": a["question_id"], "answer_data": "right"}}),
    ("POST", "/student/attempts/{attempt_id}/sections/{section_id}/finish"): (CANDIDATE, REFUSED, None),
    ("POST", "/student/attempts/{attempt_id}/submit"): (CANDIDATE, REFUSED, None),
    ("GET", "/student/completed-exams/"): (CANDIDATE, LIST, None),
    ("GET", "/student/exams/"): (CANDIDATE, LIST, None),
    ("POST", "/student/exams/{exam_id}/start"): (CANDIDATE, REFUSED, None),
    ("GET", "/student/unfinished-attempts/"): (CANDIDATE, LIST, None),
}

# Which of a side's ids fills each path parameter. Staff reach the graded paper; candidates the papers still open.
PARAMS = {
    "answer_id": "answer_id", "exam_id": "exam_id", "question_id": "question_id", "student_id": "student_id",
    "user_id": "student_id", "group_id": "group_id", "section_id": "section_id",
}
ATTEMPT_FOR = {"/questions/{question_id}/next": "attempt_paced", "/evaluated-results": "attempt_done",
               "/results": "attempt_done"}


def _url(method, path, ids, role):
    values = {name: ids[key] for name, key in PARAMS.items()}
    values["attempt_id"] = ids["attempt_done"] if role != CANDIDATE else next(
        (ids[key] for tail, key in ATTEMPT_FOR.items() if path.endswith(tail)), ids["attempt_live"])
    if path == "/admin/exams/{exam_id}/grading/{question_id}":
        values["question_id"] = ids["written"]
    if path.startswith("/admin/exams/{exam_id}/extra-time"):
        values["exam_id"] = ids["live_exam_id"]
    return path.format(**values)


def _populate(client, db, org, owner, student, name):
    """A side's data, made through the API: a group, two questions, three exams and three papers."""
    staff, kid = headers_for(owner, org), headers_for(student, org)

    def ok(res):
        assert res.status_code < 300, res.text
        return res.json()

    def exam(**body):
        made = ok(client.post("/admin/exams/", json=_window(**body), headers=staff))
        ok(client.post(f"/admin/exams/{made['id']}/publish", headers=staff))
        return made

    group = ok(client.post("/org/groups", json={"name": f"{name} batch"}, headers=staff))
    ok(client.post(f"/org/groups/{group['id']}/members", json={"user_ids": [str(student.id)]}, headers=staff))
    choice = ok(client.post("/admin/questions/", headers=staff, json={
        "title": f"{name}: pick the right one", "complexity": "easy", "type": "single_choice",
        "options": ["right", "wrong"], "correct_answers": "right", "max_score": 1, "tags": ["isolation"]}))
    written = ok(client.post("/admin/questions/", headers=staff, json={
        "title": f"{name}: explain why", "complexity": "medium", "type": "text", "max_score": 4}))

    graded = exam(title=f"{name} graded", question_ids=[choice["id"], written["id"]], group_ids=[group["id"]])
    parts = exam(title=f"{name} in two parts", question_ids=[choice["id"], written["id"]],
                 sections=[{"title": "Part A", "time_limit_minutes": 20}, {"title": "Part B", "time_limit_minutes": 20}],
                 question_sections={choice["id"]: 0, written["id"]: 1})
    rapid = exam(title=f"{name} one at a time", question_ids=[choice["id"]], timing_mode="per_question",
                 shuffle_questions=False)

    # A submitted paper with a written answer to grade; a sectioned and a per-question paper still being written
    done = ok(client.post(f"/student/exams/{graded['id']}/start", headers=kid))["attempt"]["id"]
    for question, answer in ((choice, "right"), (written, "Light scatters.")):
        ok(client.post(f"/student/attempts/{done}/save-answer", headers=kid,
                       json={"question_id": question["id"], "answer_data": answer}))
    ok(client.post(f"/student/attempts/{done}/submit", headers=kid))
    session = ok(client.post(f"/student/exams/{parts['id']}/start", headers=kid))
    live = session["attempt"]["id"]
    ok(client.post(f"/student/attempts/{live}/save-answer", headers=kid,
                   json={"question_id": choice["id"], "answer_data": "wrong"}))
    paced = ok(client.post(f"/student/exams/{rapid['id']}/start", headers=kid))["attempt"]["id"]
    ok(client.put(f"/admin/exams/{parts['id']}/extra-time/{student.id}", json={"minutes": 5}, headers=staff))
    answer = db.query(models.Answer).filter_by(attempt_id=uuid.UUID(done), question_id=uuid.UUID(written["id"])).one()
    return {
        "exam_id": graded["id"], "live_exam_id": parts["id"], "rapid_exam_id": rapid["id"],
        "question_id": choice["id"], "written": written["id"], "answer_id": str(answer.id),
        "attempt_done": done, "attempt_live": live, "attempt_paced": paced, "section_id": session["exam"]["sections"][0]["id"],
        "student_id": str(student.id), "group_id": group["id"],
    }


def _rows(db, model, *criteria):
    columns = [c.key for c in model.__table__.columns]
    return sorted(tuple(str(getattr(row, c)) for c in columns) for row in db.query(model).filter(*criteria))


def _snapshot(db, org_id):
    """Every row that belongs to an organization, as text, to compare before and after."""
    db.expire_all()
    exams = [e.id for e in db.query(models.Exam).filter(models.Exam.organization_id == org_id)]
    attempts = [a.id for a in db.query(models.ExamAttempt).filter(models.ExamAttempt.exam_id.in_(exams))]
    answers = [a.id for a in db.query(models.Answer).filter(models.Answer.attempt_id.in_(attempts))]
    groups = [g.id for g in db.query(models.Group).filter(models.Group.organization_id == org_id)]
    members = [m.user_id for m in db.query(models.Membership).filter(models.Membership.organization_id == org_id)]
    tables = {
        "organization": _rows(db, models.Organization, models.Organization.id == org_id),
        "memberships": _rows(db, models.Membership, models.Membership.organization_id == org_id),
        "users": _rows(db, models.User, models.User.id.in_(members)),
        "groups": _rows(db, models.Group, models.Group.organization_id == org_id),
        "questions": _rows(db, models.Question, models.Question.organization_id == org_id),
        "exams": _rows(db, models.Exam, models.Exam.organization_id == org_id),
        "sections": _rows(db, models.ExamSection, models.ExamSection.exam_id.in_(exams)),
        "extra_time": _rows(db, models.ExamExtraTime, models.ExamExtraTime.exam_id.in_(exams)),
        "attempts": _rows(db, models.ExamAttempt, models.ExamAttempt.id.in_(attempts)),
        "attempt_sections": _rows(db, models.AttemptSection, models.AttemptSection.attempt_id.in_(attempts)),
        "question_timings": _rows(db, models.AttemptQuestionTiming, models.AttemptQuestionTiming.attempt_id.in_(attempts)),
        "events": _rows(db, models.IntegrityEvent, models.IntegrityEvent.attempt_id.in_(attempts)),
        "answers": _rows(db, models.Answer, models.Answer.id.in_(answers)),
        "evaluations": _rows(db, models.Evaluation, models.Evaluation.answer_id.in_(answers)),
    }
    links = ((models.group_members, models.group_members.c.group_id, groups),
             (models.exam_groups, models.exam_groups.c.exam_id, exams),
             (models.exam_questions, models.exam_questions.c.exam_id, exams))
    for table, key, wanted in links:
        tables[table.name] = sorted(str(tuple(row)) for row in db.execute(table.select().where(key.in_(wanted))))
    return tables


@pytest.fixture
def world(client, test_db):
    a, b = make_org(test_db, "Alpha Coaching"), make_org(test_db, "Beta Academy")
    people = {
        "owner_a": make_user(test_db, "owner@alpha.com", a, models.ROLE_OWNER),
        "examiner_a": make_user(test_db, "examiner@alpha.com", a, models.ROLE_EXAMINER),
        "student_a": make_user(test_db, "student@alpha.com", a, models.ROLE_CANDIDATE),
        "other_a": make_user(test_db, "classmate@alpha.com", a, models.ROLE_CANDIDATE),
        "owner_b": make_user(test_db, "owner@beta.com", b, models.ROLE_OWNER),
        "student_b": make_user(test_db, "student@beta.com", b, models.ROLE_CANDIDATE),
    }
    ids_a = _populate(client, test_db, a, people["owner_a"], people["student_a"], "Alpha")
    ids_b = _populate(client, test_db, b, people["owner_b"], people["student_b"], "Beta")
    ids_b["template"] = client.get("/admin/questions-template", headers=headers_for(people["owner_b"], b)).content
    return {"a": a, "b": b, **people, "ids_a": ids_a, "ids_b": ids_b}


def _call(client, method, path, case, w, caller, org):
    role, _, request = case
    kwargs = request(w["ids_a"], w["ids_b"]) if request else {}
    return client.request(method, _url(method, path, w["ids_a"], role), headers=headers_for(caller, org), **kwargs)


def _b_caller(w, role):
    return w["student_b"] if role == CANDIDATE else w["owner_b"]


def test_every_endpoint_is_covered():
    endpoints = {(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops}
    assert endpoints - PUBLIC - OWN_ACCOUNT - set(CASES) == set(), "add a tenant-isolation case for these endpoints"
    assert set(CASES) | PUBLIC | OWN_ACCOUNT == endpoints, "these cases name endpoints that no longer exist"


def test_another_organization_gets_nothing_of_a(client, test_db, world):
    w = world
    before = _snapshot(test_db, w["a"].id)
    notify.outbox.clear()
    markers = [v for k, v in w["ids_a"].items()] + ["Alpha", "alpha.com"]
    for (method, path), case in CASES.items():
        role, expect, _ = case
        res = _call(client, method, path, case, w, _b_caller(w, role), w["b"])
        if expect == REFUSED:
            assert res.status_code in (400, 403, 404, 409, 422), (method, path, res.status_code, res.text)
            if res.status_code in (400, 409, 422):
                # A refusal for any other reason must still not have found A's rows
                assert not any(m in res.text for m in markers), (method, path, res.text)
        else:
            assert res.status_code < 300, (method, path, res.status_code, res.text)
            if "json" in res.headers.get("content-type", ""):
                assert not any(m in res.text for m in markers), (method, path, res.text)
    assert _snapshot(test_db, w["a"].id) == before
    assert not [e for e in notify.outbox if "alpha.com" in e.to]


def test_path_ids_from_a_are_not_found(client, world):
    """Stricter than the sweep above: with A's ids in the path, the answer is 403 or 404, never another error."""
    w = world
    for (method, path), case in CASES.items():
        role, expect, _ = case
        if expect == REFUSED and "{" in path:
            res = _call(client, method, path, case, w, _b_caller(w, role), w["b"])
            assert res.status_code in (403, 404), (method, path, res.status_code, res.text)


def test_naming_another_organization_in_the_header_is_refused(client, world):
    w = world
    for (method, path), case in CASES.items():
        res = _call(client, method, path, case, w, _b_caller(w, case[0]), w["a"])
        assert res.status_code == 403, (method, path, res.status_code, res.text)


def test_each_role_is_refused_what_it_may_not_do(client, world):
    w = world
    refusals = {STAFF: [w["student_a"]], MANAGER: [w["student_a"], w["examiner_a"]], CANDIDATE: [w["owner_a"], w["examiner_a"]]}
    for (method, path), case in CASES.items():
        for caller in refusals.get(case[0], []):
            res = _call(client, method, path, case, w, caller, w["a"])
            assert res.status_code == 403, (method, path, caller.email, res.status_code, res.text)


def test_a_candidate_cant_reach_a_classmates_attempt(client, test_db, world):
    w = world
    before = _snapshot(test_db, w["a"].id)
    for (method, path), case in CASES.items():
        if case[0] == CANDIDATE and "{attempt_id}" in path:
            res = _call(client, method, path, case, w, w["other_a"], w["a"])
            assert res.status_code in (403, 404), (method, path, res.status_code, res.text)
    assert _snapshot(test_db, w["a"].id) == before


def test_bs_own_exams_groups_and_papers_cant_point_at_a(client, test_db, world):
    """B's own resources, with one of A's ids where an id of B's belongs."""
    w = world
    a, b = w["ids_a"], w["ids_b"]
    owner, kid = headers_for(w["owner_b"], w["b"]), headers_for(w["student_b"], w["b"])
    before = _snapshot(test_db, w["a"].id)
    attempts = [
        (owner, "POST", "/admin/exams/", {"json": _window(title="Mixed", question_ids=[b["question_id"]], group_ids=[a["group_id"]])}),
        (owner, "PUT", f"/admin/exams/{b['exam_id']}", {"json": _window(title="Mixed", question_ids=[a["question_id"]])}),
        (owner, "PUT", f"/admin/exams/{b['live_exam_id']}/extra-time/{a['student_id']}", {"json": {"minutes": 30}}),
        (owner, "GET", f"/admin/exams/{b['exam_id']}/grading/{a['written']}", {}),
        (owner, "POST", f"/admin/exams/attempts/{b['attempt_done']}/evaluate", {"json": {"answers": [{"answer_id": a["answer_id"], "score": 1}]}}),
        (owner, "POST", f"/org/groups/{b['group_id']}/members", {"json": {"user_ids": [a["student_id"]]}}),
        (kid, "POST", f"/student/attempts/{b['attempt_live']}/save-answer", {"json": {"question_id": a["question_id"], "answer_data": "right"}}),
        (kid, "POST", f"/student/attempts/{b['attempt_live']}/sections/{a['section_id']}/finish", {}),
        (kid, "POST", f"/student/attempts/{b['attempt_paced']}/questions/{a['question_id']}/next", {}),
    ]
    for headers, method, url, kwargs in attempts:
        res = client.request(method, url, headers=headers, **kwargs)
        assert res.status_code in (400, 403, 404, 409, 422), (method, url, res.status_code, res.text)
    # These answer with B's own rows: removing someone who isn't in the group changes nothing
    for res in (client.delete(f"/org/groups/{b['group_id']}/members/{a['student_id']}", headers=owner),
                client.get(f"/admin/exams/{b['exam_id']}/result-cards", params={"attempt": a["attempt_done"]}, headers=owner)):
        assert res.status_code in (200, 404) and "Alpha" not in res.text and a["student_id"] not in res.text, res.text
    assert _snapshot(test_db, w["a"].id) == before
