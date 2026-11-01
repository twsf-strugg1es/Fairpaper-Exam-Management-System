"""An exam's results as an Excel workbook, and the data behind the printable result cards (task 4.5).

The cards themselves are drawn by the web app and saved as PDF by the browser, which shapes every script
(Bengali conjuncts, Arabic) correctly without the server bundling fonts.

Times are shown in the organization's timezone. Text from users (names, emails, titles) is always written as
text, so a name such as "=HYPERLINK(...)" can't become a formula when the file is opened.
"""
from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session, joinedload

from . import crud, models

ENDED_BY = {
    models.SUBMIT_STUDENT: "Submitted",
    models.SUBMIT_TIME_UP: "Time ran out",
    models.SUBMIT_VIOLATIONS: "Violation limit reached",
}
TYPE_NAMES = {
    "single_choice": "Single answer", "multi_choice": "Multiple answers", "true_false": "True or false",
    "fill_blank": "Fill in the blank", "numeric": "Number", "matching": "Matching", "ordering": "Ordering",
    "text": "Written", "image_upload": "Image",
}
HEADER_FILL = PatternFill("solid", fgColor="E3F1EA")


def _zone(org: models.Organization | None):
    try:
        return ZoneInfo(org.timezone) if org and org.timezone else timezone.utc
    except ZoneInfoNotFoundError:
        return timezone.utc


def _rows(db: Session, exam: models.Exam) -> list[dict]:
    """Every attempt with its rank and final score (submitted ones), integrity summary and per-question marks.
    Ranked attempts first, in rank order; unfinished ones after, by name."""
    attempts = (
        db.query(models.ExamAttempt)
        .options(joinedload(models.ExamAttempt.student), joinedload(models.ExamAttempt.integrity_events))
        .filter(models.ExamAttempt.exam_id == exam.id)
        .all()
    )
    ranked = {row["attempt"].id: row for row in crud.merit_list(db, exam)}
    parts = crud.breakdowns(db, exam, attempts)
    total_marks = float(crud.exam_total_marks(exam))
    rows = []
    for attempt in attempts:
        merit = ranked.get(attempt.id)
        rows.append({
            "attempt": attempt,
            "student": attempt.student,
            "rank": merit["rank"] if merit else None,
            "tied": merit["tied"] if merit else False,
            "score": merit["score"] if merit else None,
            "total": float(attempt.total_possible_score) if attempt.total_possible_score is not None else total_marks,
            "seconds": merit["seconds"] if merit else None,
            "integrity": crud.integrity_summary(attempt),
            "questions": parts.get(attempt.id, []),
        })
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, _sort_name(r["student"])))
    return rows


def _sort_name(student: models.User | None) -> str:
    return ((student.full_name or student.email or "") if student else "").lower()


def _slots(exam: models.Exam, marks: dict) -> list[tuple[str, int]]:
    """The column for each position on a paper: fixed questions first, then each pool rule's draws, in the
    order papers store them. ("Q4", 1, "random") reads "the 4th question, worth 1, drawn per student"."""
    slots = [(marks[q.id], False) for q in exam.questions or []]
    for rule in exam.pool_rules:
        slots.extend((rule.marks, True) for _ in range(rule.count))
    return [(f"Q{i} ({worth}{', random' if drawn else ''})", worth) for i, (worth, drawn) in enumerate(slots, start=1)]


def _text(cell, value):
    """A cell that is text whatever it starts with (no formulas from user input), minus characters Excel rejects."""
    cell.value = ILLEGAL_CHARACTERS_RE.sub("", str(value)) if value is not None else None
    if value is not None:
        cell.data_type = "s"
    return cell


def _header(ws, headers, widths):
    for col, (label, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=col, value=label)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"


def results_workbook(db: Session, exam: models.Exam) -> bytes:
    org = db.get(models.Organization, exam.organization_id)
    zone = _zone(org)

    def local(moment):  # Excel has no time zones: write the organization's wall-clock time
        return crud.as_utc(moment).astimezone(zone).replace(tzinfo=None) if moment else None
    rows = _rows(db, exam)
    marks = crud.exam_marks(exam)
    questions = list(exam.questions or [])

    wb = Workbook()

    # 1. Results: one row per student
    ws = wb.active
    ws.title = "Results"
    _header(
        ws,
        ["Rank", "Name", "Email", "Score", "Out of", "Percent", "Time taken", "Started", "Submitted", "Ended by",
         "Violations", "Flags", "Time away", "Risk"],
        [7, 28, 32, 9, 9, 9, 11, 17, 17, 22, 11, 8, 11, 9],
    )
    for r, row in enumerate(rows, start=2):
        attempt, student, integrity = row["attempt"], row["student"], row["integrity"]
        ws.cell(row=r, column=1, value=row["rank"])
        _text(ws.cell(row=r, column=2), student.full_name if student and student.full_name else "")
        _text(ws.cell(row=r, column=3), student.email if student else "")
        if row["score"] is not None:
            ws.cell(row=r, column=4, value=row["score"])
            ws.cell(row=r, column=5, value=row["total"])
            if row["total"]:
                ws.cell(row=r, column=6, value=row["score"] / row["total"]).number_format = "0.0%"
        if row["seconds"] is not None:
            ws.cell(row=r, column=7, value=row["seconds"] / 86400).number_format = "[h]:mm:ss"
        ws.cell(row=r, column=8, value=local(attempt.start_time)).number_format = "yyyy-mm-dd hh:mm"
        if attempt.end_time:
            ws.cell(row=r, column=9, value=local(attempt.end_time)).number_format = "yyyy-mm-dd hh:mm"
        _text(ws.cell(row=r, column=10), ENDED_BY.get(attempt.submit_reason, "In progress" if not attempt.end_time else attempt.submit_reason))
        ws.cell(row=r, column=11, value=integrity["violations"])
        ws.cell(row=r, column=12, value=integrity["flags"])
        ws.cell(row=r, column=13, value=integrity["seconds_away"] / 86400).number_format = "[h]:mm:ss"
        _text(ws.cell(row=r, column=14), integrity["risk"].capitalize())

    # 2. Marks by question: what each student earned on each question (with pools: on each slot of their paper)
    wq = wb.create_sheet("Marks by question")
    slots = _slots(exam, marks)
    _header(wq, ["Name", "Email"] + [label for label, _ in slots], [28, 32] + [12] * len(slots))
    for r, row in enumerate(rows, start=2):
        student = row["student"]
        _text(wq.cell(row=r, column=1), student.full_name if student and student.full_name else "")
        _text(wq.cell(row=r, column=2), student.email if student else "")
        for c, part in enumerate(row["questions"], start=3):
            if part["earned"] is None:
                _text(wq.cell(row=r, column=c), "Not graded")
            else:
                wq.cell(row=r, column=c, value=part["earned"])

    # 3. The questions, so the Q numbers mean something
    wl = wb.create_sheet("Questions")
    _header(wl, ["Q", "Question", "Type", "Marks"], [6, 80, 18, 8])
    for i, question in enumerate(questions, start=1):
        wl.cell(row=i + 1, column=1, value=f"Q{i}")
        _text(wl.cell(row=i + 1, column=2), question.title).alignment = Alignment(wrap_text=True, vertical="top")
        _text(wl.cell(row=i + 1, column=3), TYPE_NAMES.get(question.type, question.type))
        wl.cell(row=i + 1, column=4, value=marks[question.id])
    # Pool rules: which slots each one fills, and what it draws
    first, row = len(questions) + 1, len(questions) + 2
    for rule in exam.pool_rules:
        last = first + rule.count - 1
        _text(wl.cell(row=row, column=1), f"Q{first}" if first == last else f"Q{first}-Q{last}")
        _text(wl.cell(row=row, column=2), crud.describe_rule(rule))
        _text(wl.cell(row=row, column=3), "Drawn per student")
        wl.cell(row=row, column=4, value=rule.marks)
        first, row = last + 1, row + 1

    # 4. The exam itself
    we = wb.create_sheet("Exam")
    we.column_dimensions["A"].width = 18
    we.column_dimensions["B"].width = 48
    details = [
        ("Exam", exam.title),
        ("Organization", org.name if org else ""),
        ("Opens", local(exam.start_time)),
        ("Closes", local(exam.end_time)),
        ("Duration (min)", exam.duration_minutes),
        ("Total marks", crud.exam_total_marks(exam)),
        ("Students", len(rows)),
        ("Submitted", sum(1 for row in rows if row["attempt"].end_time)),
        ("Exported", local(datetime.now(timezone.utc))),
        ("Times shown in", org.timezone if org else "UTC"),
    ]
    for r, (label, value) in enumerate(details, start=1):
        we.cell(row=r, column=1, value=label).font = Font(bold=True)
        cell = we.cell(row=r, column=2)
        if isinstance(value, str):
            _text(cell, value)
        else:
            cell.value = value
            if isinstance(value, datetime):
                cell.number_format = "yyyy-mm-dd hh:mm"
        cell.alignment = Alignment(horizontal="left")

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def result_cards(db: Session, exam: models.Exam, attempt_id=None) -> dict:
    """One card per submitted attempt (or just `attempt_id`'s). Cards go to students, so they carry the score
    and the marks per question but no integrity details, and a rank only when the exam shows ranks."""
    org = db.get(models.Organization, exam.organization_id)
    rows = [row for row in _rows(db, exam) if row["attempt"].end_time is not None]
    submitted = len(rows)
    if attempt_id is not None:
        rows = [row for row in rows if row["attempt"].id == attempt_id]
    return {
        "exam": {
            "id": str(exam.id),
            "title": exam.title,
            "organization": org.name if org else "",
            "start_time": crud.as_utc(exam.start_time).isoformat(),
            "end_time": crud.as_utc(exam.end_time).isoformat(),
            "total_marks": crud.exam_total_marks(exam),
            "show_rank": exam.show_rank,
            "results_visible": crud.results_visible(exam),
        },
        "submitted": submitted,
        "cards": [
            {
                "attempt_id": str(row["attempt"].id),
                "student": {
                    "full_name": row["student"].full_name if row["student"] else None,
                    "email": row["student"].email if row["student"] else None,
                },
                "rank": row["rank"] if exam.show_rank else None,
                "tied": row["tied"] if exam.show_rank else False,
                "score": row["score"],
                "total": row["total"],
                "percentage": round(100 * row["score"] / row["total"], 1) if row["total"] else 0,
                "time_taken_seconds": row["seconds"],
                "submitted_at": crud.as_utc(row["attempt"].end_time).isoformat(),
                "questions": [
                    {"n": n, "type": part["question"].type, "worth": part["worth"], "earned": part["earned"]}
                    for n, part in enumerate(row["questions"], start=1)
                ],
            }
            for row in rows
        ],
    }
