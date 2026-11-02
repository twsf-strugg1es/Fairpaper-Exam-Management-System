"""Background jobs. The API runs them in a loop (see `main.lifespan`); cron can run them too:

    python -m app.jobs finalize-attempts

Every job must be safe to run twice at once (several API instances, or the loop plus cron).
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import crud, models
from .database import SessionLocal

logger = logging.getLogger(__name__)

FINALIZE_EVERY_SECONDS = 60


def finalize_overdue_attempts(db: Session, now: datetime | None = None) -> int:
    """Score attempts whose time ran out without a submit (closed tab, lost connection).

    They end at their deadline, as `time_up`, once the answer grace period has passed.
    Returns how many were finalized here.
    """
    now = now or datetime.now(timezone.utc)
    grace = timedelta(seconds=crud.ANSWER_GRACE_SECONDS)
    open_attempts = (
        db.query(models.ExamAttempt)
        .join(models.Exam, models.Exam.id == models.ExamAttempt.exam_id)
        .filter(models.ExamAttempt.end_time.is_(None))
        .all()
    )
    finalized = 0
    for attempt in open_attempts:
        exam = attempt.exam
        deadline = crud.get_attempt_deadline(attempt, exam)
        # Timed sections or questions end the attempt when the last one's time ran out, if that came first
        for blocks in (crud.section_timeline(db, exam, attempt, now), crud.question_timeline(db, exam, attempt, now)):
            if blocks and all(e["state"] == "closed" for e in blocks):
                deadline = min(deadline, max(crud.as_utc(e["row"].closed_at) for e in blocks))
        if now <= deadline + grace:
            continue
        if crud.finish_attempt(db, attempt, reason=models.SUBMIT_TIME_UP, ended_at=deadline):
            finalized += 1
    if finalized:
        logger.info("Finalized abandoned attempts", extra={"fields": {"count": finalized}})
    return finalized


def _run_finalizer() -> None:
    db = SessionLocal()
    try:
        finalize_overdue_attempts(db)
    except Exception:
        logger.exception("Finalizing abandoned attempts failed")
        db.rollback()
    finally:
        db.close()


def jobs_enabled() -> bool:
    return os.getenv("BACKGROUND_JOBS", "on").lower() != "off"


async def run_forever() -> None:
    """The API's job loop. Cancelled when the app shuts down."""
    while True:
        await asyncio.to_thread(_run_finalizer)
        await asyncio.sleep(FINALIZE_EVERY_SECONDS)


if __name__ == "__main__":
    from .logging_config import configure_logging

    configure_logging()
    if sys.argv[1:] == ["finalize-attempts"]:
        _run_finalizer()
    else:
        sys.exit("usage: python -m app.jobs finalize-attempts")
