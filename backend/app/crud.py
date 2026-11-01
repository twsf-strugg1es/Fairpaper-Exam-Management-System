from sqlalchemy import String, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, object_session
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from . import models, schemas
from .security import get_password_hash

logger = logging.getLogger(__name__)


def get_user_by_email(db: Session, email: str) -> models.User | None:
    """Find a user by email address, ignoring case (Arif@Mail.com is arif@mail.com)."""
    return db.query(models.User).filter(func.lower(models.User.email) == email.strip().lower()).first()


def create_user(db: Session, user: schemas.UserCreate, commit: bool = True) -> models.User:
    """Create a new user with hashed password."""
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        date_of_birth=user.date_of_birth,
        gender=user.gender,
    )
    db.add(db_user)
    if commit:
        db.commit()
        db.refresh(db_user)
    else:
        db.flush()
    return db_user


def create_organization(
    db: Session, name: str, owner: models.User, locale: schemas.LocaleFields | None = None
) -> models.Organization:
    """Create an organization with `owner` as its first member."""
    org = models.Organization(name=name)
    if locale:
        for field in schemas.LocaleFields.model_fields:
            if getattr(locale, field) is not None:
                setattr(org, field, getattr(locale, field))
    db.add(org)
    db.flush()
    db.add(models.Membership(user_id=owner.id, organization_id=org.id, role=models.ROLE_OWNER))
    db.commit()
    db.refresh(org)
    return org


def membership_out(membership: models.Membership) -> schemas.MembershipOut:
    org = membership.organization
    return schemas.MembershipOut(
        organization_id=membership.organization_id,
        organization_name=org.name,
        role=membership.role,
        timezone=org.timezone or models.DEFAULT_TIMEZONE,
        default_language=org.default_language or models.DEFAULT_LANGUAGE,
    )


def get_membership(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> models.Membership | None:
    return (
        db.query(models.Membership)
        .filter(models.Membership.user_id == user_id, models.Membership.organization_id == organization_id)
        .first()
    )


def find_join_code(
    db: Session, code: str
) -> tuple[models.Organization, models.Group | None] | None:
    """Resolve a join code to its organization, plus the group when it's a group's code."""
    code = code.strip().upper()
    group = db.query(models.Group).filter(models.Group.join_code == code).first()
    if group:
        return group.organization, group
    org = db.query(models.Organization).filter(models.Organization.join_code == code).first()
    return (org, None) if org else None


def join_with_code(db: Session, user: models.User, code: str) -> models.Membership:
    """Join an organization as a candidate using its join code or one of its groups' codes.

    A group code also adds the candidate to that group. Joining again with another
    group's code adds the group to the existing membership.
    """
    found = find_join_code(db, code)
    if not found:
        raise ValueError("Invalid join code")
    org, group = found

    membership = get_membership(db, user.id, org.id)
    if not membership:
        membership = models.Membership(user_id=user.id, organization_id=org.id, role=models.ROLE_CANDIDATE)
        db.add(membership)
    if group and group not in membership.groups:
        if membership.role != models.ROLE_CANDIDATE:
            raise ValueError("Staff members can't join a candidate group")
        membership.groups.append(group)
    db.commit()
    db.refresh(membership)
    return membership


def visible_to_candidate(exam: models.Exam, membership: models.Membership) -> bool:
    """Whether a candidate may see and take an exam: same organization, and in one of its groups if it has any."""
    if exam.organization_id != membership.organization_id:
        return False
    if not exam.groups:
        return True
    return bool({g.id for g in exam.groups} & {g.id for g in membership.groups})


def get_question_by_id(db: Session, question_id: uuid.UUID) -> models.Question | None:
    """Find a question by ID."""
    return db.query(models.Question).filter(models.Question.id == question_id).first()


MAX_TAGS = 20
MAX_TAG_LENGTH = 40


def normalize_tags(raw) -> list[str]:
    """Tags as the teacher wrote them: lower-cased, trimmed, without a leading '#', no repeats.

    Accepts "Physics, Waves" or a list. Quotes and backslashes are dropped so a tag can
    always be matched inside the stored JSON.
    """
    if raw is None:
        return []
    items = raw.split(",") if isinstance(raw, str) else [str(item) for item in raw if item is not None]
    tags: list[str] = []
    for item in items:
        tag = " ".join(item.replace('"', "").replace("\\", "").strip().lstrip("#").split()).lower()
        if tag and tag not in tags:
            tags.append(tag[:MAX_TAG_LENGTH])
    return tags[:MAX_TAGS]


def create_question(db: Session, question: schemas.QuestionBase, organization_id: uuid.UUID) -> models.Question:
    """Create a new question in an organization's question bank."""
    db_q = models.Question(
        organization_id=organization_id,
        title=question.title,
        description=question.description,
        complexity=question.complexity,
        type=question.type,
        options=question.options,
        correct_answers=question.correct_answers,
        max_score=question.max_score,
        tags=normalize_tags(question.tags),
    )
    db.add(db_q)
    db.commit()
    db.refresh(db_q)
    return db_q


def final_score(db: Session, attempt: models.ExamAttempt) -> float:
    """Auto-graded score plus the marks staff awarded to written and image answers, capped at the total."""
    manual = (
        db.query(func.coalesce(func.sum(models.Evaluation.score_awarded), 0))
        .join(models.Answer, models.Answer.id == models.Evaluation.answer_id)
        .join(models.Question, models.Question.id == models.Answer.question_id)
        .filter(models.Answer.attempt_id == attempt.id, models.Question.type.in_(("text", "image_upload")))
        .scalar()
    )
    return min(float(attempt.score or 0) + float(manual or 0), float(attempt.total_possible_score or 0))


def merit_list(db: Session, exam: models.Exam) -> list[dict]:
    """Submitted attempts ranked by final score (higher first), then time taken (shorter first).
    Candidates level on both share a rank, and the next rank skips (1, 2, 2, 4)."""
    attempts = (
        db.query(models.ExamAttempt)
        .options(joinedload(models.ExamAttempt.student))
        .filter(models.ExamAttempt.exam_id == exam.id, models.ExamAttempt.end_time.isnot(None))
        .all()
    )
    rows = []
    for attempt in attempts:
        seconds = int((as_utc(attempt.end_time) - as_utc(attempt.start_time)).total_seconds())
        rows.append({"attempt": attempt, "score": final_score(db, attempt), "seconds": max(0, seconds)})
    rows.sort(key=lambda r: (-r["score"], r["seconds"]))
    ranked, previous = [], None
    for i, row in enumerate(rows):
        key = (row["score"], row["seconds"])
        rank = ranked[-1]["rank"] if previous == key else i + 1
        ranked.append({**row, "rank": rank})
        previous = key
    for row in ranked:
        row["tied"] = sum(r["rank"] == row["rank"] for r in ranked) > 1
    return ranked


def results_visible(exam: models.Exam, now: datetime | None = None) -> bool:
    """Whether students may see their scores (and later the answer key) for this exam yet."""
    if exam.results_release == models.RESULTS_IMMEDIATE or exam.results_released_at is not None:
        return True
    if exam.results_release == models.RESULTS_ON_CLOSE:
        return (now or datetime.now(timezone.utc)) > as_utc(exam.end_time)
    return False


def exam_marks(exam: models.Exam) -> dict[uuid.UUID, int]:
    """What each question is worth in this exam: its per-exam override, else its own max_score."""
    db = object_session(exam)
    overrides = dict(
        db.query(models.exam_questions.c.question_id, models.exam_questions.c.marks)
        .filter(models.exam_questions.c.exam_id == exam.id, models.exam_questions.c.marks.isnot(None))
        .all()
    ) if db is not None else {}
    return {q.id: overrides.get(q.id, q.max_score) for q in exam.questions}


def exam_question_count(exam: models.Exam) -> int:
    """How many questions each student gets: the fixed ones plus everything the pool rules draw."""
    return len(exam.questions or []) + sum(rule.count for rule in exam.pool_rules)


def exam_total_marks(exam: models.Exam) -> int:
    """The total every student's paper adds up to (pool rules give each drawn question a fixed mark)."""
    return sum(exam_marks(exam).values()) + sum(rule.count * rule.marks for rule in exam.pool_rules)


def papers(db: Session, exam: models.Exam, attempts: list[models.ExamAttempt]) -> dict[uuid.UUID, list[tuple]]:
    """Each attempt's questions in a stable order, each with what it's worth: the paper drawn and stored when
    the attempt started (exams with pool rules), else the exam's own questions at their exam marks."""
    stored = (
        db.query(models.AttemptQuestion)
        .options(joinedload(models.AttemptQuestion.question))
        .filter(models.AttemptQuestion.attempt_id.in_([a.id for a in attempts]))
        .order_by(models.AttemptQuestion.attempt_id, models.AttemptQuestion.position)
        .all()
    ) if attempts else []
    drawn: dict[uuid.UUID, list[tuple]] = {}
    for row in stored:
        drawn.setdefault(row.attempt_id, []).append((row.question, float(row.marks)))
    marks = exam_marks(exam)
    fixed = [(q, float(marks[q.id] or 0)) for q in exam.questions]
    return {attempt.id: drawn.get(attempt.id, fixed) for attempt in attempts}


def attempt_questions(db: Session, exam: models.Exam, attempt: models.ExamAttempt) -> list[tuple]:
    return list(papers(db, exam, [attempt])[attempt.id])


def pool_candidates(db: Session, organization_id: uuid.UUID, complexity: str | None, tag: str | None) -> list[uuid.UUID]:
    """IDs of the bank's live questions a pool rule may draw from."""
    query = db.query(models.Question.id).filter(
        models.Question.organization_id == organization_id, models.Question.archived_at.is_(None)
    )
    if complexity:
        query = query.filter(models.Question.complexity == complexity)
    if tag:
        # Same match as the question bank's tag filter: the quoted tag inside the stored JSON text
        query = query.filter(cast(models.Question.tags, String).contains(json.dumps(tag), autoescape=True))
    return [row[0] for row in query.all()]


def describe_rule(rule) -> str:
    parts = [f"{rule.count} random", rule.complexity, "question" if rule.count == 1 else "questions"]
    text = " ".join(p for p in parts if p)
    return f'{text} tagged "{rule.tag}"' if rule.tag else text


def pool_shortfall(db: Session, organization_id: uuid.UUID, fixed_ids, rules) -> str | None:
    """Why the bank can't fill these pool rules, or None when it can. Questions already in the exam don't count."""
    fixed = set(fixed_ids)
    reachable: set[uuid.UUID] = set()
    for rule in rules:
        ids = set(pool_candidates(db, organization_id, rule.complexity, rule.tag)) - fixed
        reachable |= ids
        if len(ids) < rule.count:
            return f'Only {len(ids)} questions in the bank match "{describe_rule(rule)}".'
    if len(reachable) < sum(rule.count for rule in rules):
        return "The pool rules overlap: together they need more different questions than the bank has for them."
    return None


def draw_pool_questions(db: Session, exam: models.Exam, attempt: models.ExamAttempt) -> None:
    """Draw an attempt's random questions, once, and store its whole paper (fixed questions first, then each
    rule's draw). Later calls (a reload, a resume, a second "start") keep what was drawn (PRD AC18)."""
    if not exam.pool_rules:
        return
    if db.query(models.AttemptQuestion.attempt_id).filter(models.AttemptQuestion.attempt_id == attempt.id).first():
        return
    marks = exam_marks(exam)
    paper = [(q.id, marks[q.id]) for q in exam.questions]
    taken = {question_id for question_id, _ in paper}
    rng = random.Random(f"{attempt.id}:pool")
    for rule in exam.pool_rules:
        pool = sorted((qid for qid in pool_candidates(db, exam.organization_id, rule.complexity, rule.tag) if qid not in taken), key=str)
        picked = rng.sample(pool, min(rule.count, len(pool)))
        if len(picked) < rule.count:
            logger.warning("A pool rule drew fewer questions than it asks for", extra={"fields": {
                "exam_id": str(exam.id), "rule_id": str(rule.id), "wanted": rule.count, "drawn": len(picked)}})
        paper.extend((question_id, rule.marks) for question_id in picked)
        taken.update(picked)
    for position, (question_id, worth) in enumerate(paper):
        db.add(models.AttemptQuestion(attempt_id=attempt.id, question_id=question_id, position=position, marks=worth))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # a parallel request stored this attempt's paper first; the seed makes it the same draw


def _set_pool_rules(exam: models.Exam, rules) -> None:
    exam.pool_rules = [
        models.ExamPoolRule(position=i, count=rule.count, complexity=rule.complexity, tag=rule.tag, marks=rule.marks)
        for i, rule in enumerate(rules)
    ]


def _apply_question_marks(db: Session, exam: models.Exam, marks: dict[uuid.UUID, int]) -> None:
    """Store the per-exam marks (after the exam's questions are attached and flushed)."""
    db.flush()
    for question in exam.questions:
        override = marks.get(question.id)
        db.execute(
            models.exam_questions.update()
            .where(models.exam_questions.c.exam_id == exam.id, models.exam_questions.c.question_id == question.id)
            .values(marks=override if override != question.max_score else None)
        )


def create_exam(db: Session, exam: schemas.ExamCreate, organization_id: uuid.UUID) -> models.Exam:
    """Create a new exam with associated questions and target groups."""
    db_exam = models.Exam(
        organization_id=organization_id,
        title=exam.title,
        start_time=exam.start_time,
        end_time=exam.end_time,
        duration_minutes=exam.duration_minutes,
        is_published=False,
        shuffle_questions=exam.shuffle_questions,
        shuffle_options=exam.shuffle_options,
        require_fullscreen=exam.require_fullscreen,
        block_copy_paste=exam.block_copy_paste,
        max_violations=exam.max_violations,
        results_release=exam.results_release,
        show_rank=exam.show_rank,
    )
    if exam.group_ids:
        db_exam.groups = db.query(models.Group).filter(models.Group.id.in_(exam.group_ids)).all()
    
    # Attach questions to the exam
    for question_id in exam.question_ids:
        question = get_question_by_id(db, question_id)
        if question:
            db_exam.questions.append(question)
    
    _set_pool_rules(db_exam, exam.pool_rules)
    db.add(db_exam)
    _apply_question_marks(db, db_exam, exam.question_marks)
    db.commit()
    db.refresh(db_exam)
    return db_exam


# Why an exam can't be edited (shown to staff, translated on the client)
EXAM_ARCHIVED = "This exam is archived."
EXAM_STARTED = "Students have already started this exam, so it can't be changed."
EXAM_OPEN = "This exam is already open. Unpublish it before changing it."


def exam_edit_blocker(db: Session, exam: models.Exam, now: datetime | None = None) -> str | None:
    """Why this exam can't be edited any more, or None while it still can be: a draft, or
    published but not open yet, and nobody has started it."""
    now = now or datetime.now(timezone.utc)
    if exam.archived_at is not None:
        return EXAM_ARCHIVED
    if db.query(models.ExamAttempt.id).filter(models.ExamAttempt.exam_id == exam.id).first():
        return EXAM_STARTED
    if exam.is_published and as_utc(exam.start_time) <= now:
        return EXAM_OPEN
    return None


def update_exam(db: Session, exam: models.Exam, data: schemas.ExamCreate) -> models.Exam:
    """Replace an exam's details, questions and groups (callers check exam_edit_blocker first)."""
    for field in ("title", "start_time", "end_time", "duration_minutes", "shuffle_questions",
                  "shuffle_options", "require_fullscreen", "block_copy_paste", "max_violations", "results_release", "show_rank"):
        setattr(exam, field, getattr(data, field))
    exam.questions = db.query(models.Question).filter(models.Question.id.in_(data.question_ids)).all()
    exam.groups = db.query(models.Group).filter(models.Group.id.in_(data.group_ids)).all() if data.group_ids else []
    _set_pool_rules(exam, data.pool_rules)
    _apply_question_marks(db, exam, data.question_marks)
    db.commit()
    db.refresh(exam)
    return exam


def get_exams(db: Session, organization_id: uuid.UUID) -> list[models.Exam]:
    """Get all of an organization's exams."""
    return (
        db.query(models.Exam)
        .filter(models.Exam.organization_id == organization_id, models.Exam.archived_at.is_(None))
        .all()
    )


QUESTION_LOCKED = "Students have already taken an exam with this question, so changing it would change their results. Duplicate it to make a new version."


def question_edit_blocker(db: Session, question: models.Question) -> str | None:
    """A question locks once any student has started an exam that contains it: editing it then
    would change what they saw or how they're graded. A copy can be edited instead."""
    started = (
        db.query(models.ExamAttempt.id)
        .join(models.exam_questions, models.exam_questions.c.exam_id == models.ExamAttempt.exam_id)
        .filter(models.exam_questions.c.question_id == question.id)
        .first()
    )
    answered = db.query(models.Answer.id).filter(models.Answer.question_id == question.id).first()
    return QUESTION_LOCKED if started or answered else None


def save_question(db: Session, question: models.Question, data: schemas.QuestionEdit) -> models.Question:
    for field in ("title", "description", "complexity", "type", "options", "correct_answers", "max_score"):
        setattr(question, field, getattr(data, field))
    question.tags = normalize_tags(data.tags)
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def question_in_use(db: Session, question_id: uuid.UUID) -> bool:
    """Whether deleting the question would erase part of an exam or a student's answer."""
    answered = db.query(models.Answer.id).filter(models.Answer.question_id == question_id).first()
    in_exam = db.query(models.exam_questions.c.exam_id).filter(models.exam_questions.c.question_id == question_id).first()
    drawn = db.query(models.AttemptQuestion.attempt_id).filter(models.AttemptQuestion.question_id == question_id).first()
    return bool(answered or in_exam or drawn)


def remove_question(db: Session, question: models.Question) -> str:
    """Delete an unused question; archive one that exams or answers refer to. Returns what happened."""
    if question_in_use(db, question.id):
        question.archived_at = datetime.now(timezone.utc)
        db.commit()
        return "archived"
    db.delete(question)
    db.commit()
    return "deleted"


def remove_exam(db: Session, exam: models.Exam) -> str:
    """Delete an exam nobody has started; archive (and unpublish) one with attempts. Returns what happened."""
    started = db.query(models.ExamAttempt.id).filter(models.ExamAttempt.exam_id == exam.id).first()
    if started:
        exam.archived_at = datetime.now(timezone.utc)
        exam.is_published = False
        db.commit()
        return "archived"
    db.delete(exam)
    db.commit()
    return "deleted"


def get_exam_by_id(db: Session, exam_id: uuid.UUID) -> models.Exam | None:
    """Find an exam by ID."""
    return (
        db.query(models.Exam)
        .options(joinedload(models.Exam.questions))
        .filter(models.Exam.id == exam_id)
        .first()
    )


def get_available_exams(db: Session, membership: models.Membership) -> list[models.Exam]:
    """Get the published exams a candidate may take."""
    exams = (
        db.query(models.Exam)
        .options(joinedload(models.Exam.questions), joinedload(models.Exam.groups))
        .filter(
            models.Exam.is_published == True,
            models.Exam.organization_id == membership.organization_id,
            models.Exam.archived_at.is_(None),
        )
        .all()
    )
    return [exam for exam in exams if visible_to_candidate(exam, membership)]


# Extra time allowed after an attempt's deadline for answers that were
# in flight when the clock ran out (network latency, slow connections).
ANSWER_GRACE_SECONDS = 30


def as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes (e.g. from SQLite) as UTC so they compare with aware ones."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    """A time as the API sends it: ISO 8601 in UTC with its offset; None stays None."""
    return as_utc(dt).isoformat() if dt else None


def get_attempt_deadline(attempt: models.ExamAttempt, exam: models.Exam) -> datetime:
    """When an attempt must finish: its own duration, but never past the exam window."""
    personal_deadline = as_utc(attempt.start_time) + timedelta(minutes=exam.duration_minutes)
    return min(personal_deadline, as_utc(exam.end_time))


def create_exam_attempt(
    db: Session, exam_id: uuid.UUID, student_id: uuid.UUID
) -> models.ExamAttempt:
    """Create a student's attempt at an exam, or return the one they already have.

    Two "start" requests can arrive together (a double click, a retried request); the
    database's one-attempt-per-exam constraint makes the second one reuse the first.
    """
    attempt = models.ExamAttempt(
        exam_id=exam_id,
        student_id=student_id,
        start_time=datetime.now(timezone.utc),  # type: ignore
    )
    db.add(attempt)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return (
            db.query(models.ExamAttempt)
            .filter(models.ExamAttempt.exam_id == exam_id, models.ExamAttempt.student_id == student_id)
            .one()
        )
    db.refresh(attempt)
    return attempt


def save_answer(
    db: Session,
    attempt_id: uuid.UUID,
    student_id: uuid.UUID,
    answer_in: schemas.AnswerCreate,
) -> bool:
    """Save or update a student's answer with security verification. Returns False when the
    save was older (by `client_seq`) than the answer already stored, and so was ignored."""
    # Verify the attempt belongs to the student
    attempt = (
        db.query(models.ExamAttempt)
        .filter(
            models.ExamAttempt.id == attempt_id,
            models.ExamAttempt.student_id == student_id,
        )
        .first()
    )
    if not attempt:
        raise ValueError("Attempt not found or does not belong to student")

    if attempt.end_time is not None:
        raise ValueError("Exam already submitted")

    exam = get_exam_by_id(db, attempt.exam_id)
    if not exam:
        raise ValueError("Exam not found")

    deadline = get_attempt_deadline(attempt, exam)
    if datetime.now(timezone.utc) > deadline + timedelta(seconds=ANSWER_GRACE_SECONDS):
        raise ValueError("Exam time is over. Answers can no longer be changed")

    if answer_in.question_id not in {q.id for q, _ in attempt_questions(db, exam, attempt)}:
        raise ValueError("Question does not belong to this exam")

    def existing() -> models.Answer | None:
        return (
            db.query(models.Answer)
            .filter(models.Answer.attempt_id == attempt_id, models.Answer.question_id == answer_in.question_id)
            .first()
        )

    def overwrite() -> bool:
        # One conditional UPDATE, so two saves racing can't let the older one win
        query = db.query(models.Answer).filter(
            models.Answer.attempt_id == attempt_id, models.Answer.question_id == answer_in.question_id
        )
        if answer_in.client_seq is not None:
            query = query.filter(or_(models.Answer.client_seq.is_(None), models.Answer.client_seq < answer_in.client_seq))
        changed = query.update(
            {models.Answer.answer_data: answer_in.answer_data, models.Answer.client_seq: answer_in.client_seq},
            synchronize_session=False,
        )
        db.commit()
        return changed > 0

    if existing() is None:
        db.add(models.Answer(
            attempt_id=attempt_id, question_id=answer_in.question_id,
            answer_data=answer_in.answer_data, client_seq=answer_in.client_seq,
        ))
        try:
            db.commit()
            return True
        except IntegrityError:
            # Another save (a second tab, a retried request) inserted it first
            db.rollback()
    return overwrite()


def question_points(question: models.Question, answer_data, worth: float) -> float | None:
    """What an answer earns on an auto-graded question: all its marks or none. Grading compares option values,
    never positions. None for written and image answers, which staff grade."""
    if question.type not in ("single_choice", "multi_choice"):
        return None
    if answer_data is None:
        return 0.0
    def norm(value):
        return sorted(str(v) for v in value) if isinstance(value, list) else [str(value)]

    return float(worth) if norm(question.correct_answers) == norm(answer_data) else 0.0


def breakdowns(db: Session, exam: models.Exam, attempts: list[models.ExamAttempt]) -> dict[uuid.UUID, list[dict]]:
    """Per attempt, question by question in its paper's order: what it's worth and what the attempt earned.
    `earned` is None for a written or image answer nobody has graded yet. Two queries for any number of attempts."""
    if not attempts:
        return {}
    paper_of = papers(db, exam, attempts)
    answers = db.query(models.Answer).filter(models.Answer.attempt_id.in_([a.id for a in attempts])).all()
    graded = dict(
        db.query(models.Evaluation.answer_id, models.Evaluation.score_awarded)
        .filter(models.Evaluation.answer_id.in_([a.id for a in answers]), models.Evaluation.score_awarded.isnot(None))
        .all()
    ) if answers else {}
    by_attempt: dict[uuid.UUID, dict[uuid.UUID, models.Answer]] = {}
    for answer in answers:
        by_attempt.setdefault(answer.attempt_id, {})[answer.question_id] = answer
    result = {}
    for attempt in attempts:
        given = by_attempt.get(attempt.id, {})
        rows = []
        for question, worth in paper_of[attempt.id]:
            answer = given.get(question.id)
            earned = question_points(question, answer.answer_data if answer else None, worth)
            if earned is None:  # written or image: staff's mark, 0 if left blank, None while waiting to be graded
                earned = float(graded[answer.id]) if answer and answer.id in graded else (None if answer else 0.0)
            rows.append({"question": question, "worth": worth, "earned": earned, "answered": answer is not None})
        result[attempt.id] = rows
    return result


def finish_attempt(
    db: Session, attempt: models.ExamAttempt, reason: str = models.SUBMIT_STUDENT, ended_at: datetime | None = None
) -> bool:
    """Close an attempt and auto-grade it. Returns False when something else closed it first
    (a second tab, a retried request, the abandoned-attempt job): it's scored exactly once."""
    exam = db.query(models.Exam).filter(models.Exam.id == attempt.exam_id).first()
    if not exam:
        raise ValueError("Exam not found")
    ended_at = ended_at or datetime.now(timezone.utc)

    # Claim it atomically; on PostgreSQL the row stays locked until the commit below
    claimed = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.id == attempt.id, models.ExamAttempt.end_time.is_(None))
        .update({models.ExamAttempt.end_time: ended_at}, synchronize_session=False)
    )
    if not claimed:
        db.rollback()
        db.refresh(attempt)
        return False

    # Get all answers for this attempt
    answers = (
        db.query(models.Answer).filter(models.Answer.attempt_id == attempt.id).all()
    )
    answer_map = {ans.question_id: ans.answer_data for ans in answers}

    # Calculate scores on this attempt's own paper (fixed questions, plus any it drew from pools)
    total_score = 0.0
    total_possible = 0.0
    for question, worth in attempt_questions(db, exam, attempt):
        total_possible += worth
        total_score += question_points(question, answer_map.get(question.id), worth) or 0.0

    attempt.score = float(total_score)  # type: ignore
    attempt.total_possible_score = float(total_possible)  # type: ignore
    attempt.end_time = ended_at  # type: ignore
    attempt.submit_reason = reason  # type: ignore
    db.commit()
    db.refresh(attempt)
    return True


def calculate_and_save_score(
    db: Session, attempt: models.ExamAttempt, reason: str = models.SUBMIT_STUDENT, ended_at: datetime | None = None
) -> models.ExamAttempt:
    """Close and grade an attempt; if it was already closed, return it as it was saved."""
    finish_attempt(db, attempt, reason, ended_at)
    return attempt


def create_or_update_evaluation(
    db: Session,
    answer_id: uuid.UUID,
    evaluator_id: uuid.UUID,
    eval_data: schemas.EvaluationCreate,
) -> models.Evaluation:
    """Create or update an evaluation for a student answer."""
    # Check if evaluation exists
    existing = (
        db.query(models.Evaluation)
        .filter(models.Evaluation.answer_id == answer_id)
        .first()
    )

    if existing:
        # Update existing evaluation
        if eval_data.is_correct is not None:
            existing.is_correct = eval_data.is_correct
        if eval_data.comment is not None:
            existing.comment = eval_data.comment[:100]  # Ensure max 100 chars
        if eval_data.score_awarded is not None:
            existing.score_awarded = eval_data.score_awarded
        existing.updated_at = datetime.now(timezone.utc)  # type: ignore
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new evaluation
        new_eval = models.Evaluation(
            answer_id=answer_id,
            evaluated_by=evaluator_id,
            is_correct=eval_data.is_correct,
            comment=eval_data.comment[:100] if eval_data.comment else None,
            score_awarded=eval_data.score_awarded,
            created_at=datetime.now(timezone.utc),  # type: ignore
            updated_at=datetime.now(timezone.utc),  # type: ignore
        )
        db.add(new_eval)
        db.commit()
        db.refresh(new_eval)
        return new_eval


def get_evaluation_by_answer(db: Session, answer_id: uuid.UUID) -> models.Evaluation | None:
    """Get evaluation for a specific answer."""
    return (
        db.query(models.Evaluation)
        .filter(models.Evaluation.answer_id == answer_id)
        .first()
    )


# --- Integrity ---

def questions_for_attempt(db: Session, exam: models.Exam, attempt: models.ExamAttempt) -> list[dict]:
    """The attempt's questions as this student sees them, without answers.

    Shuffling is seeded with the attempt's ID: every student gets their own order,
    and it stays the same when they reload or resume.
    """
    paper = attempt_questions(db, exam, attempt)
    if exam.shuffle_questions:
        paper.sort(key=lambda item: str(item[0].id))  # a fixed starting point, so the seed alone decides the order
        random.Random(f"{attempt.id}:questions").shuffle(paper)

    result = []
    for q, worth in paper:
        options = list(q.options) if isinstance(q.options, list) else q.options
        # Answers are stored as option values, not positions, so shuffling never affects grading
        if exam.shuffle_options and isinstance(options, list):
            random.Random(f"{attempt.id}:{q.id}").shuffle(options)
        result.append({
            "id": str(q.id),
            "title": q.title,
            "type": q.type,
            "complexity": q.complexity,
            "max_score": int(worth),
            "options": options,
        })
    return result


def integrity_settings(exam: models.Exam) -> dict:
    return {
        "shuffle_questions": exam.shuffle_questions,
        "shuffle_options": exam.shuffle_options,
        "require_fullscreen": exam.require_fullscreen,
        "block_copy_paste": exam.block_copy_paste,
        "max_violations": exam.max_violations,
    }


def count_violations(db: Session, attempt_id: uuid.UUID) -> int:
    return (
        db.query(models.IntegrityEvent)
        .filter(
            models.IntegrityEvent.attempt_id == attempt_id,
            models.IntegrityEvent.type.in_(models.VIOLATION_EVENTS),
        )
        .count()
    )


def record_integrity_events(
    db: Session, attempt: models.ExamAttempt, events: list[schemas.IntegrityEventIn]
) -> int:
    """Store events from the exam page and return the attempt's violation count.

    Once the count reaches the exam's limit, the attempt is submitted on the spot.
    """
    for event in events:
        db.add(models.IntegrityEvent(
            attempt_id=attempt.id,
            type=event.type,
            occurred_at=event.occurred_at,
            details=event.details,
        ))
    db.commit()

    violations = count_violations(db, attempt.id)
    limit = attempt.exam.max_violations
    if limit and violations >= limit and attempt.end_time is None:
        calculate_and_save_score(db, attempt, reason=models.SUBMIT_VIOLATIONS)
    return violations


def integrity_summary(attempt: models.ExamAttempt) -> dict:
    """Counts and an overall risk level, so examiners know which attempts to look at first.

    - high: auto-submitted for violations, 3+ violations, or a minute or more away from the exam
    - review: any violation or flag
    - clean: nothing recorded
    """
    events = attempt.integrity_events
    counts = {event_type: 0 for event_type in models.EVENT_TYPES}
    seconds_away = 0.0
    for event in events:
        counts[event.type] = counts.get(event.type, 0) + 1
        if event.type == models.EVENT_FOCUS_RETURNED:
            seconds_away += float((event.details or {}).get("away_ms") or 0) / 1000

    violations = sum(counts[t] for t in models.VIOLATION_EVENTS)
    flags = sum(counts[t] for t in models.FLAG_EVENTS)
    if attempt.submit_reason == models.SUBMIT_VIOLATIONS or violations >= 3 or seconds_away >= 60:
        risk = "high"
    elif violations or flags:
        risk = "review"
    else:
        risk = "clean"
    return {
        "risk": risk,
        "violations": violations,
        "flags": flags,
        "seconds_away": round(seconds_away),
        "counts": counts,
    }
