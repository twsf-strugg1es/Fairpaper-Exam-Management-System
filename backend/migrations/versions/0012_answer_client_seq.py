"""Answers remember the exam page's save number, so a delayed retry can't overwrite a newer answer

Revision ID: 0012_answer_client_seq
Revises: 0011_waitlist_signups
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_answer_client_seq"
down_revision = "0011_waitlist_signups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("answers", sa.Column("client_seq", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("answers", "client_seq")
