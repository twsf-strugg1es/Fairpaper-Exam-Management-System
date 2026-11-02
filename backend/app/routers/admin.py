import json
from uuid import UUID
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import String, cast
from sqlalchemy.orm import Session, joinedload
import openpyxl

import logging

from ..database import get_db
from .. import analytics, schemas, crud, models, results_export, question_types
from ..logging_config import internal_error_detail
from ..permissions import require_manager, require_staff

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = logging.getLogger(__name__)


# Lookups below only find records in the caller's organization, so IDs from
# another organization behave exactly like IDs that don't exist.

def _get_org_question(db: Session, question_id: UUID, membership: models.Membership) -> models.Question:
    question = (
        db.query(models.Question)
        .filter(
            models.Question.id == question_id,
            models.Question.organization_id == membership.organization_id,
        )
        .first()
    )
    if not question or question.archived_at is not None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


def _get_org_exam(db: Session, exam_id: UUID, membership: models.Membership) -> models.Exam:
    exam = crud.get_exam_by_id(db, exam_id)
    if not exam or exam.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


def _get_org_attempt(db: Session, attempt_id: UUID, membership: models.Membership) -> models.ExamAttempt | None:
    return (
        db.query(models.ExamAttempt)
        .join(models.Exam, models.ExamAttempt.exam_id == models.Exam.id)
        .filter(
            models.ExamAttempt.id == attempt_id,
            models.Exam.organization_id == membership.organization_id,
        )
        .first()
    )


def _get_org_answer(db: Session, answer_id: UUID, membership: models.Membership) -> models.Answer | None:
    return (
        db.query(models.Answer)
        .join(models.ExamAttempt, models.Answer.attempt_id == models.ExamAttempt.id)
        .join(models.Exam, models.ExamAttempt.exam_id == models.Exam.id)
        .filter(
            models.Answer.id == answer_id,
            models.Exam.organization_id == membership.organization_id,
        )
        .first()
    )


def _groups_payload(exam: models.Exam) -> list[dict]:
    return [{"id": str(g.id), "name": g.name} for g in exam.groups]


@router.get("/questions/", response_model=list[schemas.Question])
def list_questions(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
    search: str = Query(None, description="Search in title and complexity"),
    question_type: str = Query(None, description="Filter by question type"),
    complexity: str = Query(None, description="Filter by complexity"),
    tag: str = Query(None, description="Filter by tag"),
):
    """List all questions for exam building with search and filter capabilities."""
    query = db.query(models.Question).filter(
        models.Question.organization_id == membership.organization_id,
        models.Question.archived_at.is_(None),
    )

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            models.Question.title.ilike(search_pattern) | 
            models.Question.complexity.ilike(search_pattern)
        )

    if question_type:
        query = query.filter(models.Question.type == question_type)

    if complexity:
        # Normalize complexity to lowercase
        complexity = complexity.lower()
        query = query.filter(models.Question.complexity == complexity)

    if tag:
        # tags is a JSON array such as ["math", "waves"]: match the quoted tag inside the stored
        # JSON text, where non-ASCII is escaped (\u09ac...) as json.dumps does. autoescape keeps
        # PostgreSQL's LIKE from eating those backslashes and stops _ and % acting as wildcards
        wanted = crud.normalize_tags([tag])
        if wanted:
            query = query.filter(cast(models.Question.tags, String).contains(json.dumps(wanted[0]), autoescape=True))

    return query.all()


def _question_payload(db: Session, question: models.Question) -> dict:
    return {
        **schemas.Question.model_validate(question).model_dump(mode="json"),
        # Why the question can't be edited any more; null while it can
        "edit_blocked": crud.question_edit_blocker(db, question),
    }


@router.get("/questions/{question_id}")
def get_question(
    question_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Get a single question by ID, with whether it can still be edited."""
    return _question_payload(db, _get_org_question(db, question_id, membership))


@router.post("/questions/", status_code=status.HTTP_201_CREATED)
def create_question(
    data: schemas.QuestionEdit,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Write one question in the editor."""
    question = crud.save_question(db, models.Question(organization_id=membership.organization_id), data)
    return _question_payload(db, question)


@router.put("/questions/{question_id}")
def update_question(
    question_id: UUID,
    data: schemas.QuestionEdit,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Change a question nobody has met in an exam yet; otherwise 409 (duplicate it instead)."""
    question = _get_org_question(db, question_id, membership)
    reason = crud.question_edit_blocker(db, question)
    if reason:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)
    return _question_payload(db, crud.save_question(db, question, data))


@router.post("/questions/{question_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_question(
    question_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Copy a question into a new, editable one. Exams keep using the original."""
    original = _get_org_question(db, question_id, membership)
    copy = models.Question(
        organization_id=membership.organization_id,
        title=original.title,
        description=original.description,
        complexity=original.complexity,
        type=original.type,
        options=list(original.options) if isinstance(original.options, list) else original.options,
        correct_answers=list(original.correct_answers) if isinstance(original.correct_answers, list) else original.correct_answers,
        max_score=original.max_score,
        tags=list(original.tags or []),
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _question_payload(db, copy)


@router.delete("/questions/{question_id}")
def delete_question(
    question_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Delete a question, or archive it if exams or student answers use it (results are never erased)."""
    question = _get_org_question(db, question_id, membership)
    outcome = crud.remove_question(db, question)
    message = "Question deleted" if outcome == "deleted" else "Question archived: it's used in an exam, so past results keep it"
    return {"status": outcome, "message": message}


@router.post("/questions/delete-bulk")
def delete_bulk_questions(
    data: schemas.BulkQuestionIds,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Delete unused questions and archive used ones. Questions from other organizations are skipped."""
    counts = {"deleted": 0, "archived": 0, "failed": 0}
    for question_id in data.question_ids:
        question = (
            db.query(models.Question)
            .filter(
                models.Question.id == question_id,
                models.Question.organization_id == membership.organization_id,
                models.Question.archived_at.is_(None),
            )
            .first()
        )
        if not question:
            counts["failed"] += 1
            continue
        counts[crud.remove_question(db, question)] += 1
    return {"status": "success", **counts}


QUESTION_COLUMNS = ("title", "complexity", "type", "options", "correct_answers", "max_score")


def _sheet_value(value):
    """An options or correct_answers cell: JSON when it is JSON, otherwise the text as written ("Dhaka", "9.8 ± 0.1")."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text in ("", "null"):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _read_question_sheet(file: UploadFile) -> list[schemas.QuestionBase]:
    """The questions in an uploaded workbook, each checked by the rules of its type the way the editor checks it.
    Rows without a title, difficulty or type are skipped. Any other problem is a 400 naming the row, before
    anything is imported."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400, detail="Only Excel files (.xlsx or .xls) are accepted. Please upload a valid Excel file."
        )
    try:
        ws = openpyxl.load_workbook(file.file, data_only=True).active
    except Exception:
        raise HTTPException(
            status_code=400, detail="This file couldn't be opened as an Excel workbook. Save it as .xlsx and try again."
        )
    try:
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    except StopIteration:
        raise HTTPException(status_code=400, detail="Excel file is empty")
    header = [str(h).strip().lower() if h is not None else "" for h in header_row]
    missing = [c for c in QUESTION_COLUMNS if c not in header]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(missing)}")
    column = {name: header.index(name) for name in (*QUESTION_COLUMNS, "tags", "description", "time_limit_seconds") if name in header}

    questions = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        def cell(name):
            at = column.get(name)
            return row[at] if at is not None and at < len(row) else None

        title, complexity, qtype = cell("title"), cell("complexity"), cell("type")
        if not title or not complexity or not qtype:
            continue
        complexity, qtype = str(complexity).strip().lower(), str(qtype).strip().lower()
        if complexity not in models.COMPLEXITIES:
            raise HTTPException(status_code=400, detail=f"Row {i}: complexity must be one of: {', '.join(models.COMPLEXITIES)}.")
        if qtype not in models.QUESTION_TYPES:
            raise HTTPException(status_code=400, detail=f"Row {i}: type must be one of: {', '.join(models.QUESTION_TYPES)}.")
        try:
            options, correct = question_types.clean(
                qtype, str(title), _sheet_value(cell("options")), _sheet_value(cell("correct_answers"))
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Row {i}: {e}")
        raw_score = cell("max_score")
        try:
            max_score = int(raw_score) if raw_score not in (None, "") else 1
        except (TypeError, ValueError):
            max_score = 0
        if not 1 <= max_score <= 100:
            raise HTTPException(status_code=400, detail=f"Row {i}: max_score must be a whole number from 1 to 100.")
        raw_limit, (low, high) = cell("time_limit_seconds"), models.QUESTION_SECONDS
        try:
            limit = int(raw_limit) if raw_limit not in (None, "") else None
        except (TypeError, ValueError):
            limit = 0
        if limit is not None and not low <= limit <= high:
            raise HTTPException(status_code=400, detail=f"Row {i}: time_limit_seconds must be a whole number from {low} to {high}, or empty.")
        tags, description = cell("tags"), cell("description")
        questions.append(schemas.QuestionBase(
            title=str(title).strip(),
            description=(str(description).strip() or None) if description else None,
            complexity=complexity,
            type=qtype,
            options=options,
            correct_answers=correct,
            max_score=max_score,
            tags=crud.normalize_tags(tags if isinstance(tags, (str, list)) else None) or None,
            default_time_limit_seconds=limit,
        ))
    return questions


@router.post("/upload-questions/")
async def upload_questions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Import every question in the workbook, or none of them when a row has a problem."""
    questions = _read_question_sheet(file)
    for question in questions:
        crud.create_question(db, question, membership.organization_id)
    return JSONResponse({"status": "success", "rows_imported": len(questions)})


@router.post("/preview-questions/")
async def preview_questions(
    file: UploadFile = File(...),
    _: models.Membership = Depends(require_staff),
):
    """The questions an import would create, checked the same way, without creating them."""
    questions = [q.model_dump() for q in _read_question_sheet(file)]
    return JSONResponse({"questions": questions, "count": len(questions)})


@router.get("/questions-template")
def download_questions_template(_: models.Membership = Depends(require_staff)):
    """Return an Excel template with headers and sample rows."""
    from openpyxl import Workbook
    from io import BytesIO

    wb = Workbook()
    ws = wb.active
    ws.title = "questions"
    headers = [
        "title",
        "complexity",
        "type",
        "options",
        "correct_answers",
        "max_score",
        "tags",
    ]
    ws.append(headers)
    # One sample row per type, written the way the importer reads them
    for row in (
        ["What is 2+2?", "easy", "single_choice", '["1", "2", "3", "4"]', '"4"', 1, "math,arithmetic"],
        ["Select the prime numbers", "medium", "multi_choice", '["2", "4", "5", "6"]', '["2", "5"]', 2, "math"],
        ["Water boils at 100 °C at sea level.", "easy", "true_false", "", "true", 1, "science"],
        ["The capital of Bangladesh is ___.", "easy", "fill_blank", "", '["Dhaka", "Dacca"]', 1, "geography"],
        ["___ and ___ are the two parts of a fraction.", "medium", "fill_blank", "",
         '[["numerator"], ["denominator"]]', 2, "math"],
        ["What is g at the Earth's surface, in m/s²?", "medium", "numeric", "", "9.8 ± 0.1", 2, "physics"],
        ["Match each country to its capital.", "medium", "matching",
         '[["Bangladesh", "Dhaka"], ["India", "New Delhi"], ["Nepal", "Kathmandu"]]', "", 3, "geography"],
        ["Put the planets in order from the Sun.", "hard", "ordering", '["Mercury", "Venus", "Earth", "Mars"]', "", 2,
         "science"],
        ["Briefly explain polymorphism", "hard", "text", "", "", 5, "programming,oop"],
        ["Upload a diagram of the water cycle", "medium", "image_upload", "", "", 10, "science,biology"],
    ):
        ws.append(row)

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=questions_template.xlsx"
        },
    )


@router.post("/exams/")
def create_exam(
    exam: schemas.ExamCreate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Create a new exam with associated questions (same payload as GET /admin/exams/{id})."""
    _check_exam_references(db, exam, membership)
    return _exam_payload(db, crud.create_exam(db, exam, membership.organization_id))


def _check_exam_references(db: Session, exam: schemas.ExamCreate, membership: models.Membership) -> None:
    """Every question and group must belong to this organization (archived questions don't count)."""
    for question_id in exam.question_ids:
        _get_org_question(db, question_id, membership)
    org_group_ids = {
        g.id for g in db.query(models.Group).filter(models.Group.organization_id == membership.organization_id)
    }
    if set(exam.group_ids) - org_group_ids:
        raise HTTPException(status_code=404, detail="Group not found")
    shortfall = crud.pool_shortfall(db, membership.organization_id, exam.question_ids, exam.pool_rules)
    if shortfall:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=shortfall)


def _exam_payload(db: Session, exam: models.Exam) -> dict:
    marks = crud.exam_marks(exam)
    # Sections are referred to by their place in the list, the way the exam form sends them
    index = {section.id: i for i, section in enumerate(exam.sections)}
    section_of = crud.exam_question_sections(db, exam)
    limits = dict(
        db.query(models.exam_questions.c.question_id, models.exam_questions.c.time_limit_seconds)
        .filter(models.exam_questions.c.exam_id == exam.id, models.exam_questions.c.time_limit_seconds.isnot(None))
        .all()
    )
    publisher_email = None
    if exam.published_by:
        publisher = db.query(models.User).filter(models.User.id == exam.published_by).first()
        publisher_email = publisher.email if publisher else "Unknown"
    return {
        "id": str(exam.id),
        "title": exam.title,
        "start_time": crud.iso(exam.start_time),
        "end_time": crud.iso(exam.end_time),
        "duration_minutes": exam.duration_minutes,
        "is_published": exam.is_published,
        "published_by": publisher_email,
        "groups": _groups_payload(exam),
        **crud.integrity_settings(exam),
        # Why the exam can't be edited any more; null while it can
        "edit_blocked": crud.exam_edit_blocker(db, exam),
        "questions": [
            {
                "id": str(q.id),
                "title": q.title,
                "complexity": q.complexity,
                "type": q.type,
                "options": q.options,
                "correct_answers": q.correct_answers,
                "max_score": marks[q.id],  # in this exam
                "bank_max_score": q.max_score,
                "tags": q.tags,
                "section": index.get(section_of.get(q.id)),
                "time_limit_seconds": limits.get(q.id, q.default_time_limit_seconds),  # in this exam
                "bank_time_limit_seconds": q.default_time_limit_seconds,
            }
            for q in (exam.questions or [])
        ],
        "pool_rules": [
            {"id": str(r.id), "count": r.count, "complexity": r.complexity, "tag": r.tag, "marks": r.marks,
             "section": index.get(r.section_id)}
            for r in exam.pool_rules
        ],
        "sections": [
            {"id": str(s.id), "title": s.title, "instructions": s.instructions, "time_limit_minutes": s.time_limit_minutes}
            for s in exam.sections
        ],
        "timed_sections": crud.timed_sections(exam),
        "timing_mode": exam.timing_mode,
        "question_count": crud.exam_question_count(exam),
        "total_marks": crud.exam_total_marks(exam),
        "results_release": exam.results_release,
        "results_released_at": crud.iso(exam.results_released_at),
        "results_visible": crud.results_visible(exam),
        "show_rank": exam.show_rank,
    }


@router.get("/exams/{exam_id}")
def get_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """One exam with its questions and groups, e.g. for the edit form."""
    exam = _get_org_exam(db, exam_id, membership)
    if exam.archived_at is not None:
        raise HTTPException(status_code=404, detail="Exam not found")
    return _exam_payload(db, exam)


@router.put("/exams/{exam_id}")
def update_exam(
    exam_id: UUID,
    data: schemas.ExamCreate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Change an exam before anyone has started it: while it's a draft or hasn't opened yet."""
    exam = _get_org_exam(db, exam_id, membership)
    if exam.archived_at is not None:
        raise HTTPException(status_code=404, detail="Exam not found")
    reason = crud.exam_edit_blocker(db, exam)
    if reason:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)
    _check_exam_references(db, data, membership)
    return _exam_payload(db, crud.update_exam(db, exam, data))


@router.get("/exams/")
def list_exams(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """List all exams with publisher information."""
    return [_exam_payload(db, exam) for exam in crud.get_exams(db, membership.organization_id)]


@router.post("/exams/{exam_id}/results/release")
def release_results(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Let students see their scores now, whatever the exam's release setting."""
    exam = _get_org_exam(db, exam_id, membership)
    exam.results_released_at = datetime.now(timezone.utc)
    db.commit()
    return _exam_payload(db, exam)


@router.delete("/exams/{exam_id}/results/release")
def withdraw_results(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Hide released results again (e.g. released by mistake). Only manual exams hide them."""
    exam = _get_org_exam(db, exam_id, membership)
    exam.results_released_at = None
    db.commit()
    return _exam_payload(db, exam)


@router.post("/exams/{exam_id}/publish")
def publish_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Publish an exam to make it available to students."""
    exam = _get_org_exam(db, exam_id, membership)
    # The bank can change after the exam was saved (questions archived): check the pools still fill
    shortfall = crud.pool_shortfall(db, exam.organization_id, [q.id for q in exam.questions], exam.pool_rules)
    if shortfall:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=shortfall)

    exam.is_published = True
    exam.published_by = membership.user_id  # Track which admin published
    db.commit()
    db.refresh(exam)

    return _exam_payload(db, exam)


@router.post("/exams/{exam_id}/unpublish")
def unpublish_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Unpublish an exam to make it unavailable to students."""
    exam = _get_org_exam(db, exam_id, membership)

    exam.is_published = False
    db.commit()
    db.refresh(exam)

    return _exam_payload(db, exam)


@router.delete("/exams/{exam_id}")
def delete_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Delete an exam nobody has started; archive one with attempts so results and records are kept."""
    exam = _get_org_exam(db, exam_id, membership)
    outcome = crud.remove_exam(db, exam)
    message = "Exam deleted" if outcome == "deleted" else "Exam archived: students took it, so their results are kept"
    return {"status": outcome, "message": message}


@router.get("/exams/{exam_id}/merit")
def get_merit_list(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """The exam's merit list (PRD AC17). Provisional until the exam closes."""
    exam = _get_org_exam(db, exam_id, membership)
    rows = crud.merit_list(db, exam)
    return {
        "closed": datetime.now(timezone.utc) > crud.as_utc(exam.end_time),
        "rows": [
            {
                "rank": r["rank"],
                "tied": r["tied"],
                "attempt_id": str(r["attempt"].id),
                "student": {
                    "id": str(r["attempt"].student_id),
                    "email": r["attempt"].student.email if r["attempt"].student else None,
                    "full_name": r["attempt"].student.full_name if r["attempt"].student else None,
                },
                "score": r["score"],
                "total_possible_score": r["attempt"].total_possible_score,
                "percentage": round(100 * r["score"] / r["attempt"].total_possible_score, 2) if r["attempt"].total_possible_score else 0,
                "time_taken_seconds": r["seconds"],
                "submit_reason": r["attempt"].submit_reason,
            }
            for r in rows
        ],
    }


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/exams/{exam_id}/export.xlsx")
def export_results(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """The exam's results as an Excel workbook (task 4.5): results, marks by question, the questions, the exam."""
    exam = _get_org_exam(db, exam_id, membership)
    data = results_export.results_workbook(db, exam)
    name = quote(f"{exam.title} results.xlsx", safe="")
    return Response(
        content=data,
        media_type=XLSX,
        headers={"Content-Disposition": f"attachment; filename=\"results.xlsx\"; filename*=UTF-8''{name}"},
    )


@router.get("/exams/{exam_id}/result-cards")
def get_result_cards(
    exam_id: UUID,
    attempt: UUID | None = Query(default=None, description="Only this attempt's card"),
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Data for the printable result cards: one per submitted attempt."""
    exam = _get_org_exam(db, exam_id, membership)
    return results_export.result_cards(db, exam, attempt)


@router.get("/exams/{exam_id}/attempts")
def get_exam_attempts(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Get all attempts for a specific exam."""
    # Verify exam exists
    exam = _get_org_exam(db, exam_id, membership)

    # Get all attempts for this exam
    attempts = db.query(models.ExamAttempt).filter(
        models.ExamAttempt.exam_id == exam_id
    ).all()

    # Build response with student info and calculated scores
    result = []
    for attempt in attempts:
        student = db.query(models.User).filter(
            models.User.id == attempt.student_id
        ).first()

        # Get all answers for this attempt (needed for evaluation checking)
        answers = db.query(models.Answer).filter(
            models.Answer.attempt_id == attempt.id
        ).all()

        # Calculate final score with manual evaluations included
        manual_score_total = 0.0
        if attempt.end_time is not None:  # Only for submitted attempts
            for answer in answers:
                eval_record = crud.get_evaluation_by_answer(db, answer.id)
                if eval_record and eval_record.score_awarded is not None:
                    question = crud.get_question_by_id(db, answer.question_id)
                    if question and question.type in models.MANUAL_TYPES:
                        manual_score_total += float(eval_record.score_awarded)

        # Final score: auto-graded + manual scores (capped at total)
        final_score = min(attempt.score + manual_score_total, attempt.total_possible_score or 0) if attempt.score is not None else manual_score_total

        # Get evaluator info (admin who evaluated the exam)
        evaluator_email = None
        if answers:
            # Get the most recent evaluation to find who evaluated this attempt
            latest_eval = None
            for answer in answers:
                eval_record = crud.get_evaluation_by_answer(db, answer.id)
                if eval_record and (latest_eval is None or eval_record.updated_at > latest_eval.updated_at):
                    latest_eval = eval_record

            if latest_eval:
                evaluator = db.query(models.User).filter(models.User.id == latest_eval.evaluated_by).first()
                evaluator_email = evaluator.email if evaluator else "Unknown"

        attempt_data = {
            "id": str(attempt.id),
            "exam_id": str(attempt.exam_id),
            "student_id": str(attempt.student_id),
            "start_time": crud.iso(attempt.start_time),
            "end_time": crud.iso(attempt.end_time),
            "score": final_score,
            "total_possible_score": attempt.total_possible_score,
            "student": {
                "email": student.email if student else "Unknown",
                "full_name": student.full_name if (student and student.full_name) else (student.email if student else "Unknown"),
                "id": str(student.id) if student else None,
            },
            "is_submitted": attempt.end_time is not None,
            "submit_reason": attempt.submit_reason,
            "extra_minutes": attempt.extra_minutes,
            "deadline": crud.iso(crud.get_attempt_deadline(attempt, exam)) if attempt.end_time is None else None,
            "integrity": crud.integrity_summary(attempt),
            "evaluated_by": evaluator_email,
            "is_evaluated": evaluator_email is not None,
        }
        if attempt.end_time:
            attempt_data["submitted_at"] = crud.iso(attempt.end_time)
        result.append(attempt_data)

    return result


@router.get("/attempts/{attempt_id}/integrity")
def get_attempt_integrity(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Everything the exam page recorded during an attempt, for an examiner to review."""
    attempt = _get_org_attempt(db, attempt_id, membership)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    started = crud.as_utc(attempt.start_time)
    return {
        "attempt": {
            "id": str(attempt.id),
            "start_time": crud.iso(attempt.start_time),
            "end_time": crud.iso(attempt.end_time),
            "submit_reason": attempt.submit_reason,
            "score": attempt.score,
            "total_possible_score": attempt.total_possible_score,
        },
        "student": {
            "id": str(attempt.student.id),
            "email": attempt.student.email,
            "full_name": attempt.student.full_name,
        },
        "exam": {"id": str(attempt.exam.id), "title": attempt.exam.title, **crud.integrity_settings(attempt.exam)},
        "summary": crud.integrity_summary(attempt),
        "events": [
            {
                "type": event.type,
                "recorded_at": crud.iso(event.recorded_at),
                # Seconds into the attempt, by the server's clock
                "seconds_into_attempt": max(0, round((crud.as_utc(event.recorded_at) - started).total_seconds())),
                "is_violation": event.type in models.VIOLATION_EVENTS,
                "details": event.details,
            }
            for event in attempt.integrity_events
        ],
    }


@router.get("/attempts/{attempt_id}/results")
def get_attempt_results_admin(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Get detailed results for a specific exam attempt (admin view)."""
    # Get the attempt
    attempt = _get_org_attempt(db, attempt_id, membership)

    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    # Get the student
    student = db.query(models.User).filter(
        models.User.id == attempt.student_id
    ).first()

    # Get the exam
    exam = crud.get_exam_by_id(db, attempt.exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Get student's answers
    answers = db.query(models.Answer).filter(
        models.Answer.attempt_id == attempt.id
    ).all()

    # Calculate final score with manual evaluations included
    manual_score_total = 0.0
    for answer in answers:
        eval_record = crud.get_evaluation_by_answer(db, answer.id)
        if eval_record and eval_record.score_awarded is not None:
            question = crud.get_question_by_id(db, answer.question_id)
            if question and question.type in models.MANUAL_TYPES:
                manual_score_total += float(eval_record.score_awarded)

    # Final score: auto-graded + manual scores (capped at total)
    final_score = min(attempt.score + manual_score_total, attempt.total_possible_score or 0) if attempt.score is not None else manual_score_total

    attempt_payload = schemas.ExamAttempt.model_validate(attempt).model_dump()
    attempt_payload["answers"] = [
        schemas.Answer.model_validate(a).model_dump() for a in answers
    ]
    attempt_payload["student_email"] = student.email if student else "Unknown"
    attempt_payload["score"] = final_score  # Override with calculated score

    # Get publisher email if published
    publisher_email = None
    if exam.published_by:
        publisher = db.query(models.User).filter(models.User.id == exam.published_by).first()
        publisher_email = publisher.email if publisher else "Unknown"

    # Manually build exam dict to avoid Pydantic validation issues with published_by
    exam_payload = {
        "id": str(exam.id),
        "title": exam.title,
        "start_time": crud.iso(exam.start_time),
        "end_time": crud.iso(exam.end_time),
        "duration_minutes": exam.duration_minutes,
        "is_published": exam.is_published,
        "published_by": publisher_email,
        "groups": _groups_payload(exam),
        "questions": [
            {
                "id": str(q.id),
                "title": q.title,
                "complexity": q.complexity,
                "type": q.type,
                "options": q.options,
                "correct_answers": q.correct_answers,
                "max_score": int(worth),
                "tags": q.tags,
            }
            for q, worth in crud.attempt_questions(db, exam, attempt)
        ],
    }

    return {"attempt": attempt_payload, "exam": exam_payload}


def _grade(db: Session, answer_id: UUID, grade: schemas.GradeIn, membership: models.Membership) -> models.Evaluation:
    answer = _get_org_answer(db, answer_id, membership)
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    try:
        return crud.grade_answer(db, answer, membership.user_id, grade)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/answers/{answer_id}/evaluate", response_model=schemas.Evaluation)
def evaluate_answer(
    answer_id: UUID,
    grade: schemas.GradeIn,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Grade a written or image answer: a mark from 0 to what it's worth, and an optional comment."""
    return _grade(db, answer_id, grade, membership)


@router.get("/exams/{exam_id}/analytics")
def get_exam_analytics(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """How each question worked (difficulty and discrimination), the class per topic, and how the scores spread."""
    return analytics.exam_analytics(db, _get_org_exam(db, exam_id, membership))


@router.get("/exams/{exam_id}/extra-time")
def get_extra_time(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Everyone with extra time on this exam: minutes, whether they've started, and their deadline while writing."""
    return crud.extra_time_list(db, _get_org_exam(db, exam_id, membership))


@router.put("/exams/{exam_id}/extra-time/{student_id}")
def put_extra_time(
    exam_id: UUID,
    student_id: UUID,
    data: schemas.ExtraTimeIn,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Set a student's extra minutes on this exam (0 removes them), before they start or while they write."""
    exam = _get_org_exam(db, exam_id, membership)
    try:
        entry = crud.set_extra_time(db, exam, student_id, data.minutes, membership.user_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    logger.info("Extra time set", extra={"fields": {"exam_id": str(exam.id), "student_id": str(student_id), "minutes": data.minutes}})
    return entry


@router.get("/exams/{exam_id}/grading")
def get_exam_grading(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """The exam's written and image questions with how many submitted answers each has, and how many are graded."""
    return crud.grading_overview(db, _get_org_exam(db, exam_id, membership))


@router.get("/exams/{exam_id}/grading/{question_id}")
def get_question_grading(
    exam_id: UUID,
    question_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Every submitted answer to one written or image question of the exam, with its mark so far."""
    sheet = crud.grading_sheet(db, _get_org_exam(db, exam_id, membership), question_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="No submitted paper has this question to grade.")
    return sheet


@router.get("/answers/{answer_id}/evaluation")
def get_answer_evaluation(
    answer_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Get evaluation for a specific answer."""
    if not _get_org_answer(db, answer_id, membership):
        raise HTTPException(status_code=404, detail="Answer not found")
    evaluation = crud.get_evaluation_by_answer(db, answer_id)
    if not evaluation:
        return None
    return schemas.Evaluation.model_validate(evaluation).model_dump()


@router.get("/students/")
def list_all_students(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """List the organization's candidates with their overall performance in its exams."""
    candidates = (
        db.query(models.Membership)
        .options(joinedload(models.Membership.user), joinedload(models.Membership.groups))
        .filter(
            models.Membership.organization_id == membership.organization_id,
            models.Membership.role == models.ROLE_CANDIDATE,
        )
        .all()
    )
    result = []
    for candidate in candidates:
        student = candidate.user
        # Calculate overall performance percentage
        attempts = (
            db.query(models.ExamAttempt)
            .join(models.Exam, models.ExamAttempt.exam_id == models.Exam.id)
            .filter(
                models.ExamAttempt.student_id == student.id,
                models.ExamAttempt.end_time.isnot(None),  # Only completed exams
                models.Exam.organization_id == membership.organization_id,
            )
            .all()
        )

        overall_percentage = 0
        if attempts:
            total_percentage = 0
            for attempt in attempts:
                # Calculate final score with manual evaluations included
                manual_score_total = 0.0
                answers = db.query(models.Answer).filter(
                    models.Answer.attempt_id == attempt.id
                ).all()

                for answer in answers:
                    eval_record = crud.get_evaluation_by_answer(db, answer.id)
                    if eval_record and eval_record.score_awarded is not None:
                        question = crud.get_question_by_id(db, answer.question_id)
                        if question and question.type in models.MANUAL_TYPES:
                            manual_score_total += float(eval_record.score_awarded)

                # Final score: auto-graded + manual scores (capped at total)
                final_score = min(attempt.score + manual_score_total, attempt.total_possible_score or 0)

                # Calculate percentage for this attempt
                if attempt.total_possible_score:
                    total_percentage += (final_score / attempt.total_possible_score * 100)
                else:
                    total_percentage += 0

            overall_percentage = round(total_percentage / len(attempts))

        student_dict = {
            "id": str(student.id),
            "email": student.email,
            "full_name": student.full_name,
            "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
            "gender": student.gender,
            "groups": [{"id": str(g.id), "name": g.name} for g in candidate.groups],
            "joined_at": crud.iso(candidate.created_at),
            "overall": overall_percentage,
        }
        result.append(student_dict)
    return result


@router.delete("/students/{student_id}")
def remove_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_manager),
):
    """Remove a candidate from the organization. Their account and past results are kept."""
    candidate = (
        db.query(models.Membership)
        .filter(
            models.Membership.user_id == student_id,
            models.Membership.organization_id == membership.organization_id,
            models.Membership.role == models.ROLE_CANDIDATE,
        )
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Student not found")

    db.delete(candidate)
    db.commit()
    return {"status": "success", "message": "Student removed from the organization"}


@router.get("/exams/attempts/{attempt_id}")
def get_attempt_details(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Get detailed information about an exam attempt including all answers."""
    try:
        # Get the attempt
        attempt = _get_org_attempt(db, attempt_id, membership)

        if not attempt:
            raise HTTPException(status_code=404, detail="Attempt not found")

        # Get student and exam info
        student = db.query(models.User).filter(models.User.id == attempt.student_id).first()
        exam = db.query(models.Exam).filter(models.Exam.id == attempt.exam_id).first()

        # Build attempt response
        attempt_data = {
            "id": str(attempt.id),
            "student": {
                "id": str(student.id),
                "email": student.email,
                "full_name": student.full_name,
            } if student else None,
            "exam": {
                "id": str(exam.id),
                "title": exam.title,
            } if exam else None,
            "start_time": crud.iso(attempt.start_time),
            "end_time": crud.iso(attempt.end_time),
        }

        # Get all answers for this attempt
        answers = db.query(models.Answer).filter(
            models.Answer.attempt_id == attempt_id
        ).all()

        answers_data = []
        for answer in answers:
            question = db.query(models.Question).filter(
                models.Question.id == answer.question_id
            ).first()

            # Get evaluation data if exists
            evaluation = db.query(models.Evaluation).filter(
                models.Evaluation.answer_id == answer.id
            ).first()

            # Handle answer_data - it can be dict, list, string, or other types
            answer_text = None
            uploaded_file = None

            if isinstance(answer.answer_data, dict):
                # For dict types, try to extract text or name
                answer_text = answer.answer_data.get("text")
                uploaded_file = answer.answer_data.get("name")
            elif isinstance(answer.answer_data, (str, int, float, bool)):
                # For primitive types, use directly
                answer_text = str(answer.answer_data)
            elif isinstance(answer.answer_data, list):
                # For arrays, join them
                answer_text = ", ".join([str(x) for x in answer.answer_data])

            answer_dict = {
                "id": str(answer.id),
                "question_id": str(answer.question_id),
                "attempt_id": str(answer.attempt_id),
                "question": {
                    "id": str(question.id),
                    "title": question.title,
                    "type": question.type,
                    "correct_answers": question.correct_answers,
                } if question else None,
                "answer_text": answer_text,
                "uploaded_file": uploaded_file,
                "score": evaluation.score_awarded if evaluation else 0,
                "feedback": evaluation.comment if evaluation else "",
                "is_evaluated": evaluation is not None,
            }
            answers_data.append(answer_dict)

        return {
            "attempt": attempt_data,
            "answers": answers_data,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Loading attempt details failed")
        raise HTTPException(status_code=500, detail=internal_error_detail())


@router.post("/exams/attempts/{attempt_id}/evaluate")
def evaluate_exam_attempt(
    attempt_id: UUID,
    body: schemas.AttemptGradesIn,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Grade several answers of one attempt; each mark is checked like a single grade."""
    attempt = _get_org_attempt(db, attempt_id, membership)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    attempt_answer_ids = {a.id for a in db.query(models.Answer).filter(models.Answer.attempt_id == attempt.id)}
    if any(item.answer_id not in attempt_answer_ids for item in body.answers):
        raise HTTPException(status_code=400, detail="Answer does not belong to this attempt")
    for item in body.answers:
        _grade(db, item.answer_id, schemas.GradeIn(score_awarded=item.score, comment=item.feedback), membership)
    return {"status": "success", "message": "Evaluation saved successfully"}


@router.get("/evaluations/attempts/{attempt_id}")
def get_attempt_for_evaluation(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """
    Get attempt details for evaluation page.
    Returns only text and image_upload type questions with their answers.
    """
    try:
        # Get the attempt
        attempt = _get_org_attempt(db, attempt_id, membership)

        if not attempt:
            raise HTTPException(status_code=404, detail="Attempt not found")

        # Get student info
        student = db.query(models.User).filter(
            models.User.id == attempt.student_id
        ).first()

        # Get exam info
        exam = db.query(models.Exam).filter(
            models.Exam.id == attempt.exam_id
        ).first()

        # Build response
        response = {
            "attempt_id": str(attempt.id),
            "student": {
                "id": str(student.id) if student else None,
                "email": student.email if student else None,
                "full_name": student.full_name if student else None,
            },
            "exam": {
                "id": str(exam.id) if exam else None,
                "title": exam.title if exam else None,
                "total_marks": crud.exam_total_marks(exam) if exam else 0,
            },
            "submitted_at": crud.iso(attempt.end_time),
            "answers": []
        }

        # Get all answers for this attempt
        answers = db.query(models.Answer).filter(
            models.Answer.attempt_id == attempt_id
        ).all()

        marks = {q.id: int(worth) for q, worth in crud.attempt_questions(db, exam, attempt)} if exam else {}

        # Process each answer
        for answer in answers:
            question = db.query(models.Question).filter(
                models.Question.id == answer.question_id
            ).first()

            # Only include text and image_upload questions
            if not question or question.type not in models.MANUAL_TYPES:
                continue

            # Get evaluation if exists
            evaluation = db.query(models.Evaluation).filter(
                models.Evaluation.answer_id == answer.id
            ).first()

            # Parse answer data
            answer_text = None
            uploaded_file_path = None
            uploaded_file_name = None
            uploaded_file_preview = None

            if isinstance(answer.answer_data, dict):
                answer_text = answer.answer_data.get("text")
                uploaded_file_path = answer.answer_data.get("file_path")
                # The exam page stores uploaded images inline as a data: URL
                preview = answer.answer_data.get("preview")
                if isinstance(preview, str) and preview.startswith("data:image/"):
                    uploaded_file_preview = preview
                uploaded_file_name = answer.answer_data.get("name")
            elif isinstance(answer.answer_data, str):
                answer_text = answer.answer_data

            answer_dict = {
                "answer_id": str(answer.id),
                "question_id": str(question.id),
                "question_title": question.title,
                "question_type": question.type,
                "question_max_score": marks.get(question.id, question.max_score),
                "answer_text": answer_text,
                "uploaded_file_path": uploaded_file_path,
                "uploaded_file_name": uploaded_file_name,
                "uploaded_file_preview": uploaded_file_preview,
                "is_evaluated": evaluation is not None,
                "score_awarded": evaluation.score_awarded if evaluation else None,
                "comment": evaluation.comment if evaluation else None,
            }
            response["answers"].append(answer_dict)

        return response

    except HTTPException:
        raise
    except Exception:
        logger.exception("Loading attempt for grading failed")
        raise HTTPException(status_code=500, detail=internal_error_detail())


@router.post("/evaluations/answers/{answer_id}/submit")
def submit_answer_evaluation(
    answer_id: UUID,
    grade: schemas.GradeIn,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Grade a written or image answer: `score_awarded` from 0 to what it's worth (or `is_correct` for full marks
    or none), and an optional comment."""
    evaluation = _grade(db, answer_id, grade, membership)
    return {
        "status": "success",
        "message": "Evaluation submitted successfully",
        "answer_id": str(answer_id),
        "score_awarded": evaluation.score_awarded,
    }
