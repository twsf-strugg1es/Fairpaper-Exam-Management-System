"""Sign-in sessions end when the password changes

users.tokens_valid_after is set when someone changes or resets their password; every sign-in
token issued before it stops working, refreshes included, so a stolen token dies with the old
password. Null (every account until its next password change) keeps today's behavior.

Revision ID: 0021_session_cutoff
Revises: 0020_extra_time
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_session_cutoff"
down_revision = "0020_extra_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tokens_valid_after")
