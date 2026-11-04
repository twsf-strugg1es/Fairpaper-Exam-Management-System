"""Exam sections: parts of an exam with their own title, instructions and, optionally, time

Fixed questions and pool rules each belong to a section (null while the exam has none);
an attempt's drawn questions keep the section of the rule that drew them. For exams whose
sections have time limits, attempt_sections records when each section opened and closed.

Revision ID: 0018_exam_sections
Revises: 0017_unique_evaluation
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018_exam_sections"
down_revision = "0017_unique_evaluation"
branch_labels = None
depends_on = None

SECTION_TABLES = ("exam_questions", "exam_pool_rules", "attempt_questions")


def upgrade() -> None:
    op.create_table(
        "exam_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("instructions", sa.String(1000), nullable=True),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
    )
    op.create_index("ix_exam_sections_exam_id", "exam_sections", ["exam_id"])
    for table in SECTION_TABLES:
        op.add_column(table, sa.Column(
            "section_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_sections.id", ondelete="SET NULL", name=f"fk_{table}_section_id"), nullable=True,
        ))
    op.create_table(
        "attempt_sections",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exam_attempts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exam_sections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("attempt_sections")
    for table in SECTION_TABLES:
        op.drop_constraint(f"fk_{table}_section_id", table, type_="foreignkey")
        op.drop_column(table, "section_id")
    op.drop_index("ix_exam_sections_exam_id", table_name="exam_sections")
    op.drop_table("exam_sections")
