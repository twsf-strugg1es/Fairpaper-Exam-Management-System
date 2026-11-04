"""Per-question time limits: a timing mode per exam, limits per question, and when each opened

An exam in `per_question` mode shows one question at a time with its own countdown; a
question's limit is its exam override, else the question's default, else none. For those
exams, attempt_question_timings records when each question opened and closed. Questions
also keep the teacher's order in an exam (`position`), which a forward-only exam depends on;
existing exams have none and keep the order they had.

Revision ID: 0019_per_question_timing
Revises: 0018_exam_sections
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019_per_question_timing"
down_revision = "0018_exam_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exams", sa.Column("timing_mode", sa.String(), nullable=False, server_default="exam"))
    op.add_column("questions", sa.Column("default_time_limit_seconds", sa.Integer(), nullable=True))
    op.add_column("exam_questions", sa.Column("time_limit_seconds", sa.Integer(), nullable=True))
    op.add_column("exam_questions", sa.Column("position", sa.Integer(), nullable=True))
    op.create_table(
        "attempt_question_timings",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), primary_key=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("attempt_question_timings")
    op.drop_column("exam_questions", "position")
    op.drop_column("exam_questions", "time_limit_seconds")
    op.drop_column("questions", "default_time_limit_seconds")
    op.drop_column("exams", "timing_mode")
