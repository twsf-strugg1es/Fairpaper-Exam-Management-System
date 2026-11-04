"""Exam analytics (task 4.12): how each question worked (item analysis), how the class did per topic, and how the
scores spread. Built from the submitted attempts' own papers (crud.breakdowns), so random questions count only
for the students who drew them, and written answers count once they're graded.

Difficulty index: the share of the marks students earned on a question (1.0: everyone got it all). Discrimination
index: that share among the top 27 % of students by total score minus the share among the bottom 27 % (from -1
to 1); a good question is answered better by the students who did better overall. It needs at least
MIN_FOR_DISCRIMINATION submitted attempts to mean anything.
"""
import statistics

from sqlalchemy.orm import Session

from . import crud, models

GROUP_SHARE = 0.27  # the classic upper and lower groups
MIN_FOR_DISCRIMINATION = 5
VERY_HARD, VERY_EASY = 0.25, 0.9
WEAK_DISCRIMINATION = 0.2
CHOICE_TYPES = (*models.CHOICE_TYPES, "true_false")


def _share(rows: list[dict]) -> float | None:
    worth = sum(r["worth"] for r in rows)
    return round(sum(r["earned"] for r in rows) / worth, 3) if worth else None


def _flags(difficulty: float | None, discrimination: float | None) -> list[str]:
    flags = []
    if difficulty is not None and difficulty < VERY_HARD:
        flags.append("very_hard")
    if difficulty is not None and difficulty > VERY_EASY:
        flags.append("very_easy")
    if discrimination is not None and discrimination < 0:
        flags.append("check_key")  # stronger students did worse: often a wrong key or a misleading question
    elif discrimination is not None and discrimination < WEAK_DISCRIMINATION:
        flags.append("weak")
    return flags


def _picked(answer_data) -> list[str]:
    if answer_data is None:
        return []
    return [str(v) for v in answer_data] if isinstance(answer_data, list) else [str(answer_data)]


def exam_analytics(db: Session, exam: models.Exam) -> dict:
    """Item analysis, topics and the score distribution for an exam's submitted attempts."""
    attempts = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.exam_id == exam.id, models.ExamAttempt.end_time.isnot(None))
        .order_by(models.ExamAttempt.id)
        .all()
    )
    papers = crud.breakdowns(db, exam, attempts)
    answers = {
        (a.attempt_id, a.question_id): a.answer_data
        for a in db.query(models.Answer).filter(models.Answer.attempt_id.in_([a.id for a in attempts]))
    } if attempts else {}

    # Each attempt's share of its paper's marks; ungraded written answers count as 0 here until graded
    totals = {}
    for attempt in attempts:
        rows = papers[attempt.id]
        worth = sum(r["worth"] for r in rows)
        totals[attempt.id] = sum(r["earned"] or 0 for r in rows) / worth if worth else 0.0
    ranked = sorted(attempts, key=lambda a: (-totals[a.id], str(a.id)))
    size = max(1, round(GROUP_SHARE * len(ranked)))
    upper = {a.id for a in ranked[:size]}
    lower = {a.id for a in ranked[-size:]}
    enough = len(ranked) >= MIN_FOR_DISCRIMINATION

    by_question: dict = {}
    for attempt in attempts:
        for row in papers[attempt.id]:
            entry = by_question.setdefault(row["question"].id, {"question": row["question"], "rows": []})
            entry["rows"].append({**row, "attempt_id": attempt.id})

    items, topic_rows = [], {}
    for entry in by_question.values():
        question = entry["question"]
        graded = [r for r in entry["rows"] if r["earned"] is not None]
        difficulty = _share(graded)
        discrimination = None
        if enough:
            high = _share([r for r in graded if r["attempt_id"] in upper])
            low = _share([r for r in graded if r["attempt_id"] in lower])
            if high is not None and low is not None:
                discrimination = round(high - low, 3)
        options = None
        if question.type in CHOICE_TYPES:
            choices = ["true", "false"] if question.type == "true_false" else [str(o) for o in (question.options or [])]
            key = set(_picked(question.correct_answers))
            counts = {choice: 0 for choice in choices}
            blank = 0
            for r in entry["rows"]:
                picked = _picked(answers.get((r["attempt_id"], question.id)))
                blank += not picked
                for choice in picked:
                    if choice in counts:
                        counts[choice] += 1
            options = {"choices": [{"option": c, "count": n, "correct": c in key} for c, n in counts.items()], "blank": blank}
        items.append({
            "question_id": str(question.id),
            "title": question.title,
            "type": question.type,
            "tags": question.tags or [],
            "worth": entry["rows"][0]["worth"],
            "papers": len(entry["rows"]),
            "answered": sum(1 for r in entry["rows"] if r["answered"]),
            "waiting": len(entry["rows"]) - len(graded),  # written answers nobody has graded yet
            "difficulty": difficulty,
            "discrimination": discrimination,
            "flags": _flags(difficulty, discrimination),
            "options": options,
        })
        for tag in question.tags or [None]:
            topic_rows.setdefault(tag, {"questions": set(), "rows": []})
            topic_rows[tag]["questions"].add(question.id)
            topic_rows[tag]["rows"].extend(graded)

    topics = sorted(
        ({"tag": tag, "questions": len(t["questions"]), "difficulty": _share(t["rows"])} for tag, t in topic_rows.items()),
        key=lambda t: (t["tag"] is None, t["difficulty"] if t["difficulty"] is not None else 2, t["tag"] or ""),
    )
    shares = [totals[a.id] for a in attempts]
    distribution = [0] * 10
    for share in shares:
        distribution[min(9, int(share * 10))] += 1
    return {
        "exam": {"id": str(exam.id), "title": exam.title},
        "submitted": len(attempts),
        "discrimination_needs": MIN_FOR_DISCRIMINATION,
        "summary": {
            "mean": round(statistics.mean(shares), 3) if shares else None,
            "median": round(statistics.median(shares), 3) if shares else None,
            "highest": round(max(shares), 3) if shares else None,
            "lowest": round(min(shares), 3) if shares else None,
        },
        "distribution": distribution,  # attempts per 10 % band of their score, 0-9 % first
        "items": items,
        "topics": topics,
    }
