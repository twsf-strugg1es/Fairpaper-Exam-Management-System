"""Question types (task 4.7, PRD F19): true or false, fill in the blank, numeric, matching and ordering are written
in the editor or a workbook, sent to students without their key, and graded automatically."""
import io
import uuid
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest

from app import models, question_types as qt
from tests.test_organizations import headers_for, make_org, make_user

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- what people type

@pytest.mark.parametrize("typed, number", [
    ("9.8", 9.8), (" 9,81 ", 9.81), ("0,500", 0.5), ("1,000", 1000), ("1,00,000", 100000), ("12,34,567", 1234567),
    ("1,000.5", 1000.5), ("1.000,5", 1000.5), ("১২.৫", 12.5), ("−3", -3), ("-0,5", -0.5), ("1 000", 1000),
    ("6.02e23", 6.02e23), (7, 7.0), (2.5, 2.5), ("٣٫١٤", 3.14),
])
def test_numbers_are_read_the_way_people_type_them(typed, number):
    assert qt.parse_number(typed) == pytest.approx(number)


@pytest.mark.parametrize("typed", ["", "abc", "nan", "inf", "-infinity", "1.2.3", "9.8 m/s", True, None])
def test_anything_but_one_number_is_refused(typed):
    with pytest.raises(ValueError):
        qt.parse_number(typed)


def test_typed_words_are_compared_kindly():
    assert qt.normalize_text("  The   DHAKA. ") == "the dhaka"
    assert qt.normalize_text("Café") == qt.normalize_text("Café")  # composed or not
    assert qt.normalize_text("STRASSE") == qt.normalize_text("straße")
    assert qt.normalize_text("ঢাকা") == "ঢাকা" and qt.normalize_text("১০") == "10"


# --- answer keys

def test_choice_keys_are_kept_as_before():
    assert qt.clean("single_choice", "2+2?", [1, 2, 4], 4) == (["1", "2", "4"], "4")
    assert qt.clean("multi_choice", "Primes", ["2", "4", "5"], ["5", "2", "5"]) == (["2", "4", "5"], ["5", "2"])
    assert qt.clean("text", "Explain", ["x"], "y") == (None, None)


def test_true_or_false_keys():
    assert qt.clean("true_false", "Water boils at 100 °C.", None, True) == (["true", "false"], "true")
    assert qt.clean("true_false", "x", None, "FALSE")[1] == "false"
    assert qt.clean("true_false", "x", None, ["মিথ্যা"])[1] == "false"
    for key in ("maybe", None, ["true", "false"]):
        with pytest.raises(ValueError):
            qt.clean("true_false", "x", None, key)


def test_fill_in_the_blank_keys_have_answers_for_every_blank():
    assert qt.clean("fill_blank", "The capital is ___.", None, "Dhaka") == (None, [["Dhaka"]])
    assert qt.clean("fill_blank", "The capital is ___.", None, ["Dhaka", "Dacca"]) == (None, [["Dhaka", "Dacca"]])
    assert qt.clean("fill_blank", "___ over ___", None, ["top", "bottom"]) == (None, [["top"], ["bottom"]])
    assert qt.clean("fill_blank", "___ over ___", None, [["a", "b"], ["c"]]) == (None, [["a", "b"], ["c"]])
    assert qt.clean("fill_blank", "No marker", None, "x") == (None, [["x"]])  # no ___: one blank after the question
    for title, key in [("___ over ___", [["a"]]), ("One ___", []), ("One ___", [[" "]]), ("One ___", [["?"]]),
                       ("One ___", [["a", "a"]])]:
        with pytest.raises(ValueError):
            qt.clean("fill_blank", title, None, key)


def test_numeric_keys():
    assert qt.clean("numeric", "g?", None, 9.8) == (None, {"value": 9.8, "tolerance": 0.0})
    assert qt.clean("numeric", "g?", None, "9.8 ± 0.1") == (None, {"value": 9.8, "tolerance": 0.1})
    assert qt.clean("numeric", "g?", None, {"value": "9,8", "tolerance": "0,05"}) == (None, {"value": 9.8, "tolerance": 0.05})
    for key in ("about ten", {"value": 1, "tolerance": -1}, {"value": 1, "tolerance": "x"}, None, {"tolerance": 1}):
        with pytest.raises(ValueError):
            qt.clean("numeric", "g?", None, key)


def test_matching_keys():
    pairs = [["Bangladesh", "Dhaka"], ["India", "New Delhi"]]
    assert qt.clean("matching", "Match", pairs, None) == (
        {"left": ["Bangladesh", "India"], "right": ["Dhaka", "New Delhi"]}, {"Bangladesh": "Dhaka", "India": "New Delhi"})
    with_extra = {"left": ["Bangladesh", "India"], "right": ["Dhaka", "New Delhi", "Karachi"]}
    assert qt.clean("matching", "Match", with_extra, {"India": "New Delhi", "Bangladesh": "Dhaka"})[1] == {
        "Bangladesh": "Dhaka", "India": "New Delhi"}
    for options, key in [
        (with_extra, {"Bangladesh": "Dhaka"}),  # India has no match
        (with_extra, {"Bangladesh": "Dhaka", "India": "Dhaka"}),  # one match used twice
        (with_extra, {"Bangladesh": "Dhaka", "India": "Lahore"}),  # not one of the answers
        ({"left": ["A"], "right": ["1"]}, {"A": "1"}),  # a single pair
        ({"left": ["A", "B", "C"], "right": ["1", "2"]}, {"A": "1", "B": "2", "C": "1"}),  # fewer answers than items
        ("A-1, B-2", None),
    ]:
        with pytest.raises(ValueError):
            qt.clean("matching", "Match", options, key)


def test_ordering_keys():
    assert qt.clean("ordering", "Order", ["Mercury", "Venus", "Earth"], None) == (["Mercury", "Venus", "Earth"],) * 2
    assert qt.clean("ordering", "Order", ["b", "a"], ["a", "b"]) == (["a", "b"], ["a", "b"])
    for options, key in [(["only"], None), (["a", "b"], ["a", "c"]), (["a", "a"], None), (["a", "b"], "a,b")]:
        with pytest.raises(ValueError):
            qt.clean("ordering", "Order", options, key)


# --- grading

@pytest.mark.parametrize("qtype, key, answer, right", [
    ("true_false", "true", "true", True),
    ("true_false", "true", "false", False),
    ("fill_blank", [["Dhaka", "Dacca"]], ["  dacca. "], True),
    ("fill_blank", [["numerator"], ["denominator"]], ["Numerator", "denominator"], True),
    ("fill_blank", [["numerator"], ["denominator"]], ["denominator", "numerator"], False),
    ("fill_blank", [["numerator"], ["denominator"]], ["numerator"], False),
    ("fill_blank", [["Dhaka"]], [""], False),
    ("numeric", {"value": 9.8, "tolerance": 0.1}, "9,85", True),
    ("numeric", {"value": 9.8, "tolerance": 0.1}, "9.9", True),  # the edge of the margin counts
    ("numeric", {"value": 9.8, "tolerance": 0.1}, "9.95", False),
    ("numeric", {"value": 0.3, "tolerance": 0}, 0.1 + 0.2, True),
    ("numeric", {"value": 12.5, "tolerance": 0}, "১২.৫", True),
    ("numeric", {"value": 1, "tolerance": 0}, "one", False),
    ("matching", {"A": "1", "B": "2"}, {"B": "2", "A": "1"}, True),
    ("matching", {"A": "1", "B": "2"}, {"A": "2", "B": "1"}, False),
    ("matching", {"A": "1", "B": "2"}, {"A": "1"}, False),
    ("ordering", ["a", "b", "c"], ["a", "b", "c"], True),
    ("ordering", ["a", "b", "c"], ["a", "c", "b"], False),
    ("ordering", ["a", "b", "c"], "abc", False),
    ("single_choice", "4", 4, True),
    ("text", None, "anything", None),
])
def test_grading(qtype, key, answer, right):
    assert qt.is_correct(qtype, key, answer) is right


# --- what students see

def test_students_never_get_an_order_that_gives_the_answer_away():
    pair = models.Question(type="ordering", title="Order", options=["a", "b"], correct_answers=["a", "b"])
    assert all(qt.student_options(pair, f"attempt-{i}:q", False) == ["b", "a"] for i in range(30))
    six = models.Question(type="ordering", title="Order", options=list("abcdef"), correct_answers=list("abcdef"))
    seen = {tuple(qt.student_options(six, f"attempt-{i}:q", False)) for i in range(30)}
    assert tuple("abcdef") not in seen and len(seen) > 1
    assert qt.student_options(six, "same", False) == qt.student_options(six, "same", False)  # stable on reload

    match = models.Question(type="matching", title="Match", options={"left": list("ABCDE"), "right": list("12345")})
    shown = qt.student_options(match, "seed", shuffle=False)
    assert shown["left"] == list("ABCDE") and sorted(shown["right"]) == list("12345")
    blanks = models.Question(type="fill_blank", title="___ and ___", options=None)
    assert qt.student_options(blanks, "s", False) == {"blanks": 2}


# --- through the API

def setup(db):
    org = make_org(db, f"Types {uuid.uuid4().hex[:6]}")
    owner = make_user(db, f"owner-{uuid.uuid4().hex[:6]}@types.com", org, models.ROLE_OWNER)
    return org, owner, headers_for(owner, org)


QUESTIONS = {
    "true_false": {"title": "Water boils at 100 °C at sea level.", "correct_answers": "true"},
    "fill_blank": {"title": "The capital of Bangladesh is ___.", "correct_answers": [["Dhaka", "Dacca"]]},
    "numeric": {"title": "What is g, in m/s²?", "correct_answers": {"value": 9.8, "tolerance": 0.1}},
    "matching": {"title": "Match each country to its capital.",
                 "options": {"left": ["Bangladesh", "India", "Nepal"], "right": ["Dhaka", "New Delhi", "Kathmandu", "Karachi"]},
                 "correct_answers": {"Bangladesh": "Dhaka", "India": "New Delhi", "Nepal": "Kathmandu"}},
    "ordering": {"title": "Put them in order from the Sun.", "options": ["Mercury", "Venus", "Earth", "Mars"]},
}
RIGHT = {"true_false": "true", "fill_blank": ["dhaka"], "numeric": "9,75",
         "matching": {"Bangladesh": "Dhaka", "India": "New Delhi", "Nepal": "Kathmandu"},
         "ordering": ["Mercury", "Venus", "Earth", "Mars"]}
WRONG = {"true_false": "false", "fill_blank": ["Chattogram"], "numeric": "10",
         "matching": {"Bangladesh": "Karachi", "India": "New Delhi", "Nepal": "Kathmandu"},
         "ordering": ["Venus", "Mercury", "Earth", "Mars"]}


def sit(client, db, org, exam_id, ids, answers):
    kid = make_user(db, f"kid-{uuid.uuid4().hex[:6]}@types.com", org, models.ROLE_CANDIDATE)
    h = headers_for(kid, org)
    session = client.post(f"/student/exams/{exam_id}/start", headers=h).json()
    attempt_id = session["attempt"]["id"]
    for qtype, answer in answers.items():
        res = client.post(f"/student/attempts/{attempt_id}/save-answer", headers=h,
                          json={"question_id": ids[qtype], "answer_data": answer})
        assert res.status_code == 200, res.text
    client.post(f"/student/attempts/{attempt_id}/submit", headers=h)
    attempt = db.get(models.ExamAttempt, uuid.UUID(attempt_id))
    db.refresh(attempt)
    return session, attempt, h


def test_each_new_type_is_written_sent_without_its_key_and_graded(client, test_db):
    org, owner, h = setup(test_db)
    ids = {}
    for qtype, body in QUESTIONS.items():
        res = client.post("/admin/questions/", headers=h, json={"complexity": "easy", "type": qtype, "max_score": 2, **body})
        assert res.status_code == 201, (qtype, res.text)
        ids[qtype] = res.json()["id"]
    now = datetime.now(timezone.utc)
    exam = client.post("/admin/exams/", headers=h, json={
        "title": "Every type", "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 30,
        "question_ids": list(ids.values()), "require_fullscreen": False}).json()
    assert client.post(f"/admin/exams/{exam['id']}/publish", headers=h).status_code == 200

    session, attempt, hk = sit(client, test_db, org, exam["id"], ids, RIGHT)
    assert (attempt.score, attempt.total_possible_score) == (10, 10)
    shown = {q["type"]: q for q in session["exam"]["questions"]}
    assert all("correct_answers" not in q for q in shown.values())
    assert shown["true_false"]["options"] == ["true", "false"]
    assert shown["fill_blank"]["options"] == {"blanks": 1} and shown["numeric"]["options"] is None
    assert sorted(shown["matching"]["options"]["right"]) == sorted(QUESTIONS["matching"]["options"]["right"])
    order = shown["ordering"]["options"]
    assert order != RIGHT["ordering"] and sorted(order) == sorted(RIGHT["ordering"])

    _, wrong, _ = sit(client, test_db, org, exam["id"], ids, WRONG)
    assert wrong.score == 0

    # While the exam is open the results hold back the key, and the stored order that is the key
    results = client.get(f"/student/attempts/{attempt.id}/results", headers=hk).json()["exam"]
    ordering = next(q for q in results["questions"] if q["type"] == "ordering")
    assert ordering["correct_answers"] is None and ordering["is_correct"] is None and ordering["options"] == order

    stored = test_db.get(models.Exam, uuid.UUID(exam["id"]))
    stored.end_time = now - timedelta(minutes=1)
    test_db.commit()
    results = client.get(f"/student/attempts/{attempt.id}/results", headers=hk).json()["exam"]
    assert [q["is_correct"] for q in results["questions"]] == [True] * 5


def workbook(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["title", "complexity", "type", "options", "correct_answers", "max_score"])
    for row in rows:
        ws.append(list(row))
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return {"file": ("q.xlsx", stream, XLSX)}


def test_the_template_imports_as_it_is(client, test_db):
    org, _, h = setup(test_db)
    template = client.get("/admin/questions-template", headers=h)
    assert template.status_code == 200
    preview = client.post("/admin/preview-questions/", headers=h,
                          files={"file": ("questions_template.xlsx", io.BytesIO(template.content), XLSX)}).json()
    assert {q["type"] for q in preview["questions"]} == set(models.QUESTION_TYPES)
    res = client.post("/admin/upload-questions/", headers=h,
                      files={"file": ("questions_template.xlsx", io.BytesIO(template.content), XLSX)})
    assert res.status_code == 200 and res.json()["rows_imported"] == preview["count"] == 10
    stored = {q.title: q for q in test_db.query(models.Question).filter_by(organization_id=org.id)}
    assert stored["What is g at the Earth's surface, in m/s²?"].correct_answers == {"value": 9.8, "tolerance": 0.1}
    assert stored["Match each country to its capital."].correct_answers["Nepal"] == "Kathmandu"
    assert stored["Water boils at 100 °C at sea level."].correct_answers == "true"
    assert stored["___ and ___ are the two parts of a fraction."].correct_answers == [["numerator"], ["denominator"]]


def test_a_bad_row_is_named_and_nothing_is_imported(client, test_db):
    org, _, h = setup(test_db)
    res = client.post("/admin/upload-questions/", headers=h, files=workbook([
        ("Water is wet", "easy", "true_false", None, "true", 1),
        ("Order these", "easy", "ordering", '["only one"]', None, 1),
    ]))
    assert res.status_code == 400 and res.json()["detail"] == "Row 3: Add at least 2 items to put in order."
    assert test_db.query(models.Question).filter_by(organization_id=org.id).count() == 0
    plain = client.post("/admin/upload-questions/", headers=h, files=workbook([
        ("The capital of Bangladesh is ___.", "easy", "fill_blank", None, "Dhaka", 1),
    ]))
    assert plain.status_code == 200  # plain text in a cell, not JSON, is read as written
