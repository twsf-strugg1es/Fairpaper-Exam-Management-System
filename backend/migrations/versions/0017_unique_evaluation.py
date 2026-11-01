"""One grade per answer

Grading by question (4.9) lets several staff grade the same exam at once. A grade was
created in code after checking that none existed, so two graders saving the same answer
together could store two grades, and the final score would count both. Duplicates are
removed first, keeping the most recently changed grade.

Revision ID: 0017_unique_evaluation
Revises: 0016_pool_rules
Create Date: 2026-11-01
"""
from alembic import op

revision = "0017_unique_evaluation"
down_revision = "0016_pool_rules"
branch_labels = None
depends_on = None

DUPLICATES = """
    SELECT id FROM (
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY answer_id
            ORDER BY CASE WHEN updated_at IS NULL THEN 1 ELSE 0 END, updated_at DESC, id
        ) AS rn
        FROM evaluations
    ) ranked
    WHERE rn > 1
"""


def upgrade() -> None:
    op.execute(f"DELETE FROM evaluations WHERE id IN ({DUPLICATES})")
    op.create_unique_constraint("uq_evaluation_answer", "evaluations", ["answer_id"])


def downgrade() -> None:
    op.drop_constraint("uq_evaluation_answer", "evaluations", type_="unique")
