from sqlalchemy import String, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, object_session
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from . import models, question_types, schemas
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
        default_time_limit_seconds=question.default_time_limit_seconds,
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
        .filter(models.Answer.attempt_id == attempt.id, models.Question.type.in_(models.MANUAL_TYPES))
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
    fixed_sections = exam_question_sections(db, exam)
    paper = [(q.id, marks[q.id], fixed_sections.get(q.id)) for q in exam.questions]
    taken = {question_id for question_id, _, _ in paper}
    rng = random.Random(f"{attempt.id}:pool")
    for rule in exam.pool_rules:
        pool = sorted((qid for qid in pool_candidates(db, exam.organization_id, rule.complexity, rule.tag) if qid not in taken), key=str)
        picked = rng.sample(pool, min(rule.count, len(pool)))
        if len(picked) < rule.count:
            logger.warning("A pool rule drew fewer questions than it asks for", extra={"fields": {
                "exam_id": str(exam.id), "rule_id": str(rule.id), "wanted": rule.count, "drawn": len(picked)}})
        paper.extend((question_id, rule.marks, rule.section_id) for question_id in picked)
        taken.update(picked)
    for position, (question_id, worth, section_id) in enumerate(paper):
        db.add(models.AttemptQuestion(attempt_id=attempt.id, question_id=question_id, position=position, marks=worth,
                                      section_id=section_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # a parallel request stored this attempt's paper first; the seed makes it the same draw


def _set_sections_and_rules(exam: models.Exam, data: schemas.ExamCreate) -> None:
    exam.sections = [
        models.ExamSection(position=i, title=section.title, instructions=section.instructions,
                           time_limit_minutes=section.time_limit_minutes)
        for i, section in enumerate(data.sections)
    ]
    exam.pool_rules = [
        models.ExamPoolRule(position=i, count=rule.count, complexity=rule.complexity, tag=rule.tag, marks=rule.marks,
                            section=exam.sections[rule.section] if rule.section is not None else None)
        for i, rule in enumerate(data.pool_rules)
    ]


def _apply_question_settings(db: Session, exam: models.Exam, data: schemas.ExamCreate) -> None:
    """Store each question's marks and section for this exam (after its questions are attached and flushed)."""
    db.flush()
    position = {question_id: i for i, question_id in enumerate(data.question_ids)}
    for question in exam.questions:
        override = data.question_marks.get(question.id)
        section = data.question_sections.get(question.id)
        limit = data.question_time_limits.get(question.id)
        db.execute(
            models.exam_questions.update()
            .where(models.exam_questions.c.exam_id == exam.id, models.exam_questions.c.question_id == question.id)
            .values(marks=override if override != question.max_score else None,
                    section_id=exam.sections[section].id if section is not None else None,
                    time_limit_seconds=limit if limit != question.default_time_limit_seconds else None,
                    position=position.get(question.id))
        )


def exam_question_sections(db: Session, exam: models.Exam) -> dict[uuid.UUID, uuid.UUID]:
    """The section of each of the exam's fixed questions ({} for an exam without sections)."""
    if not exam.sections:
        return {}
    return dict(
        db.query(models.exam_questions.c.question_id, models.exam_questions.c.section_id)
        .filter(models.exam_questions.c.exam_id == exam.id, models.exam_questions.c.section_id.isnot(None))
        .all()
    )


def question_sections(db: Session, exam: models.Exam, attempt: models.ExamAttempt) -> dict[uuid.UUID, uuid.UUID]:
    """Which section each question on this attempt's paper is in: as stored with the paper (exams with pool
    rules), else as set on the exam. {} for an exam without sections."""
    if not exam.sections:
        return {}
    stored = dict(
        db.query(models.AttemptQuestion.question_id, models.AttemptQuestion.section_id)
        .filter(models.AttemptQuestion.attempt_id == attempt.id)
        .all()
    )
    return {q: s for q, s in stored.items() if s is not None} if stored else exam_question_sections(db, exam)


TIMEOUT_GRACE_SECONDS = 5  # an answer sent as a section's or question's time runs out still counts


def timed_sections(exam: models.Exam) -> bool:
    """Whether students take the exam's sections one at a time: any section has a time limit."""
    return any(section.time_limit_minutes for section in exam.sections)


def per_question(exam: models.Exam) -> bool:
    """Whether the exam shows one question at a time, each with its own limit (task 4.11b)."""
    return exam.timing_mode == models.TIMING_PER_QUESTION


def _open_in_turn(rows: dict, blocks: list[tuple], opens_at: datetime, now: datetime, make_row) -> bool:
    """Keep one block (a timed section, or a question of a per-question exam) open at a time, in order. The first
    opens at `opens_at`; a block whose time has run out closes at its deadline, and the next opens at the moment
    the one before closed, so the clock keeps running while the student is away. `blocks` are (key, seconds or
    None); missing rows are made with make_row(key, opened_at, closes_at). Returns whether anything changed."""
    changed = False
    for key, seconds in blocks:
        row = rows.get(key)
        if row is None:
            row = make_row(key, opens_at, opens_at + timedelta(seconds=seconds) if seconds else None)
            rows[key] = row
            changed = True
        if row.closed_at is None and row.closes_at is not None and as_utc(row.closes_at) <= now:
            row.closed_at = row.closes_at
            changed = True
        if row.closed_at is None:
            break  # the open block
        opens_at = as_utc(row.closed_at)
    return changed


def _timeline_rows(db: Session, model, key: str, attempt: models.ExamAttempt, blocks: list[tuple], now: datetime) -> dict:
    """The attempt's timing rows (by block key), brought up to date and stored."""
    for _ in range(2):
        rows = {getattr(r, key): r for r in db.query(model).filter(model.attempt_id == attempt.id)}

        def make_row(block, opened_at, closes_at):
            row = model(attempt_id=attempt.id, opened_at=opened_at, closes_at=closes_at, **{key: block})
            db.add(row)
            return row

        if not _open_in_turn(rows, blocks, as_utc(attempt.start_time), now, make_row):
            return rows
        try:
            db.commit()
            return rows
        except IntegrityError:
            db.rollback()  # a parallel request opened the same block first: read again
    return rows


def _state(row) -> str:
    return "upcoming" if row is None else "closed" if row.closed_at is not None else "open"


def closed_for_good(row, now: datetime) -> bool:
    """Whether answers can no longer change in this section or question: the student moved on, or its time ran
    out more than a few seconds ago (an answer sent as the time ran out still counts)."""
    if row is None or row.closed_at is None:
        return False
    timed_out = row.closes_at is not None and as_utc(row.closed_at) >= as_utc(row.closes_at)
    return not timed_out or now > as_utc(row.closed_at) + timedelta(seconds=TIMEOUT_GRACE_SECONDS)


def section_timeline(db: Session, exam: models.Exam, attempt: models.ExamAttempt, now: datetime | None = None) -> list[dict]:
    """Each section of a timed-sections exam with its state for this attempt: `closed`, `open` (at most one)
    or `upcoming`, and its `row` (models.AttemptSection) once it has opened (see _open_in_turn).
    [] for exams without timed sections."""
    if not timed_sections(exam):
        return []
    blocks = [(section.id, section.time_limit_minutes * 60 if section.time_limit_minutes else None) for section in exam.sections]
    rows = _timeline_rows(db, models.AttemptSection, "section_id", attempt, blocks, now or datetime.now(timezone.utc))
    return [{"section": section, "row": rows.get(section.id), "state": _state(rows.get(section.id))} for section in exam.sections]


def question_limits(db: Session, exam: models.Exam, attempt: models.ExamAttempt) -> dict[uuid.UUID, int | None]:
    """Seconds each question on the attempt's paper gets in a per-question exam: the exam's limit for it, else
    the question's own default (drawn questions have only that); None waits for Next."""
    overrides = dict(
        db.query(models.exam_questions.c.question_id, models.exam_questions.c.time_limit_seconds)
        .filter(models.exam_questions.c.exam_id == exam.id, models.exam_questions.c.time_limit_seconds.isnot(None))
        .all()
    )
    return {q.id: overrides.get(q.id, q.default_time_limit_seconds) for q, _ in attempt_questions(db, exam, attempt)}


def question_timeline(db: Session, exam: models.Exam, attempt: models.ExamAttempt, now: datetime | None = None) -> list[dict]:
    """Each question of a per-question exam, in this student's order, with its state (`closed`, `open`,
    `upcoming`), what it's worth, its limit and its `row` (models.AttemptQuestionTiming) once it has opened.
    [] for exams timed as a whole."""
    if not per_question(exam):
        return []
    paper = ordered_paper(db, exam, attempt)
    limits = question_limits(db, exam, attempt)
    rows = _timeline_rows(db, models.AttemptQuestionTiming, "question_id", attempt,
                          [(q.id, limits.get(q.id)) for q, _ in paper], now or datetime.now(timezone.utc))
    return [{"question": q, "worth": worth, "limit": limits.get(q.id), "row": rows.get(q.id), "state": _state(rows.get(q.id))}
            for q, worth in paper]


def next_question(db: Session, exam: models.Exam, attempt: models.ExamAttempt, question_id: uuid.UUID,
                  now: datetime | None = None) -> list[dict]:
    """Lock the open question early (the student pressed Next) and open the next. Moving on from a question
    that is already closed changes nothing, so a double click can't skip one. Raises ValueError."""
    now = now or datetime.now(timezone.utc)
    timeline = question_timeline(db, exam, attempt, now)
    entry = next((e for e in timeline if e["question"].id == question_id), None)
    if entry is None:
        raise ValueError("This question isn't on your paper.")
    if entry["state"] == "upcoming":
        raise ValueError("This question hasn't opened yet.")
    if entry is timeline[-1]:
        raise ValueError("This is the last question. Submit the exam to finish.")
    if entry["state"] == "open":
        entry["row"].closed_at = now
        db.commit()
    return question_timeline(db, exam, attempt, now)


def finish_section(db: Session, exam: models.Exam, attempt: models.ExamAttempt, section_id: uuid.UUID,
                   now: datetime | None = None) -> list[dict]:
    """Close the open section early (the student pressed Finish section) and open the next. Finishing a section
    that is already closed changes nothing, so a double click can't skip one. Raises ValueError."""
    now = now or datetime.now(timezone.utc)
    timeline = section_timeline(db, exam, attempt, now)
    entry = next((e for e in timeline if e["section"].id == section_id), None)
    if entry is None:
        raise ValueError("This exam has no such section.")
    if entry["state"] == "upcoming":
        raise ValueError("This section hasn't started yet.")
    if entry is timeline[-1]:
        raise ValueError("This is the last section. Submit the exam to finish.")
    if entry["state"] == "open":
        entry["row"].closed_at = now
        db.commit()
    return section_timeline(db, exam, attempt, now)


def section_summary(db: Session, exam: models.Exam) -> list[dict]:
    """Each section's title, time and how many questions every student gets in it, for the rules screen."""
    if not exam.sections:
        return []
    counts: dict[uuid.UUID, int] = {}
    for section_id in exam_question_sections(db, exam).values():
        counts[section_id] = counts.get(section_id, 0) + 1
    for rule in exam.pool_rules:
        counts[rule.section_id] = counts.get(rule.section_id, 0) + rule.count
    return [{"title": s.title, "time_limit_minutes": s.time_limit_minutes, "question_count": counts.get(s.id, 0)}
            for s in exam.sections]


def sections_payload(db: Session, exam: models.Exam, attempt: models.ExamAttempt, timeline: list[dict],
                     deadline: datetime, now: datetime) -> list[dict]:
    """The exam's sections as the exam page shows them; for timed sections, with their state and time left."""
    of = question_sections(db, exam, attempt)
    counts: dict[uuid.UUID, int] = {}
    for section_id in of.values():
        counts[section_id] = counts.get(section_id, 0) + 1
    states = {e["section"].id: e for e in timeline}
    result = []
    for section in exam.sections:
        entry = states.get(section.id)
        row = entry["row"] if entry else None
        ends = min(as_utc(row.closes_at), deadline) if row and row.closes_at else deadline
        result.append({
            "id": str(section.id),
            "title": section.title,
            "instructions": section.instructions,
            "time_limit_minutes": section.time_limit_minutes,
            "question_count": counts.get(section.id, 0),
            "state": entry["state"] if entry else None,
            "seconds_left": max(0, int((ends - now).total_seconds())) if entry and entry["state"] == "open" else None,
        })
    return result


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
        timing_mode=exam.timing_mode,
    )
    if exam.group_ids:
        db_exam.groups = db.query(models.Group).filter(models.Group.id.in_(exam.group_ids)).all()
    
    # Attach questions to the exam
    for question_id in exam.question_ids:
        question = get_question_by_id(db, question_id)
        if question:
            db_exam.questions.append(question)
    
    _set_sections_and_rules(db_exam, exam)
    db.add(db_exam)
    _apply_question_settings(db, db_exam, exam)
    db.commit()
    db.refresh(db_exam)
    db.expire(db_exam, ["questions"])  # load them again in the stored order
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
                  "shuffle_options", "require_fullscreen", "block_copy_paste", "max_violations", "results_release", "show_rank",
                  "timing_mode"):
        setattr(exam, field, getattr(data, field))
    exam.questions = db.query(models.Question).filter(models.Question.id.in_(data.question_ids)).all()
    exam.groups = db.query(models.Group).filter(models.Group.id.in_(data.group_ids)).all() if data.group_ids else []
    _set_sections_and_rules(exam, data)
    _apply_question_settings(db, exam, data)
    db.commit()
    db.refresh(exam)
    db.expire(exam, ["questions"])  # load them again in the stored order
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
    for field in ("title", "description", "complexity", "type", "options", "correct_answers", "max_score",
                  "default_time_limit_seconds"):
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
    """When an attempt must finish: its own duration, never past the exam window, plus any extra time staff
    gave this student (task 4.11), which may run past the window's close."""
    personal_deadline = as_utc(attempt.start_time) + timedelta(minutes=exam.duration_minutes)
    return min(personal_deadline, as_utc(exam.end_time)) + timedelta(minutes=attempt.extra_minutes or 0)


def set_extra_time(db: Session, exam: models.Exam, student_id: uuid.UUID, minutes: int, staff_id: uuid.UUID,
                   now: datetime | None = None) -> dict:
    """Give a student extra minutes on an exam (task 4.11), before they start or while they write it; 0 removes
    it. An open attempt gets its new deadline at once. Raises ValueError (LookupError for an unknown student)."""
    now = now or datetime.now(timezone.utc)
    candidate = (
        db.query(models.Membership)
        .filter(models.Membership.user_id == student_id, models.Membership.organization_id == exam.organization_id,
                models.Membership.role == models.ROLE_CANDIDATE)
        .first()
    )
    if candidate is None:
        raise LookupError("Student not found")
    attempt = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.exam_id == exam.id, models.ExamAttempt.student_id == student_id)
        .first()
    )
    if attempt is not None and attempt.end_time is not None:
        raise ValueError("This student has already submitted the exam, so their time can't change.")
    if attempt is not None:
        before = attempt.extra_minutes
        attempt.extra_minutes = minutes
        if get_attempt_deadline(attempt, exam) <= now + timedelta(minutes=1):
            attempt.extra_minutes = before
            raise ValueError("That would end the student's exam right now. Give them at least as much time as they have left.")
    row = db.get(models.ExamExtraTime, (exam.id, student_id))
    if minutes == 0:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(models.ExamExtraTime(exam_id=exam.id, student_id=student_id, minutes=minutes, set_by=staff_id, updated_at=now))
    else:
        row.minutes, row.set_by, row.updated_at = minutes, staff_id, now
    db.commit()
    return extra_time_entry(db, exam, student_id, now)


def extra_time_entry(db: Session, exam: models.Exam, student_id: uuid.UUID, now: datetime | None = None) -> dict:
    """One student's extra time on an exam, with where their attempt stands and its deadline while they write."""
    now = now or datetime.now(timezone.utc)
    student = db.get(models.User, student_id)
    row = db.get(models.ExamExtraTime, (exam.id, student_id))
    attempt = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.exam_id == exam.id, models.ExamAttempt.student_id == student_id)
        .first()
    )
    state = "not_started" if attempt is None else "writing" if attempt.end_time is None else "submitted"
    return {
        "student": {"id": str(student_id), "name": (student.full_name or student.email) if student else None,
                    "email": student.email if student else None},
        "minutes": row.minutes if row else (attempt.extra_minutes if attempt else 0),
        "state": state,
        "deadline": iso(get_attempt_deadline(attempt, exam)) if state == "writing" else None,
    }


def extra_time_list(db: Session, exam: models.Exam) -> list[dict]:
    """Everyone with extra time on this exam, by name."""
    rows = db.query(models.ExamExtraTime).filter(models.ExamExtraTime.exam_id == exam.id).all()
    entries = [extra_time_entry(db, exam, row.student_id) for row in rows]
    return sorted(entries, key=lambda e: (e["student"]["name"] or "").lower())


def create_exam_attempt(
    db: Session, exam_id: uuid.UUID, student_id: uuid.UUID
) -> models.ExamAttempt:
    """Create a student's attempt at an exam, or return the one they already have.

    Two "start" requests can arrive together (a double click, a retried request); the
    database's one-attempt-per-exam constraint makes the second one reuse the first.
    """
    extra = db.get(models.ExamExtraTime, (exam_id, student_id))
    attempt = models.ExamAttempt(
        exam_id=exam_id,
        student_id=student_id,
        start_time=datetime.now(timezone.utc),  # type: ignore
        extra_minutes=extra.minutes if extra else 0,  # an accommodation set before they started
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

    now = datetime.now(timezone.utc)
    if timed_sections(exam):
        section_id = question_sections(db, exam, attempt).get(answer_in.question_id)
        entry = next((e for e in section_timeline(db, exam, attempt, now) if e["section"].id == section_id), None)
        if entry is None or entry["state"] == "upcoming":
            raise ValueError("This section hasn't started yet.")
        if closed_for_good(entry["row"], now):
            raise ValueError("This section is closed, so its answers can't change.")
    if per_question(exam):
        entry = next((e for e in question_timeline(db, exam, attempt, now) if e["question"].id == answer_in.question_id), None)
        if entry is None or entry["state"] == "upcoming":
            raise ValueError("This question hasn't opened yet.")
        if closed_for_good(entry["row"], now):
            raise ValueError("This question is closed, so its answer can't change.")

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
    """What an answer earns on an auto-graded question: all its marks or none, by the rules of its type
    (`question_types`). None for written and image answers, which staff grade."""
    return question_types.points(question, answer_data, worth)


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
            answered = answer is not None and not question_types.is_blank(answer.answer_data)
            earned = question_points(question, answer.answer_data if answer else None, worth)
            if earned is None:  # written or image: staff's mark, 0 if left blank, None while waiting to be graded
                earned = float(graded[answer.id]) if answer and answer.id in graded else (None if answered else 0.0)
            rows.append({"question": question, "worth": worth, "earned": earned, "answered": answered})
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
    for timing in (models.AttemptSection, models.AttemptQuestionTiming):
        db.query(timing).filter(timing.attempt_id == attempt.id, timing.closed_at.is_(None)).update(
            {timing.closed_at: ended_at}, synchronize_session=False
        )
    db.commit()
    db.refresh(attempt)
    return True


def calculate_and_save_score(
    db: Session, attempt: models.ExamAttempt, reason: str = models.SUBMIT_STUDENT, ended_at: datetime | None = None
) -> models.ExamAttempt:
    """Close and grade an attempt; if it was already closed, return it as it was saved."""
    finish_attempt(db, attempt, reason, ended_at)
    return attempt


def grade_answer(
    db: Session, answer: models.Answer, grader_id: uuid.UUID, grade: schemas.GradeIn
) -> models.Evaluation:
    """Record staff's mark for a written or image answer: from 0 to what the question is worth on this
    attempt's paper, to two decimals, once the student has submitted. Another grader's mark for the same
    answer is replaced, never doubled. Raises ValueError with a message for the grader."""
    attempt = db.get(models.ExamAttempt, answer.attempt_id)
    if attempt is None or attempt.end_time is None:
        raise ValueError("This answer can be graded once the student submits.")
    exam = db.get(models.Exam, attempt.exam_id)
    worth = next((w for q, w in attempt_questions(db, exam, attempt) if q.id == answer.question_id), None)
    question = db.get(models.Question, answer.question_id)
    if worth is None or question is None:
        raise ValueError("This question isn't on the student's paper.")
    if question.type not in models.MANUAL_TYPES:
        raise ValueError("This question is graded automatically.")
    score = grade.score_awarded if grade.score_awarded is not None else (worth if grade.is_correct else 0.0)
    score = round(float(score), 2)
    if score > worth:
        raise ValueError(f"Give a mark from 0 to {worth:g}.")
    values = {
        "score_awarded": score,
        "is_correct": score >= worth,
        "comment": (grade.comment or "").strip()[:100] or None,
        "evaluated_by": grader_id,
        "updated_at": datetime.now(timezone.utc),
    }
    for _ in range(2):
        existing = db.query(models.Evaluation).filter(models.Evaluation.answer_id == answer.id).first()
        if existing:
            for field, value in values.items():
                setattr(existing, field, value)
            db.commit()
            db.refresh(existing)
            return existing
        evaluation = models.Evaluation(answer_id=answer.id, **values)
        db.add(evaluation)
        try:
            db.commit()
            db.refresh(evaluation)
            return evaluation
        except IntegrityError:
            db.rollback()  # another grader saved first: overwrite theirs on the next pass
    raise ValueError("Someone else is grading this answer. Reload to see their mark.")


def _student_name(user: models.User | None) -> str:
    return (user.full_name or user.email) if user else "Unknown"


def grading_overview(db: Session, exam: models.Exam) -> dict:
    """The exam's written and image questions, each with how many submitted papers have it, how many of those
    answered it and how many of the answers are graded."""
    attempts = (
        db.query(models.ExamAttempt)
        .filter(models.ExamAttempt.exam_id == exam.id, models.ExamAttempt.end_time.isnot(None))
        .all()
    )
    paper_of = papers(db, exam, attempts)
    answers = db.query(models.Answer).filter(models.Answer.attempt_id.in_([a.id for a in attempts])).all() if attempts else []
    given = {(a.attempt_id, a.question_id): a for a in answers}
    graded = {
        answer_id for (answer_id,) in db.query(models.Evaluation.answer_id).filter(
            models.Evaluation.answer_id.in_([a.id for a in answers]), models.Evaluation.score_awarded.isnot(None)
        )
    } if answers else set()
    questions: dict[uuid.UUID, dict] = {}
    for attempt in attempts:
        for question, worth in paper_of[attempt.id]:
            if question.type not in models.MANUAL_TYPES:
                continue
            row = questions.setdefault(question.id, {
                "id": str(question.id), "title": question.title, "type": question.type, "worth": worth,
                "papers": 0, "answered": 0, "graded": 0,
            })
            row["papers"] += 1
            answer = given.get((attempt.id, question.id))
            if answer and not question_types.is_blank(answer.answer_data):
                row["answered"] += 1
                row["graded"] += answer.id in graded
    return {"exam": {"id": str(exam.id), "title": exam.title}, "submitted": len(attempts), "questions": list(questions.values())}


def grading_sheet(db: Session, exam: models.Exam, question_id: uuid.UUID) -> dict | None:
    """Every submitted answer to one written or image question, in the order students submitted, with any mark
    and comment so far. Papers where it was left blank are only counted: they earn 0 and need no grading.
    None when no submitted paper has the question."""
    attempts = (
        db.query(models.ExamAttempt)
        .options(joinedload(models.ExamAttempt.student))
        .filter(models.ExamAttempt.exam_id == exam.id, models.ExamAttempt.end_time.isnot(None))
        .order_by(models.ExamAttempt.end_time, models.ExamAttempt.id)
        .all()
    )
    paper_of = papers(db, exam, attempts)
    on_paper = [(a, w) for a in attempts for q, w in paper_of[a.id] if q.id == question_id]
    question = db.get(models.Question, question_id)
    if not on_paper or question is None or question.type not in models.MANUAL_TYPES:
        return None
    answers = {
        a.attempt_id: a for a in db.query(models.Answer).filter(
            models.Answer.question_id == question_id, models.Answer.attempt_id.in_([a.id for a, _ in on_paper])
        )
    }
    evaluations = {
        e.answer_id: e for e in db.query(models.Evaluation).options(joinedload(models.Evaluation.evaluator)).filter(
            models.Evaluation.answer_id.in_([a.id for a in answers.values()])
        )
    } if answers else {}
    rows, blank = [], 0
    for attempt, worth in on_paper:
        answer = answers.get(attempt.id)
        if answer is None or question_types.is_blank(answer.answer_data):
            blank += 1
            continue
        data = answer.answer_data
        preview = data.get("preview") if isinstance(data, dict) else None
        evaluation = evaluations.get(answer.id)
        rows.append({
            "answer_id": str(answer.id),
            "attempt_id": str(attempt.id),
            "student": {"name": _student_name(attempt.student), "email": attempt.student.email if attempt.student else None},
            "submitted_at": iso(attempt.end_time),
            "worth": worth,
            "text": data if isinstance(data, str) else (data.get("text") if isinstance(data, dict) else None),
            # The exam page stores photos inline as data: URLs; anything else is not shown
            "image": preview if isinstance(preview, str) and preview.startswith("data:image/") else None,
            "image_name": data.get("name") if isinstance(data, dict) else None,
            "score_awarded": evaluation.score_awarded if evaluation else None,
            "comment": evaluation.comment if evaluation else None,
            "graded_by": _student_name(evaluation.evaluator) if evaluation and evaluation.evaluator else None,
            "graded_at": iso(evaluation.updated_at) if evaluation else None,
        })
    return {
        "exam": {"id": str(exam.id), "title": exam.title},
        "question": {"id": str(question.id), "title": question.title, "type": question.type,
                     "notes": question.description, "worth": on_paper[0][1]},
        "answers": rows,
        "blank": blank,
    }


def get_evaluation_by_answer(db: Session, answer_id: uuid.UUID) -> models.Evaluation | None:
    """Get evaluation for a specific answer."""
    return (
        db.query(models.Evaluation)
        .filter(models.Evaluation.answer_id == answer_id)
        .first()
    )


# --- Integrity ---

def ordered_paper(db: Session, exam: models.Exam, attempt: models.ExamAttempt) -> list[tuple]:
    """The attempt's (question, worth) pairs in the order this student sees them. Shuffling is seeded with the
    attempt's ID: every student gets their own order, and it stays the same when they reload or resume.
    Questions never move between sections."""
    paper = attempt_questions(db, exam, attempt)
    if exam.shuffle_questions:
        paper.sort(key=lambda item: str(item[0].id))  # a fixed starting point, so the seed alone decides the order
        random.Random(f"{attempt.id}:questions").shuffle(paper)
    section_of = question_sections(db, exam, attempt)
    if section_of:
        order = {section.id: i for i, section in enumerate(exam.sections)}
        paper.sort(key=lambda item: order.get(section_of.get(item[0].id), len(order)))  # stable: keeps the shuffle
    return paper


def questions_for_attempt(
    db: Session, exam: models.Exam, attempt: models.ExamAttempt,
    section_id: uuid.UUID | None = None, question_id: uuid.UUID | None = None,
) -> list[dict]:
    """The attempt's questions as this student sees them, without answers, in their order (ordered_paper); only
    those of `section_id` (the open section of a timed-sections exam) or only `question_id` (the open question
    of a per-question exam) when given."""
    paper = ordered_paper(db, exam, attempt)
    section_of = question_sections(db, exam, attempt)
    if section_id is not None:
        paper = [item for item in paper if section_of.get(item[0].id) == section_id]
    if question_id is not None:
        paper = [item for item in paper if item[0].id == question_id]

    # Answers are stored as values, not positions, so shuffling never affects grading
    return [{
        "id": str(q.id),
        "title": q.title,
        "type": q.type,
        "complexity": q.complexity,
        "max_score": int(worth),
        "options": question_types.student_options(q, f"{attempt.id}:{q.id}", exam.shuffle_options),
        "section_id": str(section_of[q.id]) if q.id in section_of else None,
    } for q, worth in paper]


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
