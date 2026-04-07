"""add review decision fields to issue

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-07 00:00:00.000000

This migration adds the new v2 review decision model fields:
- editor_decision: "cut", "keep", "needs_review", or null (untouched)
- model_action: "safe_cut", "compare_takes", "review", "ignore"
- review_state: "unreviewed", "reviewed"

These fields replace the ambiguous status field which mixed model inference
and user choice. The status field is kept for backward compatibility.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect as sa_inspect
    existing_cols = {c['name'] for c in sa_inspect(bind).get_columns('issue')}

    # Add new v2 review decision fields
    if 'editor_decision' not in existing_cols:
        op.add_column('issue', sa.Column('editor_decision', sa.String, nullable=True))
    if 'model_action' not in existing_cols:
        op.add_column('issue', sa.Column('model_action', sa.String, nullable=True))
    if 'review_state' not in existing_cols:
        op.add_column('issue', sa.Column('review_state', sa.String, nullable=False, server_default='unreviewed'))

    # Update existing issues: migrate legacy status to new fields
    # - approved -> review_state="reviewed" (but don't set editor_decision, let user decide)
    # - rejected -> review_state="reviewed" (but don't set editor_decision)
    # - needs_manual -> review_state="unreviewed"
    # Note: We don't automatically set editor_decision because that's user-only now
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE issue SET review_state = 'reviewed' WHERE status IN ('approved', 'rejected')")
    )


def downgrade() -> None:
    op.drop_column('issue', 'review_state')
    op.drop_column('issue', 'model_action')
    op.drop_column('issue', 'editor_decision')
