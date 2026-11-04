"""Result publishing control: when students get to see their score

Revision ID: 0014_results_release
Revises: 0013_exam_question_marks
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_results_release"
down_revision = "0013_exam_question_marks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing exams keep today's behavior: the score shows right after submitting
    op.add_column("exams", sa.Column("results_release", sa.String(), nullable=False, server_default="immediate"))
    op.add_column("exams", sa.Column("results_released_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("exams", "results_released_at")
    op.drop_column("exams", "results_release")
