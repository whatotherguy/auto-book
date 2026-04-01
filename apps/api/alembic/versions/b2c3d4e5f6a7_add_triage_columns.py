"""add triage columns to issue

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect as sa_inspect
    existing_cols = {c['name'] for c in sa_inspect(bind).get_columns('issue')}
    if 'triage_verdict' not in existing_cols:
        op.add_column('issue', sa.Column('triage_verdict', sa.String, nullable=True))
    if 'triage_reason' not in existing_cols:
        op.add_column('issue', sa.Column('triage_reason', sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column('issue', 'triage_reason')
    op.drop_column('issue', 'triage_verdict')
