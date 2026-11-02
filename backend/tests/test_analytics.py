"""Exam analytics (task 4.12): difficulty and discrimination per question, option counts, topics and the spread of
scores, from a class whose answers give known numbers."""
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from tests.test_organizations import headers_for, make_org, make_user


def question(db, org, title, qtype="single_choice", marks=1, tags=(), options=None, correct=None):
    q = models.Question(organization_id=org.id, title=title, complexity="medium", type=qtype, max_score=marks,
                        options=options, correct_answers=correct, tags=list(tags))
    db.add(q)
    db.commit()
    return q


def setup(client, db):
    org = make_org(db, f"Stats {uuid.uuid4().hex[:6]}")
    owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@stats.com", org, models.ROLE_OWNER)
    q = {
        "easy": question(db, org, "2 + 2?", tags=["arithmetic"], options=["4", "5"], correct="4"),
        "sharp": question(db, org, "Solve 2x = 6", marks=3, tags=["algebra"], options=["x=2", "x=3", "x=4"], correct="x=3"),
        "odd": question(db, org, "Solve x + 1 = 3", tags=["algebra"], options=["2", "3"], correct="2"),
        "essay": question(db, org, "Explain how you solved it", qtype="text", tags=["algebra"]),
    }
    now = datetime.now(timezone.utc)
    exam = client.post("/admin/exams/", headers=headers_for(owner, org), json={
        "title": "Algebra check", "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 30, "require_fullscreen": False,
        "question_ids": [str(x.id) for x in q.values()]}).json()
    client.post(f"/admin/exams/{exam['id']}/publish", headers=headers_for(owner, org))
    return org, owner, q, exam


def sit(client, db, org, exam, q, answers):
    kid = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@stats.com", org, models.ROLE_CANDIDATE)
    h = headers_for(kid, org)
    attempt = client.post(f"/student/exams/{exam['id']}/start", headers=h).json()["attempt"]["id"]
    for key, value in {**answers, "essay": "I moved the 1 across."}.items():
        client.post(f"/student/attempts/{attempt}/save-answer", headers=h, json={"question_id": str(q[key].id), "answer_data": value})
    client.post(f"/student/attempts/{attempt}/submit", headers=h)


# Two strong students get the 3-mark question right and the "odd" one wrong; the others the other way round
CLASS = [
    {"easy": "4", "sharp": "x=3", "odd": "3"},  # 4 of 6
    {"easy": "4", "sharp": "x=3", "odd": "3"},  # 4
    {"easy": "4", "sharp": "x=2", "odd": "2"},  # 2
    {"easy": "4", "sharp": "x=4", "odd": "3"},  # 1
    {"easy": "4", "sharp": "x=2", "odd": "2"},  # 2
    {"easy": "4", "sharp": "x=2", "odd": "2"},  # 2
]


def test_each_question_gets_its_difficulty_and_discrimination(client, test_db):
    org, owner, q, exam = setup(client, test_db)
    for answers in CLASS:
        sit(client, test_db, org, exam, q, answers)
    data = client.get(f"/admin/exams/{exam['id']}/analytics", headers=headers_for(owner, org)).json()
    items = {item["question_id"]: item for item in data["items"]}
    easy, sharp, odd, essay = (items[str(q[k].id)] for k in ("easy", "sharp", "odd", "essay"))

    assert data["submitted"] == 6
    assert (easy["difficulty"], easy["discrimination"], easy["flags"]) == (1.0, 0.0, ["very_easy", "weak"])
    assert (sharp["difficulty"], sharp["discrimination"], sharp["flags"]) == (0.333, 1.0, [])
    assert (odd["difficulty"], odd["discrimination"], odd["flags"]) == (0.5, -0.5, ["check_key"])
    assert essay["difficulty"] is None and essay["waiting"] == 6 and essay["options"] is None
    assert {c["option"]: (c["count"], c["correct"]) for c in sharp["options"]["choices"]} == {
        "x=2": (3, False), "x=3": (2, True), "x=4": (1, False)}

    topics = {t["tag"]: t for t in data["topics"]}
    assert topics["arithmetic"]["difficulty"] == 1.0
    assert topics["algebra"]["difficulty"] == round((6 + 3) / (18 + 6), 3) and topics["algebra"]["questions"] == 3
    assert data["distribution"] == [0, 1, 0, 3, 0, 0, 2, 0, 0, 0]
    assert data["summary"] == {"mean": 0.417, "median": 0.333, "highest": 0.667, "lowest": 0.167}


def test_a_small_class_gets_no_discrimination(client, test_db):
    org, owner, q, exam = setup(client, test_db)
    for answers in CLASS[:3]:
        sit(client, test_db, org, exam, q, answers)
    data = client.get(f"/admin/exams/{exam['id']}/analytics", headers=headers_for(owner, org)).json()
    assert data["discrimination_needs"] == 5
    assert all(item["discrimination"] is None for item in data["items"])
    assert all("weak" not in item["flags"] and "check_key" not in item["flags"] for item in data["items"])


def test_only_this_organizations_staff_see_it(client, test_db):
    org, owner, q, exam = setup(client, test_db)
    other = make_org(test_db, f"Other {uuid.uuid4().hex[:6]}")
    outsider = make_user(test_db, f"o-{uuid.uuid4().hex[:6]}@other.com", other, models.ROLE_OWNER)
    assert client.get(f"/admin/exams/{exam['id']}/analytics", headers=headers_for(outsider, other)).status_code == 404
    kid = make_user(test_db, f"k-{uuid.uuid4().hex[:6]}@stats.com", org, models.ROLE_CANDIDATE)
    assert client.get(f"/admin/exams/{exam['id']}/analytics", headers=headers_for(kid, org)).status_code == 403
    empty = client.get(f"/admin/exams/{exam['id']}/analytics", headers=headers_for(owner, org)).json()
    assert empty["submitted"] == 0 and empty["items"] == [] and empty["summary"]["mean"] is None
