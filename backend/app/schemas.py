import re
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator, model_validator

from . import models, question_types
from uuid import UUID
from typing import Any, Optional
from datetime import datetime, date, timezone


_TIMEZONES = available_timezones()


def _check_language(value: Optional[str]) -> Optional[str]:
    if value is not None and value not in models.LANGUAGES:
        raise ValueError(f"Language must be one of: {', '.join(models.LANGUAGES)}")
    return value


def _check_timezone(value: Optional[str]) -> Optional[str]:
    if value is not None and value not in _TIMEZONES:
        raise ValueError("Unknown timezone. Use an IANA name such as Asia/Dhaka")
    return value


def _check_code(value: Optional[str], length: int, what: str) -> Optional[str]:
    """Country (2 letters) and currency (3 letters) codes, stored upper case; empty clears."""
    if value is None or value.strip() == "":
        return None
    value = value.strip().upper()
    if not re.fullmatch(f"[A-Z]{{{length}}}", value):
        raise ValueError(f"{what} must be a {length}-letter code")
    return value


class LocaleFields(BaseModel):
    """An organization's locale. Every field is optional so a client can change one at a time."""
    country: Optional[str] = None
    default_language: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None

    @field_validator("country")
    @classmethod
    def _country(cls, v):
        return _check_code(v, 2, "Country")

    @field_validator("currency")
    @classmethod
    def _currency(cls, v):
        return _check_code(v, 3, "Currency")

    @field_validator("default_language")
    @classmethod
    def _language(cls, v):
        return _check_language(v)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, v):
        return _check_timezone(v)


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    confirm_password: Optional[str] = None


class CandidateSignup(UserCreate):
    """Public signup; a join code also makes the new user a candidate in that organization."""
    join_code: Optional[str] = None


class OrganizationSignup(UserCreate, LocaleFields):
    """Sign up a new organization together with its owner's account.

    The signup page sends the browser's timezone, so exam windows are right from the start.
    """
    organization_name: str = Field(min_length=2, max_length=120)

    @field_validator("timezone", mode="before")
    @classmethod
    def _browser_timezone(cls, v):
        # A browser can report a zone this server doesn't know: start on UTC instead of failing
        return v if v in _TIMEZONES else None


class MembershipOut(BaseModel):
    organization_id: UUID
    organization_name: str
    role: str
    # Needed on every screen: exam windows use the timezone, the language is the fallback
    timezone: str = models.DEFAULT_TIMEZONE
    default_language: str = models.DEFAULT_LANGUAGE


class User(UserBase):
    id: UUID
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    language: Optional[str] = None
    email_verified_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class UserWithMemberships(User):
    memberships: list[MembershipOut] = []


class UserProfile(BaseModel):
    """Full user profile with all details."""
    id: UUID
    email: str
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    language: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class GroupSummary(BaseModel):
    id: UUID
    name: str
    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class OrganizationUpdate(LocaleFields):
    """Change the name and/or locale; fields left out stay as they are."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GroupOut(GroupSummary):
    join_code: str
    member_count: int


class JoinRequest(BaseModel):
    join_code: str


class MemberAdd(BaseModel):
    email: EmailStr
    role: str
    full_name: Optional[str] = Field(None, max_length=200)  # used only when the invite creates the account

    @field_validator("full_name")
    @classmethod
    def blank_name_is_none(cls, v: Optional[str]) -> Optional[str]:
        return (v or "").strip() or None


class MemberUpdate(BaseModel):
    role: str


class GroupMembersUpdate(BaseModel):
    user_ids: list[UUID]


class BulkQuestionIds(BaseModel):
    question_ids: list[UUID] = Field(min_length=1, max_length=500)


class QuestionBase(BaseModel):
    title: str
    description: Optional[str] = None
    complexity: str
    type: str
    options: Optional[Any] = None
    correct_answers: Any
    max_score: int = 1
    tags: Optional[list[str]] = None


class Question(QuestionBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


class QuestionForStudent(BaseModel):
    """Question schema for students - excludes correct_answers for security."""
    id: UUID
    title: str
    complexity: str
    type: str
    options: Optional[Any] = None
    max_score: int
    tags: Optional[list[str]] = None
    model_config = ConfigDict(from_attributes=True)


class PoolRuleIn(BaseModel):
    """Draw `count` random questions from the bank (of this difficulty, with this tag), worth `marks` each."""
    count: int = Field(ge=1, le=200)
    complexity: Optional[str] = None  # None: any difficulty
    tag: Optional[str] = Field(default=None, max_length=60)  # None: any tag
    marks: int = Field(default=1, ge=1, le=100)

    @field_validator("complexity")
    @classmethod
    def _complexity(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if v not in models.COMPLEXITIES:
            raise ValueError(f"Difficulty must be one of: {', '.join(models.COMPLEXITIES)}")
        return v

    @field_validator("tag")
    @classmethod
    def _tag(cls, v: Optional[str]) -> Optional[str]:
        # Written like question tags (lower case, no '#', single spaces), so the rule matches what the bank stores
        if not v:
            return None
        tag = " ".join(v.replace('"', "").replace("\\", "").strip().lstrip("#").split()).lower()
        return tag or None


class ExamCreate(BaseModel):
    """A new exam. The form checks the same rules, but the server is the one that enforces them."""
    title: str = Field(min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime
    duration_minutes: int = Field(ge=1, le=24 * 60)
    question_ids: list[UUID] = []  # the fixed questions every student gets
    pool_rules: list[PoolRuleIn] = Field(default=[], max_length=20)  # random questions drawn per student
    group_ids: list[UUID] = []  # empty: open to every candidate in the organization
    shuffle_questions: bool = True
    shuffle_options: bool = True
    require_fullscreen: bool = True
    block_copy_paste: bool = True
    max_violations: Optional[int] = Field(default=None, ge=1, le=100)  # None: never auto-submit
    results_release: str = "immediate"  # immediate | on_close | manual
    show_rank: bool = False  # candidates see their place on the merit list
    # Marks per question for this exam only; questions left out use their own max_score
    question_marks: dict[UUID, int] = {}

    @field_validator("results_release")
    @classmethod
    def _release(cls, v: str) -> str:
        if v not in models.RESULTS_RELEASES:
            raise ValueError("Choose when students see their results.")
        return v

    @field_validator("question_marks")
    @classmethod
    def _marks(cls, v: dict[UUID, int]) -> dict[UUID, int]:
        if any(not 1 <= m <= 100 for m in v.values()):
            raise ValueError("Marks for a question must be between 1 and 100.")
        return v

    @model_validator(mode="after")
    def _marks_for_chosen_questions(self):
        if set(self.question_marks) - set(self.question_ids):
            raise ValueError("Marks were given for a question that isn't in this exam.")
        return self

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Give the exam a title.")
        return v.strip()

    @field_validator("start_time", "end_time")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        # Times without an offset are read as UTC (rule: clients send UTC with an offset)
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)

    @field_validator("question_ids", "group_ids")
    @classmethod
    def _unique(cls, v: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(v))  # drop repeats, keep the order

    @model_validator(mode="after")
    def _window(self):
        if self.end_time <= self.start_time:
            raise ValueError("The exam must close after it opens.")
        return self

    @model_validator(mode="after")
    def _has_questions(self):
        if not self.question_ids and not self.pool_rules:
            raise ValueError("Add at least one question, or a rule that draws random questions.")
        return self


class Exam(BaseModel):
    id: UUID
    title: str
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    is_published: bool
    published_by: Optional[str] = None  # Admin email who published
    groups: list[GroupSummary] = []
    shuffle_questions: bool = True
    shuffle_options: bool = True
    require_fullscreen: bool = True
    block_copy_paste: bool = True
    max_violations: Optional[int] = None
    questions: list[Question]
    model_config = ConfigDict(from_attributes=True)


class ExamForStudent(BaseModel):
    """Exam schema for students - uses QuestionForStudent to hide correct_answers."""
    id: UUID
    title: str
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    is_published: bool
    questions: list[QuestionForStudent]
    model_config = ConfigDict(from_attributes=True)


class AnswerBase(BaseModel):
    question_id: UUID
    answer_data: Any


class AnswerCreate(AnswerBase):
    # Increases with every save from the exam page (it survives a reload); older ones are ignored
    client_seq: Optional[int] = Field(None, ge=0, le=2**53)


class Answer(AnswerBase):
    id: UUID
    attempt_id: UUID
    model_config = ConfigDict(from_attributes=True)


class ExamAttempt(BaseModel):
    id: UUID
    exam_id: UUID
    student_id: UUID
    start_time: datetime
    end_time: Optional[datetime] = None
    score: Optional[float] = None
    total_possible_score: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class ExamAttemptWithExam(BaseModel):
    """Exam attempt with nested exam details for student dashboard."""
    id: UUID
    exam_id: UUID
    student_id: UUID
    start_time: datetime
    end_time: Optional[datetime] = None
    score: Optional[float] = None
    total_possible_score: Optional[float] = None
    exam: ExamForStudent
    model_config = ConfigDict(from_attributes=True)


class ExamStartResponse(BaseModel):
    """Response when starting or resuming an exam attempt."""
    exam: ExamForStudent
    attempt: ExamAttempt
    model_config = ConfigDict(from_attributes=True)


class EvaluationCreate(BaseModel):
    """Create/update evaluation for a student answer."""
    is_correct: Optional[bool] = None
    comment: Optional[str] = None  # Max 100 chars
    score_awarded: Optional[float] = None


class Evaluation(BaseModel):
    """Evaluation of a student answer."""
    id: UUID
    answer_id: UUID
    evaluated_by: UUID
    is_correct: Optional[bool] = None
    comment: Optional[str] = None
    score_awarded: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class IntegrityEventIn(BaseModel):
    """One event reported by the exam page."""
    type: str
    occurred_at: Optional[datetime] = None
    details: Optional[dict[str, Any]] = None

    @field_validator("type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in models.EVENT_TYPES:
            raise ValueError(f"Unknown event type: {value}")
        return value

    @field_validator("details")
    @classmethod
    def small_details(cls, value: Optional[dict]) -> Optional[dict]:
        if value is not None and len(str(value)) > 1000:
            raise ValueError("details too large")
        return value


class IntegrityEventsIn(BaseModel):
    events: list[IntegrityEventIn] = Field(min_length=1, max_length=50)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=6, max_length=200)


class EmailVerification(BaseModel):
    token: str = Field(min_length=20, max_length=2000)


class QuestionEdit(BaseModel):
    """A question written in the editor. Its options and answer key are checked by the rules of its type
    (`question_types.clean`); written and image answers have neither (an examiner grades them)."""
    title: str = Field(min_length=1, max_length=2000)
    description: Optional[str] = Field(default=None, max_length=5000)
    complexity: str
    type: str
    options: Any = None  # a list, or {"left": [...], "right": [...]} for matching
    correct_answers: Any = None
    max_score: int = Field(default=1, ge=1, le=100)
    tags: list[str] = []

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Write the question.")
        return v.strip()

    @field_validator("description")
    @classmethod
    def _description(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if v else None

    @field_validator("complexity")
    @classmethod
    def _complexity(cls, v: str) -> str:
        if v not in models.COMPLEXITIES:
            raise ValueError(f"Difficulty must be one of: {', '.join(models.COMPLEXITIES)}")
        return v

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in models.QUESTION_TYPES:
            raise ValueError(f"Type must be one of: {', '.join(models.QUESTION_TYPES)}")
        return v

    @model_validator(mode="after")
    def _answers(self):
        self.options, self.correct_answers = question_types.clean(self.type, self.title, self.options, self.correct_answers)
        return self


class WaitlistJoin(BaseModel):
    email: EmailStr
    source: Optional[str] = Field(None, max_length=40)  # which call to action
    locale: Optional[str] = Field(None, max_length=20)  # navigator.language
    website: Optional[str] = None  # honeypot: hidden from people, filled in by bots

    @field_validator("source", "locale")
    @classmethod
    def tidy_label(cls, v: Optional[str]) -> Optional[str]:
        # Free text from the page; keep only short, plain labels
        v = (v or "").strip()
        return v if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", v) else None


class WaitlistUnsubscribe(BaseModel):
    token: str
