import json
from typing import Any
from uuid import UUID
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status, Query, Body
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import String, cast
from sqlalchemy.orm import Session, joinedload
import openpyxl

import logging

from ..database import get_db
from .. import schemas, crud, models, results_export
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


@router.post("/upload-questions/")
async def upload_questions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Only Excel files (.xlsx or .xls) are accepted. Please upload a valid Excel file."
        )

    try:
        wb = openpyxl.load_workbook(file.file, data_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {str(e)}")

    # Validate header columns and build index map
    try:
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        header = [str(h).strip().lower() if h is not None else "" for h in header_row]
    except StopIteration:
        raise HTTPException(status_code=400, detail="Excel file is empty")

    expected = [
        "title",
        "complexity",
        "type",
        "options",
        "correct_answers",
        "max_score",
    ]
    missing = [c for c in expected if c not in header]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}",
        )
    idx = {name: header.index(name) for name in expected}

    # Check if optional columns exist
    tags_idx = header.index("tags") if "tags" in header else None
    desc_idx = header.index("description") if "description" in header else None

    allowed_types = {"single_choice", "multi_choice", "text", "image_upload"}
    allowed_complexity = {"easy", "medium", "hard"}

    imported = 0
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row:
            continue
        # Extract using header indices for flexibility
        title = row[idx["title"]] if idx["title"] < len(row) else None
        complexity = row[idx["complexity"]] if idx["complexity"] < len(row) else None
        qtype = row[idx["type"]] if idx["type"] < len(row) else None
        options_raw = row[idx["options"]] if idx["options"] < len(row) else None
        correct_raw = row[idx["correct_answers"]] if idx["correct_answers"] < len(row) else None
        max_score_raw = row[idx["max_score"]] if idx["max_score"] < len(row) else None
        tags_raw = row[tags_idx] if tags_idx is not None and tags_idx < len(row) else None
        description = row[desc_idx] if desc_idx is not None and desc_idx < len(row) else None

        if not title or not complexity or not qtype:
            # Skip incomplete rows
            continue

        # Normalize complexity to lowercase
        complexity = str(complexity).strip().lower()
        if complexity not in allowed_complexity:
            raise HTTPException(
                status_code=400,
                detail=f"Row {i}: invalid complexity '{complexity}'. Allowed: {sorted(allowed_complexity)}",
            )

        qtype = str(qtype).strip()
        if qtype not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Row {i}: invalid type '{qtype}'. Allowed: {sorted(allowed_types)}",
            )

        try:
            tags = crud.normalize_tags(tags_raw if isinstance(tags_raw, (str, list)) else None)

            # Parse options
            options: Any = None
            if isinstance(options_raw, str):
                if options_raw.strip() not in ("", "null"):
                    options = json.loads(options_raw)
            elif options_raw not in (None, ""):
                options = options_raw

            # Parse correct answers
            if isinstance(correct_raw, str):
                correct_answers: Any = json.loads(correct_raw)
            else:
                correct_answers = correct_raw

            # Validate by type
            if qtype == "text" or qtype == "image_upload":
                # For text and image_upload questions, options and correct_answers should be null
                options = None
                correct_answers = None
            elif qtype == "single_choice":
                # options should be an array; correct_answers should be a single value
                if options is None or not isinstance(options, list):
                    raise ValueError("'options' must be a JSON array for single_choice")
                if isinstance(correct_answers, list) and len(correct_answers) == 1:
                    correct_answers = correct_answers[0]  # accept ["4"] as well as "4"
                if isinstance(correct_answers, list):
                    raise ValueError("'correct_answers' must be a single JSON value for single_choice")
            elif qtype == "multi_choice":
                # options should be an array; correct_answers should be an array
                if options is None or not isinstance(options, list):
                    raise ValueError("'options' must be a JSON array for multi_choice")
                if correct_answers is None or not isinstance(correct_answers, list):
                    raise ValueError("'correct_answers' must be a JSON array for multi_choice")

            # For non-text types, correct_answers is required
            if qtype in {"single_choice", "multi_choice"} and correct_answers in (None, ""):
                raise ValueError("'correct_answers' is required for single_choice and multi_choice")

            # max score
            max_score_val = int(max_score_raw) if max_score_raw not in (None, "") else 1
            if max_score_val <= 0:
                raise ValueError("max_score must be positive")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Row {i} parse error: {e}")

        q_schema = schemas.QuestionBase(
            title=str(title),
            description=str(description) if description else None,
            complexity=complexity,
            type=qtype,
            options=options,
            correct_answers=correct_answers,
            max_score=max_score_val,
            tags=tags if tags else None,
        )
        crud.create_question(db, q_schema, membership.organization_id)
        imported += 1

    return JSONResponse({"status": "success", "rows_imported": imported})


@router.post("/preview-questions/")
async def preview_questions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Preview questions from Excel file without importing them."""
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Only Excel files (.xlsx or .xls) are accepted. Please upload a valid Excel file."
        )

    try:
        wb = openpyxl.load_workbook(file.file, data_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    # Validate header columns and build index map
    try:
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        header = [str(h).strip().lower() if h is not None else "" for h in header_row]
    except StopIteration:
        raise HTTPException(status_code=400, detail="Excel file is empty")

    expected = [
        "title",
        "complexity",
        "type",
        "options",
        "correct_answers",
        "max_score",
    ]
    missing = [c for c in expected if c not in header]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}",
        )
    idx = {name: header.index(name) for name in expected}

    # Check if optional columns exist
    tags_idx = header.index("tags") if "tags" in header else None
    desc_idx = header.index("description") if "description" in header else None

    allowed_types = {"single_choice", "multi_choice", "text", "image_upload"}
    preview_data = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row:
            continue
        # Extract using header indices for flexibility
        title = row[idx["title"]] if idx["title"] < len(row) else None
        complexity = row[idx["complexity"]] if idx["complexity"] < len(row) else None
        qtype = row[idx["type"]] if idx["type"] < len(row) else None
        options_raw = row[idx["options"]] if idx["options"] < len(row) else None
        correct_raw = row[idx["correct_answers"]] if idx["correct_answers"] < len(row) else None
        max_score_raw = row[idx["max_score"]] if idx["max_score"] < len(row) else None

        if not title or not complexity or not qtype:
            # Skip incomplete rows
            continue

        qtype = str(qtype).strip()
        if qtype not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Row {i}: invalid type '{qtype}'. Allowed: {sorted(allowed_types)}",
            )

        try:
            # Parse options
            options: Any = None
            if isinstance(options_raw, str):
                if options_raw.strip() not in ("", "null"):
                    options = json.loads(options_raw)
            elif options_raw not in (None, ""):
                options = options_raw

            # Parse correct answers
            if isinstance(correct_raw, str):
                correct_answers: Any = json.loads(correct_raw)
            else:
                correct_answers = correct_raw

            # Validate by type
            if qtype == "text" or qtype == "image_upload":
                # For text and image_upload questions, options and correct_answers should be null
                options = None
                correct_answers = None
            elif qtype == "single_choice":
                # options should be an array; correct_answers should be a single value
                if options is None or not isinstance(options, list):
                    raise ValueError("'options' must be a JSON array for single_choice")
                if isinstance(correct_answers, list) and len(correct_answers) == 1:
                    correct_answers = correct_answers[0]  # accept ["4"] as well as "4"
                if isinstance(correct_answers, list):
                    raise ValueError("'correct_answers' must be a single JSON value for single_choice")
            elif qtype == "multi_choice":
                # options should be an array; correct_answers should be an array
                if options is None or not isinstance(options, list):
                    raise ValueError("'options' must be a JSON array for multi_choice")
                if correct_answers is None or not isinstance(correct_answers, list):
                    raise ValueError("'correct_answers' must be a JSON array for multi_choice")

            # For non-text types, correct_answers is required
            if qtype in {"single_choice", "multi_choice"} and correct_answers in (None, ""):
                raise ValueError("'correct_answers' is required for single_choice and multi_choice")

            # max score
            max_score_val = int(max_score_raw) if max_score_raw not in (None, "") else 1
            if max_score_val <= 0:
                raise ValueError("max_score must be positive")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Row {i} parse error: {e}")

        preview_data.append({
            "title": str(title),
            "complexity": str(complexity),
            "type": qtype,
            "options": options,
            "correct_answers": correct_answers,
            "max_score": max_score_val,
        })

    return JSONResponse({"questions": preview_data, "count": len(preview_data)})


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
    # Sample rows
    ws.append([
        "What is 2+2?",
        "easy",
        "single_choice",
        "[\"1\", \"2\", \"3\", \"4\"]",
        "[\"4\"]",
        1,
        "math,arithmetic",
    ])
    ws.append([
        "Select prime numbers",
        "medium",
        "multi_choice",
        "[\"2\", \"4\", \"5\", \"6\"]",
        "[\"2\", \"5\"]",
        2,
        "math",
    ])
    ws.append([
        "Briefly explain polymorphism",
        "hard",
        "text",
        "null",
        "null",
        5,
        "programming,oop",
    ])
    ws.append([
        "Upload a diagram of the water cycle",
        "medium",
        "image_upload",
        "null",
        "null",
        10,
        "science,biology",
    ])

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
            }
            for q in (exam.questions or [])
        ],
        "pool_rules": [
            {"id": str(r.id), "count": r.count, "complexity": r.complexity, "tag": r.tag, "marks": r.marks}
            for r in exam.pool_rules
        ],
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
                    if question and question.type in ("text", "image_upload"):
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
            if question and question.type in ("text", "image_upload"):
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


@router.post("/answers/{answer_id}/evaluate", response_model=schemas.Evaluation)
def evaluate_answer(
    answer_id: UUID,
    evaluation: schemas.EvaluationCreate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Evaluate a student's answer (mark as right/wrong, add comment)."""
    # Verify answer exists
    answer = _get_org_answer(db, answer_id, membership)
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    # Ensure comment is max 100 characters
    if evaluation.comment and len(evaluation.comment) > 100:
        raise HTTPException(
            status_code=400,
            detail="Comment must be 100 characters or less"
        )

    eval_record = crud.create_or_update_evaluation(
        db, answer_id, membership.user_id, evaluation
    )
    return eval_record


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
                        if question and question.type in ("text", "image_upload"):
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
    request_body: dict = Body(...),
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """Save evaluations for exam attempt answers."""
    # Get the attempt
    attempt = _get_org_attempt(db, attempt_id, membership)

    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    answers_data = request_body.get("answers", [])
    attempt_answer_ids = {
        a.id for a in db.query(models.Answer).filter(models.Answer.attempt_id == attempt.id)
    }

    for answer_eval in answers_data:
        answer_id = UUID(str(answer_eval.get("answer_id")))
        if answer_id not in attempt_answer_ids:
            raise HTTPException(status_code=400, detail="Answer does not belong to this attempt")
        score = answer_eval.get("score", 0)
        feedback = answer_eval.get("feedback", "")

        # Get or create evaluation record
        evaluation = db.query(models.Evaluation).filter(
            models.Evaluation.answer_id == answer_id
        ).first()

        if evaluation:
            # Update existing evaluation
            evaluation.score_awarded = score
            evaluation.comment = feedback
            evaluation.updated_at = datetime.now(timezone.utc)
        else:
            # Create new evaluation
            evaluation = models.Evaluation(
                answer_id=answer_id,
                evaluated_by=membership.user_id,
                score_awarded=score,
                comment=feedback,
            )
            db.add(evaluation)

        db.commit()

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
            if not question or question.type not in ["text", "image_upload"]:
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
    evaluation_data: dict = Body(...),
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_staff),
):
    """
    Submit evaluation for a single answer.
    evaluation_data should have: {"is_correct": bool, "comment": str}
    """
    try:
        # Verify answer exists
        answer = _get_org_answer(db, answer_id, membership)

        if not answer:
            raise HTTPException(status_code=404, detail="Answer not found")

        # Get the question to find max score
        question = db.query(models.Question).filter(
            models.Question.id == answer.question_id
        ).first()

        if not question:
            raise HTTPException(status_code=404, detail="Question not found")

        # Validate input
        is_correct = evaluation_data.get("is_correct")
        comment = evaluation_data.get("comment", "")

        if is_correct is None:
            raise HTTPException(status_code=400, detail="is_correct field is required")

        # Validate comment length
        if comment and len(comment) > 100:
            raise HTTPException(status_code=400, detail="Comment must be 100 characters or less")

        # Calculate score: full marks if correct, 0 if incorrect
        attempt = db.get(models.ExamAttempt, answer.attempt_id)
        exam = db.get(models.Exam, attempt.exam_id) if attempt else None
        paper = {q.id: int(worth) for q, worth in crud.attempt_questions(db, exam, attempt)} if exam and attempt else {}
        full_marks = paper.get(question.id, question.max_score)
        score_awarded = full_marks if is_correct else 0

        # Get or create evaluation
        evaluation = db.query(models.Evaluation).filter(
            models.Evaluation.answer_id == answer_id
        ).first()

        if evaluation:
            evaluation.score_awarded = score_awarded
            evaluation.comment = comment
            evaluation.updated_at = datetime.now(timezone.utc)
        else:
            evaluation = models.Evaluation(
                answer_id=answer_id,
                evaluated_by=membership.user_id,
                score_awarded=score_awarded,
                comment=comment,
            )
            db.add(evaluation)

        db.commit()

        return {
            "status": "success",
            "message": "Evaluation submitted successfully",
            "answer_id": str(answer_id),
            "score_awarded": score_awarded,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Saving grade failed")
        raise HTTPException(status_code=500, detail=internal_error_detail())