"""Answer keys stay with staff (task 5.1, AGENTS rule 2).

A candidate sits four exams (every question type; one question at a time; timed sections; results held back for
release) and every response they can get while it matters is searched for an answer key: a filled-in
`correct_answers` or `is_correct`, a key's values, an ordering question in its stored (correct) order, or the notes
staff keep for graders. The candidate answers wrongly throughout, so their own answers never look like the key.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from tests.test_organizations import headers_for, make_org, make_user

NOTE = "GRADER-NOTE"  # in every question's staff-only notes
ORDER = ["Ice", "Water", "Steam", "Plasma"]  # an ordering question's stored order, which is its answer
QUESTIONS = {
    "single_choice": {"title": "Which stone is green?", "options": ["Ruby", "Emerald", "Sapphire"], "correct_answers": "Emerald"},
    "multi_choice": {"title": "Which are metals?", "options": ["Iron", "Wood", "Copper"], "correct_answers": ["Iron", "Copper"]},
    "true_false": {"title": "Sound travels in a vacuum.", "correct_answers": "false"},
    "fill_blank": {"title": "The rarest gem in this list is ___.", "correct_answers": [["Taaffeite"]]},
    "numeric": {"title": "Give the constant to four places.", "correct_answers": {"value": 4.2817, "tolerance": 0.0003}},
    "matching": {"title": "Match each tool to its use.",
                 "options": {"left": ["Saw", "Pen", "Spoon"], "right": ["Cutting", "Writing", "Stirring", "Sleeping"]},
                 "correct_answers": {"Saw": "Cutting", "Pen": "Writing", "Spoon": "Stirring"}},
    "ordering": {"title": "Put the states of water in order of heat.", "options": ORDER},
    "text": {"title": "Explain why the sky is blue."},
    "image_upload": {"title": "Draw the light path through a prism."},
}
WRONG = {"single_choice": "Ruby", "multi_choice": ["Wood"], "true_false": "true", "fill_blank": ["Diamond"],
         "numeric": "5", "matching": {"Saw": "Sleeping", "Pen": "Cutting", "Spoon": "Writing"},
         "ordering": ["Plasma", "Ice", "Water", "Steam"], "text": "Because it reflects the sea."}
KEY_VALUES = ("Taaffeite", 4.2817, 0.0003, NOTE)


def _secrets(payload, path="$"):
    """Every place in a JSON payload that gives away an answer key or a grader's note."""
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if key in ("correct_answers", "is_correct") and value is not None:
                found.append(f"{here} = {value!r}")
            if key == "options" and value == ORDER:
                found.append(f"{here} is the ordering question's answer")
            found += _secrets(value, here)
    elif isinstance(payload, list):
        for i, value in enumerate(payload):
            found += _secrets(value, f"{path}[{i}]")
    elif isinstance(payload, (str, int, float)) and not isinstance(payload, bool):
        if any(payload == v or (isinstance(payload, str) and isinstance(v, str) and v in payload) for v in KEY_VALUES):
            found.append(f"{path} = {payload!r}")
    return found


class Candidate:
    """Calls the API as one candidate and keeps every response to search afterwards."""

    def __init__(self, client, db, org):
        self.client = client
        self.user = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@secrecy.com", org, models.ROLE_CANDIDATE)
        self.headers = headers_for(self.user, org)
        self.seen = []

    def call(self, method, url, **kwargs):
        res = self.client.request(method, url, headers=self.headers, **kwargs)
        assert res.status_code < 300, (method, url, res.status_code, res.text)
        self.seen.append((f"{method} {url}", res.json()))
        return res.json()

    def leaks(self):
        return [f"{where}: {spot}" for where, body in self.seen for spot in _secrets(body)]


def _setup(client, db):
    org = make_org(db, "Secrecy School")
    owner = make_user(db, "owner@secrecy.com", org, models.ROLE_OWNER)
    staff = headers_for(owner, org)
    ids = {}
    for qtype, body in QUESTIONS.items():
        res = client.post("/admin/questions/", headers=staff, json={
            "complexity": "easy", "type": qtype, "max_score": 2, "description": f"{NOTE}: what full marks look like", **body})
        assert res.status_code == 201, (qtype, res.text)
        ids[qtype] = res.json()["id"]
    now = datetime.now(timezone.utc)

    def exam(types, **settings):
        made = client.post("/admin/exams/", headers=staff, json={
            "title": f"Secrecy {len(types)}", "start_time": (now - timedelta(minutes=5)).isoformat(),
            "end_time": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 30, "require_fullscreen": False,
            "question_ids": [ids[t] for t in types], **settings})
        assert made.status_code == 200, made.text
        assert client.post(f"/admin/exams/{made.json()['id']}/publish", headers=staff).status_code == 200
        return made.json()["id"]

    return org, owner, ids, exam


def _answer(kid, attempt, ids, types):
    for qtype in types:
        if qtype in WRONG:
            kid.call("POST", f"/student/attempts/{attempt}/save-answer",
                     json={"question_id": ids[qtype], "answer_data": WRONG[qtype], "client_seq": 1})


def test_nothing_a_candidate_receives_while_the_exam_is_open_carries_a_key(client, test_db):
    org, _, ids, exam = _setup(client, test_db)
    exam_id = exam(list(QUESTIONS))
    kid = Candidate(client, test_db, org)
    kid.call("GET", "/student/exams/")
    attempt = kid.call("POST", f"/student/exams/{exam_id}/start")["attempt"]["id"]
    _answer(kid, attempt, ids, QUESTIONS)
    kid.call("POST", f"/student/attempts/{attempt}/events", json={"events": [{"type": "focus_lost"}, {"type": "focus_returned"}]})
    for url in (f"/student/attempts/{attempt}/answers", f"/student/attempts/{attempt}/clock", "/student/unfinished-attempts/"):
        kid.call("GET", url)
    kid.call("POST", f"/student/attempts/{attempt}/resume")
    kid.call("POST", f"/student/attempts/{attempt}/submit")
    for url in (f"/student/attempts/{attempt}/results", f"/student/attempts/{attempt}/evaluated-results",
                "/student/completed-exams/", "/student/exams/"):
        kid.call("GET", url)
    assert kid.leaks() == []
    assert not [where for where, body in kid.seen if "owner@secrecy.com" in str(body)]  # nor who published it


def test_one_question_at_a_time_hands_out_no_key(client, test_db):
    org, _, ids, exam = _setup(client, test_db)
    paced = ["ordering", "fill_blank", "numeric"]
    exam_id = exam(paced, timing_mode="per_question", shuffle_questions=False)
    kid = Candidate(client, test_db, org)
    session = kid.call("POST", f"/student/exams/{exam_id}/start")
    attempt = session["attempt"]["id"]
    for qtype in paced[:-1]:  # Next on each question but the last, which ends with Submit
        _answer(kid, attempt, ids, [qtype])
        kid.call("POST", f"/student/attempts/{attempt}/questions/{ids[qtype]}/next")
        kid.call("GET", f"/student/attempts/{attempt}/clock")
    _answer(kid, attempt, ids, paced[-1:])
    kid.call("POST", f"/student/attempts/{attempt}/submit")
    kid.call("GET", f"/student/attempts/{attempt}/results")
    assert kid.leaks() == []


def test_timed_sections_hand_out_no_key(client, test_db):
    org, _, ids, exam = _setup(client, test_db)
    exam_id = exam(["ordering", "matching"], sections=[{"title": "Part A", "time_limit_minutes": 10},
                                                       {"title": "Part B", "time_limit_minutes": 10}],
                   question_sections={ids["ordering"]: 0, ids["matching"]: 1})
    kid = Candidate(client, test_db, org)
    session = kid.call("POST", f"/student/exams/{exam_id}/start")
    attempt, first = session["attempt"]["id"], session["exam"]["sections"][0]["id"]
    _answer(kid, attempt, ids, ["ordering"])
    kid.call("POST", f"/student/attempts/{attempt}/sections/{first}/finish")
    kid.call("POST", f"/student/attempts/{attempt}/resume")
    _answer(kid, attempt, ids, ["matching"])
    kid.call("POST", f"/student/attempts/{attempt}/submit")
    kid.call("GET", f"/student/attempts/{attempt}/results")
    assert kid.leaks() == []


def test_results_held_back_keep_the_key_after_the_exam_closes(client, test_db):
    org, _, ids, exam = _setup(client, test_db)
    exam_id = exam(list(QUESTIONS), results_release="manual")
    kid = Candidate(client, test_db, org)
    attempt = kid.call("POST", f"/student/exams/{exam_id}/start")["attempt"]["id"]
    _answer(kid, attempt, ids, QUESTIONS)
    kid.call("POST", f"/student/attempts/{attempt}/submit")
    stored = test_db.get(models.Exam, uuid.UUID(exam_id))
    stored.end_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    test_db.commit()
    for url in (f"/student/attempts/{attempt}/results", f"/student/attempts/{attempt}/evaluated-results",
                "/student/completed-exams/"):
        kid.call("GET", url)
    assert kid.leaks() == []


def test_grader_notes_stay_with_staff_even_after_the_answers_are_out(client, test_db):
    org, _, ids, exam = _setup(client, test_db)
    exam_id = exam(list(QUESTIONS))
    kid = Candidate(client, test_db, org)
    attempt = kid.call("POST", f"/student/exams/{exam_id}/start")["attempt"]["id"]
    _answer(kid, attempt, ids, QUESTIONS)
    kid.call("POST", f"/student/attempts/{attempt}/submit")
    stored = test_db.get(models.Exam, uuid.UUID(exam_id))
    stored.end_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    test_db.commit()
    results = kid.call("GET", f"/student/attempts/{attempt}/results")
    assert results["exam"]["answers_revealed"] is True  # the key is out now, by design
    kid.call("GET", f"/student/attempts/{attempt}/evaluated-results")
    assert not [where for where, body in kid.seen if NOTE in str(body)]
