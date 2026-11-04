"""Random question pools: rules per exam, and the questions each attempt drew

Revision ID: 0016_pool_rules
Revises: 0015_exam_show_rank
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_pool_rules"
down_revision = "0015_exam_show_rank"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_pool_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("complexity", sa.String(), nullable=True),
        sa.Column("tag", sa.String(), nullable=True),
        sa.Column("marks", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_exam_pool_rules_exam_id", "exam_pool_rules", ["exam_id"])
    op.create_table(
        "attempt_questions",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("attempt_questions")
    op.drop_index("ix_exam_pool_rules_exam_id", table_name="exam_pool_rules")
    op.drop_table("exam_pool_rules")
