"""Per-exam marks: a question can be worth more (or less) in one exam without changing the bank

Revision ID: 0013_exam_question_marks
Revises: 0012_answer_client_seq
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_exam_question_marks"
down_revision = "0012_answer_client_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_questions", sa.Column("marks", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("exam_questions", "marks")
