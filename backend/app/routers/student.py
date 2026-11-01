from uuid import UUID
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import logging

from ..database import get_db
from .. import crud, models, question_types, schemas
from ..logging_config import internal_error_detail
from ..permissions import require_candidate

router = APIRouter(prefix="/student", tags=["Student"])
logger = logging.getLogger(__name__)


def _hide_scores(payload: dict) -> dict:
    """Scores stay on the server until the exam's results are released."""
    for key in ("score", "total_possible_score", "percentage"):
        if key in payload:
            payload[key] = None
    payload["results_released"] = False
    return payload


def _with_release(payload: dict, exam: models.Exam) -> dict:
    if not crud.results_visible(exam):
        return _hide_scores(payload)
    payload["results_released"] = True
    return payload


def _attempt_payload(attempt: models.ExamAttempt) -> dict:
    return {
        "id": str(attempt.id),
        "exam_id": str(attempt.exam_id),
        "student_id": str(attempt.student_id),
        "start_time": crud.iso(attempt.start_time),
        "end_time": crud.iso(attempt.end_time),
        "score": attempt.score,
        "total_possible_score": attempt.total_possible_score,
        "submit_reason": attempt.submit_reason,
    }


def _exam_session(db: Session, exam: models.Exam, attempt: models.ExamAttempt, now: datetime) -> dict:
    """What the exam page needs to run an attempt: questions in this student's order,
    the time left, and the integrity rules to enforce."""
    deadline = crud.get_attempt_deadline(attempt, exam)
    crud.draw_pool_questions(db, exam, attempt)  # once per attempt; later calls keep the same paper
    return {
        "exam": {
            "id": str(exam.id),
            "title": exam.title,
            "start_time": crud.iso(exam.start_time),
            "end_time": crud.iso(exam.end_time),
            "duration_minutes": exam.duration_minutes,
            "is_published": exam.is_published,
            "questions": crud.questions_for_attempt(db, exam, attempt),
            # Remaining time runs from the attempt start, capped at the exam window's end
            "time_remaining_seconds": max(0, int((deadline - now).total_seconds())),
            "exam_end_time": crud.iso(exam.end_time),
        },
        "attempt": _attempt_payload(attempt),
        "integrity": {
            **crud.integrity_settings(exam),
            "violations": crud.count_violations(db, attempt.id),
        },
    }


@router.get("/exams/")
def list_available_exams(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """List the published exams this candidate may take in the current organization."""
    exams = crud.get_available_exams(db, membership)
    now = datetime.now(timezone.utc)
    submitted_exam_ids = {
        exam_id
        for (exam_id,) in db.query(models.ExamAttempt.exam_id).filter(
            models.ExamAttempt.student_id == membership.user_id,
            models.ExamAttempt.end_time.isnot(None),
        )
    }

    result = []
    for exam in exams:
        # Get publisher email if published
        publisher_email = None
        if exam.published_by:
            publisher = db.query(models.User).filter(models.User.id == exam.published_by).first()
            publisher_email = publisher.email if publisher else "Unknown"

        # Determine exam status
        is_expired = now > crud.as_utc(exam.end_time)
        is_upcoming = now < crud.as_utc(exam.start_time)
        is_active = not is_expired and not is_upcoming

        # Manually build exam dict
        exam_dict = {
            "id": str(exam.id),
            "title": exam.title,
            "start_time": crud.iso(exam.start_time),
            "end_time": crud.iso(exam.end_time),
            "duration_minutes": exam.duration_minutes,
            "is_published": exam.is_published,
            "published_by": publisher_email,
            "is_expired": is_expired,
            "is_upcoming": is_upcoming,
            "is_active": is_active,
            "is_submitted": exam.id in submitted_exam_ids,  # one attempt per exam
            # Shown on the exam's rules screen before the student starts
            "integrity": crud.integrity_settings(exam),
            # Only the count: question content is sent when an attempt starts
            "question_count": crud.exam_question_count(exam),
        }
        result.append(exam_dict)
    return result


@router.get("/unfinished-attempts/")
def list_unfinished_attempts(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """List the current student's unfinished exam attempts in this organization."""
    attempts = (
        db.query(models.ExamAttempt)
        .join(models.Exam, models.ExamAttempt.exam_id == models.Exam.id)
        .filter(
            models.ExamAttempt.student_id == membership.user_id,
            models.ExamAttempt.end_time.is_(None),
            models.Exam.organization_id == membership.organization_id,
        )
        .all()
    )

    # Build response with exam details
    result = []
    for attempt in attempts:
        exam = crud.get_exam_by_id(db, attempt.exam_id)
        if exam:
            result.append({
                "id": str(attempt.id),
                "exam_id": str(attempt.exam_id),
                "student_id": str(attempt.student_id),
                "start_time": crud.iso(attempt.start_time),
                "end_time": crud.iso(attempt.end_time),
                "score": attempt.score,
                "total_possible_score": attempt.total_possible_score,
                "exam": {
                    "id": str(exam.id),
                    "title": exam.title,
                    "start_time": crud.iso(exam.start_time),
                    "end_time": crud.iso(exam.end_time),
                    "duration_minutes": exam.duration_minutes,
                    "is_published": exam.is_published,
                }
            })

    return result


@router.post("/exams/{exam_id}/start")
def start_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Start an exam attempt for the current student."""
    try:
        # CRITICAL: Expire all objects at the very start to prevent race conditions
        # This ensures we get fresh reads from the database for the existence check
        db.expire_all()

        exam = crud.get_exam_by_id(db, exam_id)
        if not exam or not crud.visible_to_candidate(exam, membership):
            raise HTTPException(status_code=404, detail="Exam not found")

        if not exam.is_published:
            raise HTTPException(
                status_code=400,
                detail="Exam is not published yet",
            )

        # Check exam timing
        now = datetime.now(timezone.utc)
        if now < crud.as_utc(exam.start_time):
            raise HTTPException(
                status_code=400,
                detail="This exam hasn't opened yet.",  # the rules screen shows when it opens, in local time
            )

        if now > crud.as_utc(exam.end_time):
            raise HTTPException(
                status_code=400,
                detail="Exam time has expired. You can no longer take this exam",
            )

        # One attempt per student: retaking would let them improve on a known score
        already_submitted = (
            db.query(models.ExamAttempt)
            .filter(
                models.ExamAttempt.exam_id == exam_id,
                models.ExamAttempt.student_id == membership.user_id,
                models.ExamAttempt.end_time.isnot(None),
            )
            .first()
        )
        if already_submitted:
            raise HTTPException(status_code=400, detail="You have already submitted this exam")

        # Check if student already has an unfinished attempt for this exam
        existing_attempt = (
            db.query(models.ExamAttempt)
            .filter(
                models.ExamAttempt.exam_id == exam_id,
                models.ExamAttempt.student_id == membership.user_id,
                models.ExamAttempt.end_time.is_(None)
            )
            .first()
        )

        if existing_attempt:
            # Return existing attempt instead of creating a new one
            attempt = existing_attempt
        else:
            # Create a new exam attempt
            attempt = crud.create_exam_attempt(db, exam_id, membership.user_id)
            # Immediately commit to ensure it's in the database
            db.commit()

        return _exam_session(db, exam, attempt, now)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Starting exam failed", extra={"fields": {"exam_id": str(exam_id)}})
        raise HTTPException(status_code=500, detail=internal_error_detail())


@router.post("/attempts/{attempt_id}/resume")
def resume_exam(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Resume an existing exam attempt for the current student."""
    # Get the attempt and verify ownership
    attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.id == attempt_id,
            models.ExamAttempt.student_id == membership.user_id,
            models.ExamAttempt.end_time.is_(None)  # Must be unfinished
        )
        .first()
    )

    if not attempt:
        raise HTTPException(
            status_code=404,
            detail="Unfinished attempt not found or does not belong to you",
        )

    # Get the exam
    exam = crud.get_exam_by_id(db, attempt.exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if not exam.is_published:
        raise HTTPException(
            status_code=400,
            detail="Exam is not published anymore",
        )

    # Auto-submit once the attempt's time is up
    now = datetime.now(timezone.utc)
    deadline = crud.get_attempt_deadline(attempt, exam)
    if now > deadline:
        crud.calculate_and_save_score(db, attempt, reason=models.SUBMIT_TIME_UP, ended_at=deadline)
        return {
            "exam": {"id": str(exam.id), "title": exam.title, "auto_submitted": True},
            "attempt": _with_release(_attempt_payload(attempt), exam),
        }

    return _exam_session(db, exam, attempt, now)


@router.post("/attempts/{attempt_id}/save-answer")
def save_answer(
    attempt_id: UUID,
    answer_in: schemas.AnswerCreate,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Auto-save a student's answer to a question."""
    try:
        saved = crud.save_answer(db, attempt_id, membership.user_id, answer_in)
        # "stale": a newer answer is already stored. The page treats both as delivered
        return {"status": "saved" if saved else "stale"}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/attempts/{attempt_id}/events")
def report_integrity_events(
    attempt_id: UUID,
    data: schemas.IntegrityEventsIn,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Record what the exam page noticed (leaving the tab, exiting fullscreen, copy attempts...).

    Returns the violation count; when it reaches the exam's limit the attempt is submitted.
    """
    attempt = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.id == attempt_id, models.ExamAttempt.student_id == membership.user_id)
        .first()
    )
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found or does not belong to you")

    if attempt.end_time is None:
        violations = crud.record_integrity_events(db, attempt, data.events)
    else:
        violations = crud.count_violations(db, attempt.id)  # late events after submitting are ignored

    return {
        "violations": violations,
        "max_violations": attempt.exam.max_violations,
        "submitted": attempt.end_time is not None,
        "submit_reason": attempt.submit_reason,
    }


@router.post("/attempts/{attempt_id}/submit")
def submit_exam(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Submit the exam attempt and calculate the score."""
    # Get the attempt and verify ownership
    attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.id == attempt_id,
            models.ExamAttempt.student_id == membership.user_id,
        )
        .first()
    )

    if not attempt:
        raise HTTPException(
            status_code=404,
            detail="Attempt not found or does not belong to you",
        )

    if attempt.end_time is not None:
        raise HTTPException(
            status_code=400,
            detail="Exam already submitted",
        )

    # Calculate and save score
    try:
        # Store these values BEFORE calling calculate_and_save_score which may expunge the session
        attempt_id = str(attempt.id)
        exam_id = str(attempt.exam_id)
        student_id = str(attempt.student_id)
        start_time = crud.iso(attempt.start_time)

        # Submits arriving as the clock runs out are the page's automatic time-up submit
        exam = crud.get_exam_by_id(db, attempt.exam_id)
        deadline = crud.get_attempt_deadline(attempt, exam)
        time_up = datetime.now(timezone.utc) >= deadline - timedelta(seconds=5)
        reason = models.SUBMIT_TIME_UP if time_up else models.SUBMIT_STUDENT

        updated_attempt = crud.calculate_and_save_score(db, attempt, reason=reason)

        # Store the returned values as well
        end_time = crud.iso(updated_attempt.end_time)
        score = updated_attempt.score
        total = updated_attempt.total_possible_score

        # Return manually built response instead of using response_model
        return _with_release({
            "id": attempt_id,
            "exam_id": exam_id,
            "student_id": student_id,
            "start_time": start_time,
            "end_time": end_time,
            "score": score,
            "total_possible_score": total,
            "submit_reason": updated_attempt.submit_reason,
        }, exam)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/attempts/{attempt_id}/answers")
def get_attempt_answers(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Get all answers for a specific exam attempt."""
    # Verify attempt belongs to the current student
    attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.id == attempt_id,
            models.ExamAttempt.student_id == membership.user_id,
        )
        .first()
    )
    if not attempt:
        raise HTTPException(
            status_code=404,
            detail="Attempt not found or does not belong to you",
        )

    # Fetch student's answers for this attempt
    answers = (
        db.query(models.Answer)
        .filter(models.Answer.attempt_id == attempt_id)
        .all()
    )

    return [schemas.Answer.model_validate(a) for a in answers]


@router.get("/attempts/{attempt_id}/results")
def get_attempt_results(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Return the submitted attempt with student's answers and the full exam with correct answers."""
    # Verify attempt belongs to the current student
    attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.id == attempt_id,
            models.ExamAttempt.student_id == membership.user_id,
        )
        .first()
    )
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found or does not belong to you")

    if attempt.end_time is None:
        raise HTTPException(status_code=400, detail="Exam not submitted")

    # Fetch the full exam (with correct answers)
    exam = crud.get_exam_by_id(db, attempt.exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Withhold the answer key while others may still be writing the exam
    released = crud.results_visible(exam)
    answers_revealed = released and datetime.now(timezone.utc) > crud.as_utc(exam.end_time)

    # Fetch student's answers for this attempt
    answers = (
        db.query(models.Answer)
        .filter(models.Answer.attempt_id == attempt.id)
        .all()
    )

    given = {a.question_id: a.answer_data for a in answers}
    attempt_payload = schemas.ExamAttempt.model_validate(attempt).model_dump()
    attempt_payload["answers"] = [
        schemas.Answer.model_validate(a).model_dump() for a in answers
    ]
    attempt_payload = _with_release(attempt_payload, exam)

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
        "answers_revealed": answers_revealed,
        "questions": [
            {
                "id": str(q.id),
                "title": q.title,
                "complexity": q.complexity,
                "type": q.type,
                # Until the answers are out, the same view as in the exam: stored order can be the key
                "options": q.options if answers_revealed else question_types.student_options(
                    q, f"{attempt.id}:{q.id}", exam.shuffle_options),
                "correct_answers": q.correct_answers if answers_revealed else None,
                "is_correct": question_types.is_correct(q.type, q.correct_answers, given.get(q.id)) if answers_revealed else None,
                "max_score": int(worth),
                "tags": q.tags,
            }
            for q, worth in crud.attempt_questions(db, exam, attempt)
        ],
    }

    return {"attempt": attempt_payload, "exam": exam_payload}


@router.get("/completed-exams/")
def list_completed_exams(
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """List the current student's completed exams in this organization with their scores."""
    attempts = (
        db.query(models.ExamAttempt)
        .join(models.Exam, models.ExamAttempt.exam_id == models.Exam.id)
        .filter(
            models.ExamAttempt.student_id == membership.user_id,
            models.ExamAttempt.end_time.isnot(None),
            models.Exam.organization_id == membership.organization_id,
        )
        .all()
    )

    result = []
    for attempt in attempts:
        exam = crud.get_exam_by_id(db, attempt.exam_id)
        if exam:
            # Get all answers for this attempt
            answers = (
                db.query(models.Answer)
                .filter(models.Answer.attempt_id == attempt.id)
                .all()
            )

            # Calculate final score with manual evaluations included
            manual_score_total = 0.0
            for answer in answers:
                eval_record = crud.get_evaluation_by_answer(db, answer.id)
                if eval_record and eval_record.score_awarded is not None:
                    question = crud.get_question_by_id(db, answer.question_id)
                    if question and question.type in models.MANUAL_TYPES:
                        manual_score_total += float(eval_record.score_awarded)

            # Final score: auto-graded + manual scores (capped at total)
            final_score = min(attempt.score + manual_score_total, attempt.total_possible_score or 0)

            # Calculate percentage
            percentage = 0
            if attempt.total_possible_score and attempt.total_possible_score > 0:
                percentage = (final_score / attempt.total_possible_score) * 100

            result.append(_with_release({
                "id": str(attempt.id),
                "exam_id": str(attempt.exam_id),
                "exam_title": exam.title,
                "score": final_score,
                "total_possible_score": attempt.total_possible_score,
                "percentage": round(percentage, 2),
                "end_time": crud.iso(attempt.end_time),
            }, exam))

    return result


@router.get("/attempts/{attempt_id}/evaluated-results")
def get_evaluated_results(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    membership: models.Membership = Depends(require_candidate),
):
    """Get exam results with teacher evaluations for a student."""
    # Get the attempt and verify ownership
    attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.id == attempt_id,
            models.ExamAttempt.student_id == membership.user_id,
            models.ExamAttempt.end_time.isnot(None)  # Must be submitted
        )
        .first()
    )

    if not attempt:
        raise HTTPException(status_code=404, detail="Exam attempt not found or does not belong to you")

    # Get the exam
    exam = crud.get_exam_by_id(db, attempt.exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if not crud.results_visible(exam):
        # Nothing about the marking until the results are released
        return _hide_scores({
            "exam_title": exam.title, "score": None, "total_possible_score": None, "percentage": None,
            "submitted_at": crud.iso(attempt.end_time), "answers_with_evaluations": [],
        })

    # Get student's answers
    answers = (
        db.query(models.Answer)
        .filter(models.Answer.attempt_id == attempt.id)
        .all()
    )

    # Get evaluations for all answers
    evaluations_map = {}
    manual_score_total = 0.0  # Sum of manually awarded scores for text/image_upload questions
    for answer in answers:
        eval_record = crud.get_evaluation_by_answer(db, answer.id)
        if eval_record:
            evaluations_map[str(answer.id)] = schemas.Evaluation.model_validate(eval_record).model_dump()
            # Only add manual scores for questions that require manual evaluation (text, image_upload)
            # These are NOT auto-graded, so the manual score IS the score for that question
            if eval_record.score_awarded is not None:
                question = crud.get_question_by_id(db, answer.question_id)
                if question and question.type in models.MANUAL_TYPES:
                    manual_score_total += float(eval_record.score_awarded)

    # Calculate final score: auto-graded questions score + manual evaluation scores
    # Ensure it doesn't exceed total possible score
    final_score = min(attempt.score + manual_score_total, attempt.total_possible_score or 0)

    # Build answer details with evaluations
    worth = {q.id: w for q, w in crud.attempt_questions(db, exam, attempt)}
    answers_with_eval = []
    for answer in answers:
        question = crud.get_question_by_id(db, answer.question_id)
        evaluation = evaluations_map.get(str(answer.id))

        answers_with_eval.append({
            "id": str(answer.id),
            "question_id": str(answer.question_id),
            "question_title": question.title if question else "Unknown",
            "question_type": question.type if question else "unknown",
            "question_max_score": worth.get(answer.question_id),
            "answer_data": answer.answer_data,
            "evaluation": evaluation,
        })

    # Calculate percentage using final score
    percentage = 0
    if attempt.total_possible_score and attempt.total_possible_score > 0:
        percentage = (final_score / attempt.total_possible_score) * 100

    # Get publisher info
    publisher_email = "Unknown"
    if exam.published_by:  # Use the foreign key ID, not the relationship
        publisher = db.query(models.User).filter(models.User.id == exam.published_by).first()
        if publisher:
            publisher_email = publisher.email

    return {
        "exam_title": exam.title,
        "score": final_score,
        "total_possible_score": attempt.total_possible_score,
        "percentage": round(percentage, 2),
        "submitted_at": crud.iso(attempt.end_time),
        "published_by": publisher_email,
        "answers_with_evaluations": answers_with_eval,
        "results_released": True,
        "rank": _rank_for(db, exam, attempt),
    }


def _rank_for(db: Session, exam: models.Exam, attempt: models.ExamAttempt) -> dict | None:
    """{position, of, tied} on the merit list, only when the exam is set to show it."""
    if not exam.show_rank:
        return None
    rows = crud.merit_list(db, exam)
    mine = next((r for r in rows if r["attempt"].id == attempt.id), None)
    return {"position": mine["rank"], "of": len(rows), "tied": mine["tied"]} if mine else None
