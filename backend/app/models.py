import secrets
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Table,
    Float,
    Date,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy import false as sa_false, true as sa_true
from sqlalchemy.orm import relationship

from .database import Base

# Association table for many-to-many relationship between Exam and Question
exam_questions = Table(
    "exam_questions",
    Base.metadata,
    Column("exam_id", UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "question_id",
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # Marks this question is worth in this exam; null means the question's own max_score
    Column("marks", Integer, nullable=True),
    # The section it's in (task 4.10); null while the exam has no sections
    Column("section_id", UUID(as_uuid=True), ForeignKey("exam_sections.id", ondelete="SET NULL", name="fk_exam_questions_section_id"), nullable=True),
    # Seconds it gets in a per-question exam (task 4.11b); null: the question's own default, else no limit
    Column("time_limit_seconds", Integer, nullable=True),
    # The teacher's order (the order the form sent them); shuffling still applies per student when on
    Column("position", Integer, nullable=True),
)


# Which candidates belong to which group
group_members = Table(
    "group_members",
    Base.metadata,
    Column("group_id", UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "membership_id",
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# Which groups an exam is for; an exam with no groups is open to every candidate in its organization
exam_groups = Table(
    "exam_groups",
    Base.metadata,
    Column("exam_id", UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)

# Membership roles, from most to least privileged
RESULTS_IMMEDIATE = "immediate"  # students see their score as soon as they submit
RESULTS_ON_CLOSE = "on_close"    # ...once the exam window has closed
RESULTS_MANUAL = "manual"        # ...only after staff press Release results
RESULTS_RELEASES = (RESULTS_IMMEDIATE, RESULTS_ON_CLOSE, RESULTS_MANUAL)

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_EXAMINER = "examiner"
ROLE_CANDIDATE = "candidate"
ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EXAMINER, ROLE_CANDIDATE)
STAFF_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EXAMINER)  # can manage questions, exams and grading
MANAGER_ROLES = (ROLE_OWNER, ROLE_ADMIN)  # can also manage members and groups

# What each type stores and how it's graded: question_types.py
QUESTION_TYPES = (
    "single_choice", "multi_choice", "true_false", "fill_blank", "numeric", "matching", "ordering",
    "text", "image_upload",
)
CHOICE_TYPES = ("single_choice", "multi_choice")
MANUAL_TYPES = ("text", "image_upload")  # graded by staff; every other type is graded automatically
AUTO_GRADED_TYPES = tuple(t for t in QUESTION_TYPES if t not in MANUAL_TYPES)
COMPLEXITIES = ("easy", "medium", "hard")
MAX_OPTIONS = 10

# How an exam is timed (task 4.11b): one duration with free navigation, or one question at a time, each with
# its own limit and no going back
TIMING_EXAM = "exam"
TIMING_PER_QUESTION = "per_question"
TIMING_MODES = (TIMING_EXAM, TIMING_PER_QUESTION)
QUESTION_SECONDS = (10, 3600)  # the shortest and longest limit a question can have
MAX_EXTRA_MINUTES = 600  # extra time staff can give one student on one exam (task 4.11)

# Interface languages with a catalog in the frontend (src/i18n); BCP 47 codes
LANGUAGES = ("en", "bn")
GENDERS = ("female", "male", "other")  # or none given
DEFAULT_LANGUAGE = "en"
DEFAULT_TIMEZONE = "UTC"


# Easy to read aloud and type: no lowercase, and no look-alikes such as O/0 or I/1
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_join_code() -> str:
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(8))


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    join_code = Column(String, unique=True, nullable=False, default=generate_join_code)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    # Locale: exam windows are shown in this timezone; members without a language get this one
    country = Column(String(2), nullable=True)  # ISO 3166-1 alpha-2
    default_language = Column(String, nullable=False, default=DEFAULT_LANGUAGE, server_default=DEFAULT_LANGUAGE)
    timezone = Column(String, nullable=False, default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE)  # IANA
    currency = Column(String(3), nullable=True)  # ISO 4217

    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    groups = relationship("Group", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String, nullable=True)  # 'male', 'female', 'other'
    language = Column(String, nullable=True)  # BCP 47; null = the organization's default
    email_verified_at = Column(DateTime(timezone=True), nullable=True)  # set by the emailed link
    # Sign-in tokens issued before this moment stop working: set when the password changes or is reset
    tokens_valid_after = Column(DateTime(timezone=True), nullable=True)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class Membership(Base):
    """A user's role in one organization. A user can belong to several organizations."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String, nullable=False)  # one of ROLES
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")
    groups = relationship("Group", secondary=group_members, back_populates="members")


class Group(Base):
    """A set of candidates within an organization, e.g. a batch, class or hiring round."""

    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_group_org_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    # Joining with this code also adds the candidate to the group
    join_code = Column(String, unique=True, nullable=False, default=generate_join_code)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="groups")
    members = relationship("Membership", secondary=group_members, back_populates="groups")
    exams = relationship("Exam", secondary=exam_groups, back_populates="groups")


class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    complexity = Column(String, nullable=False)
    type = Column(String, nullable=False)  # e.g., 'single_choice', 'multi_choice'
    options = Column(JSON, nullable=True)
    correct_answers = Column(JSON, nullable=False)
    max_score = Column(Integer, nullable=False, default=1)
    tags = Column(JSON, nullable=True, default=list)  # e.g., ["geography", "history"]
    # Its time in per-question exams unless the exam sets another (task 4.11b); null: no limit
    default_time_limit_seconds = Column(Integer, nullable=True)
    # Set instead of deleting once students have answered it, so past results stay intact
    archived_at = Column(DateTime(timezone=True), nullable=True)

    exams = relationship("Exam", secondary=exam_questions, back_populates="questions")


class Exam(Base):
    __tablename__ = "exams"
    # The exams list and the student dashboard filter by organization and sort by start
    __table_args__ = (Index("ix_exams_organization_start", "organization_id", "start_time"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    is_published = Column(Boolean, nullable=False, default=False)
    published_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Staff member who published

    # Integrity settings
    shuffle_questions = Column(Boolean, nullable=False, default=True, server_default=sa_true())
    shuffle_options = Column(Boolean, nullable=False, default=True, server_default=sa_true())
    require_fullscreen = Column(Boolean, nullable=False, default=True, server_default=sa_true())
    block_copy_paste = Column(Boolean, nullable=False, default=True, server_default=sa_true())
    # Submit the attempt automatically once this many violations are recorded; None = never
    max_violations = Column(Integer, nullable=True)
    # When students see their score: right after submitting, when the exam closes, or when staff release it
    results_release = Column(String, nullable=False, default="immediate", server_default="immediate")
    results_released_at = Column(DateTime(timezone=True), nullable=True)  # set by "Release results"
    # Candidates also see their place on the merit list (once results are visible)
    show_rank = Column(Boolean, nullable=False, default=False, server_default=sa_false())
    # One of TIMING_MODES: one duration, or one question at a time with its own limit (task 4.11b)
    timing_mode = Column(String, nullable=False, default=TIMING_EXAM, server_default=TIMING_EXAM)
    # Set instead of deleting once anyone has started it; archived exams are hidden and can't be started
    archived_at = Column(DateTime(timezone=True), nullable=True)

    questions = relationship("Question", secondary=exam_questions, back_populates="exams", order_by=exam_questions.c.position)
    # Parts of the exam, in order (task 4.10); none for an exam in one piece
    sections = relationship(
        "ExamSection", order_by="ExamSection.position", cascade="all, delete-orphan", back_populates="exam"
    )
    # Random questions drawn for each attempt on top of the fixed ones (task 4.6)
    pool_rules = relationship(
        "ExamPoolRule", order_by="ExamPoolRule.position", cascade="all, delete-orphan", back_populates="exam"
    )
    groups = relationship("Group", secondary=exam_groups, back_populates="exams")
    publisher = relationship("User", foreign_keys=[published_by])


class ExamSection(Base):
    """A part of an exam with its own title, instructions and, optionally, its own time (task 4.10). When any
    section of an exam has a time limit, students take the sections in order, one open at a time, and a
    section locks when its time ends or they finish it (crud.section_timeline)."""
    __tablename__ = "exam_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    title = Column(String(120), nullable=False)
    instructions = Column(String(1000), nullable=True)
    time_limit_minutes = Column(Integer, nullable=True)  # null: no time of its own

    exam = relationship("Exam", back_populates="sections")


class ExamPoolRule(Base):
    """'Draw `count` random questions (of this difficulty, with this tag) worth `marks` each' (PRD US17, AC18).
    A fixed mark per drawn question keeps every student's total the same, so the merit list stays fair."""
    __tablename__ = "exam_pool_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    count = Column(Integer, nullable=False)
    complexity = Column(String, nullable=True)  # one of COMPLEXITIES; null: any difficulty
    tag = Column(String, nullable=True)  # normalized like question tags; null: any tag
    marks = Column(Integer, nullable=False, default=1, server_default="1")
    # The section its questions go into; null while the exam has no sections
    section_id = Column(UUID(as_uuid=True), ForeignKey("exam_sections.id", ondelete="SET NULL", name="fk_exam_pool_rules_section_id"), nullable=True)

    exam = relationship("Exam", back_populates="pool_rules")
    section = relationship("ExamSection")


class AttemptQuestion(Base):
    """The paper an attempt got, for exams with pool rules: fixed and drawn questions, drawn once when the
    attempt started and stored, so a reload or a change to the bank never changes it. `marks` is frozen too."""
    __tablename__ = "attempt_questions"

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), primary_key=True)
    position = Column(Integer, nullable=False)
    marks = Column(Integer, nullable=False)
    # Frozen with the paper: a fixed question's section, or the section of the rule that drew it
    section_id = Column(UUID(as_uuid=True), ForeignKey("exam_sections.id", ondelete="SET NULL", name="fk_attempt_questions_section_id"), nullable=True)

    question = relationship("Question")


class ExamExtraTime(Base):
    """Extra minutes staff gave one student on one exam (task 4.11): an accommodation set before they start,
    or time added while they write. The attempt carries the same number as `extra_minutes`."""
    __tablename__ = "exam_extra_time"

    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    minutes = Column(Integer, nullable=False)
    set_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    student = relationship("User", foreign_keys=[student_id])


class AttemptQuestionTiming(Base):
    """When an attempt opened and closed each question of a per-question exam (task 4.11b, PRD AC26-AC28). One
    question is open at a time; the next opens when it closes (Next, or its time running out), and `closes_at`
    is fixed at opening, so a reload never restarts a question's countdown."""
    __tablename__ = "attempt_question_timings"

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), primary_key=True)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closes_at = Column(DateTime(timezone=True), nullable=True)  # null: no limit, it waits for Next
    closed_at = Column(DateTime(timezone=True), nullable=True)  # Next, time-out, or the attempt ended


class AttemptSection(Base):
    """When an attempt opened and closed each section, for exams whose sections have time limits. The first
    opens when the attempt starts and each next one when the one before closes; `closes_at` is fixed at
    opening, so the clock keeps running while the student is away."""
    __tablename__ = "attempt_sections"

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True)
    section_id = Column(UUID(as_uuid=True), ForeignKey("exam_sections.id", ondelete="CASCADE"), primary_key=True)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closes_at = Column(DateTime(timezone=True), nullable=True)  # null: the section has no time of its own
    closed_at = Column(DateTime(timezone=True), nullable=True)  # finished, timed out, or the attempt ended


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    # One attempt per student per exam; also stops two simultaneous "start" requests creating two
    __table_args__ = (UniqueConstraint("exam_id", "student_id", name="uq_attempt_exam_student"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime(timezone=True), nullable=True)
    score = Column(Float, nullable=True)
    total_possible_score = Column(Float, nullable=True)
    submit_reason = Column(String, nullable=True)  # one of SUBMIT_REASONS, set when the attempt ends
    # Extra time staff gave this student (task 4.11): moves the deadline, even past the window's close
    extra_minutes = Column(Integer, nullable=False, default=0, server_default="0")

    exam = relationship("Exam")
    student = relationship("User")
    integrity_events = relationship(
        "IntegrityEvent", back_populates="attempt", cascade="all, delete-orphan", order_by="IntegrityEvent.recorded_at"
    )


SUBMIT_STUDENT = "student"  # the student pressed submit
SUBMIT_TIME_UP = "time_up"  # the timer ran out
SUBMIT_VIOLATIONS = "violations"  # too many integrity violations
SUBMIT_REASONS = (SUBMIT_STUDENT, SUBMIT_TIME_UP, SUBMIT_VIOLATIONS)

# Integrity events reported by the exam page. Violations count toward the exam's max_violations;
# the other events are flags that examiners see in the report but that never end an attempt.
EVENT_FOCUS_LOST = "focus_lost"  # switched to another tab, window or app
EVENT_FOCUS_RETURNED = "focus_returned"  # came back; details carry how long they were away
EVENT_FULLSCREEN_EXIT = "fullscreen_exit"
EVENT_COPY_PASTE = "copy_paste"  # copy, cut or paste attempt
EVENT_CONTEXT_MENU = "context_menu"
EVENT_BLOCKED_SHORTCUT = "blocked_shortcut"  # e.g. Ctrl+C, PrintScreen, F12
EVENT_MULTIPLE_SCREENS = "multiple_screens"
VIOLATION_EVENTS = (EVENT_FOCUS_LOST, EVENT_FULLSCREEN_EXIT)
FLAG_EVENTS = (EVENT_COPY_PASTE, EVENT_CONTEXT_MENU, EVENT_BLOCKED_SHORTCUT, EVENT_MULTIPLE_SCREENS)
EVENT_TYPES = VIOLATION_EVENTS + FLAG_EVENTS + (EVENT_FOCUS_RETURNED,)


class IntegrityEvent(Base):
    """Something the exam page noticed during an attempt, such as leaving the exam tab."""

    __tablename__ = "integrity_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type = Column(String, nullable=False)  # one of EVENT_TYPES
    occurred_at = Column(DateTime(timezone=True), nullable=True)  # the student's clock; informational only
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))  # the server's clock
    details = Column(JSON, nullable=True)

    attempt = relationship("ExamAttempt", back_populates="integrity_events")


class Answer(Base):
    __tablename__ = "answers"
    # One answer per question per attempt; also serves as the index on attempt_id
    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_answer_attempt_question"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("exam_attempts.id"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    answer_data = Column(JSON, nullable=False)
    # The exam page numbers every save; a delayed retry carrying an older number is ignored
    client_seq = Column(BigInteger, nullable=True)

    attempt = relationship("ExamAttempt")
    question = relationship("Question")


class Evaluation(Base):
    """A grade for a written or image answer: one per answer (crud.grade_answer)."""
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("answer_id", name="uq_evaluation_answer"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_id = Column(UUID(as_uuid=True), ForeignKey("answers.id"), nullable=False, index=True)
    evaluated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # Teacher/Admin
    is_correct = Column(Boolean, nullable=True)  # full marks; the mark itself, partial or not, is score_awarded
    comment = Column(String(100), nullable=True)  # Max 100 characters
    score_awarded = Column(Float, nullable=True)  # Score given by teacher
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    answer = relationship("Answer")
    evaluator = relationship("User", foreign_keys=[evaluated_by])


TOKEN_RESET = "reset"    # 30 minutes, from "Forgot password?"
TOKEN_INVITE = "invite"  # 7 days, for accounts created by a bulk import


class PasswordResetToken(Base):
    """A single-use password reset link. Only the SHA-256 of the token is stored, so a
    database leak doesn't hand out working links."""

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    purpose = Column(String, nullable=False, default=TOKEN_RESET, server_default=TOKEN_RESET)

    user = relationship("User")


class WaitlistSignup(Base):
    """Someone who wants one email when Fairpaper launches. Belongs to Fairpaper itself, not to
    an organization; read only by `manage_waitlist.py`, never through the API."""

    __tablename__ = "waitlist_signups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True)  # lower-cased and trimmed
    source = Column(String(40), nullable=True)  # which call to action, e.g. landing-hero
    locale = Column(String(20), nullable=True)  # browser language, for the launch email
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    notified_at = Column(DateTime(timezone=True), nullable=True)  # launch email sent; never send twice
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
