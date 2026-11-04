"""Extra time per student: set on an exam before they start, or added while they write it

exam_extra_time holds the minutes staff gave a student on an exam; the student's attempt
carries them as `extra_minutes`, which moves its deadline (and may take it past the window's
close: that is the point of an accommodation).

Revision ID: 0020_extra_time
Revises: 0019_per_question_timing
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_extra_time"
down_revision = "0019_per_question_timing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_attempts", sa.Column("extra_minutes", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "exam_extra_time",
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("set_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exam_extra_time")
    op.drop_column("exam_attempts", "extra_minutes")
