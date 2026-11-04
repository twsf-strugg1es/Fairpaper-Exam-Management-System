"""Merit list: exams can show candidates their rank

Revision ID: 0015_exam_show_rank
Revises: 0014_results_release
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_exam_show_rank"
down_revision = "0014_results_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exams", sa.Column("show_rank", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("exams", "show_rank")
