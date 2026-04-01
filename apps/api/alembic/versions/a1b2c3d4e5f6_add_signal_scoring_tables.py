"""add signal scoring tables

Revision ID: a1b2c3d4e5f6
Revises: f0a1c2b3d4e5
Create Date: 2026-03-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f0a1c2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # --- Signal tables ---
    if 'audiosignal' not in existing_tables:
        op.create_table('audiosignal',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
            sa.Column('signal_type', sa.String, nullable=False),
            sa.Column('start_ms', sa.Integer, nullable=False),
            sa.Column('end_ms', sa.Integer, nullable=False),
            sa.Column('confidence', sa.Float, nullable=False),
            sa.Column('rms_db', sa.Float),
            sa.Column('spectral_centroid_hz', sa.Float),
            sa.Column('zero_crossing_rate', sa.Float),
            sa.Column('onset_strength', sa.Float),
            sa.Column('bandwidth_hz', sa.Float),
            sa.Column('note', sa.String),
            sa.Column('created_at', sa.DateTime, nullable=False),
        )
    if 'vadsegment' not in existing_tables:
        op.create_table('vadsegment',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
            sa.Column('start_ms', sa.Integer, nullable=False),
            sa.Column('end_ms', sa.Integer, nullable=False),
            sa.Column('speech_probability', sa.Float, nullable=False),
            sa.Column('created_at', sa.DateTime, nullable=False),
        )
    if 'alttakecluster' not in existing_tables:
        op.create_table('alttakecluster',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
            sa.Column('manuscript_start_idx', sa.Integer, nullable=False),
            sa.Column('manuscript_end_idx', sa.Integer, nullable=False),
            sa.Column('manuscript_text', sa.String, nullable=False),
            sa.Column('preferred_issue_id', sa.Integer, sa.ForeignKey('issue.id')),
            sa.Column('confidence', sa.Float, nullable=False),
            sa.Column('created_at', sa.DateTime, nullable=False),
        )
    if 'alttakemember' not in existing_tables:
        op.create_table('alttakemember',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('cluster_id', sa.Integer, sa.ForeignKey('alttakecluster.id'), index=True),
            sa.Column('issue_id', sa.Integer, sa.ForeignKey('issue.id'), index=True),
            sa.Column('take_order', sa.Integer, nullable=False),
        )

    # --- Scoring tables ---
    if 'scoringresult' not in existing_tables:
        op.create_table('scoringresult',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('issue_id', sa.Integer, sa.ForeignKey('issue.id'), index=True),
            sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
            sa.Column('scoring_version', sa.String, nullable=False),
            sa.Column('composite_scores_json', sa.String),
            sa.Column('detector_outputs_json', sa.String),
            sa.Column('recommendation_json', sa.String),
            sa.Column('derived_features_json', sa.String),
            sa.Column('mistake_score', sa.Float, default=0.0),
            sa.Column('pickup_score', sa.Float, default=0.0),
            sa.Column('performance_score', sa.Float, default=0.0),
            sa.Column('splice_score', sa.Float, default=0.0),
            sa.Column('priority', sa.String, default='info'),
            sa.Column('baseline_id', sa.String),
            sa.Column('created_at', sa.DateTime, nullable=False),
        )
    if 'calibrationprofile' not in existing_tables:
        op.create_table('calibrationprofile',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('name', sa.String, nullable=False),
            sa.Column('weights_json', sa.String),
            sa.Column('thresholds_json', sa.String),
            sa.Column('metrics_json', sa.String),
            sa.Column('is_default', sa.Boolean, default=False),
            sa.Column('created_at', sa.DateTime, nullable=False),
        )

    # --- Extend Issue table ---
    existing_issue_cols = {c['name'] for c in inspector.get_columns('issue')}
    if 'audio_features_json' not in existing_issue_cols:
        op.add_column('issue', sa.Column('audio_features_json', sa.String))
    if 'audio_signals_json' not in existing_issue_cols:
        op.add_column('issue', sa.Column('audio_signals_json', sa.String))
    if 'prosody_features_json' not in existing_issue_cols:
        op.add_column('issue', sa.Column('prosody_features_json', sa.String))
    if 'alt_take_cluster_id' not in existing_issue_cols:
        # SQLite doesn't support adding FK constraints via ALTER TABLE; column added without FK
        op.add_column('issue', sa.Column('alt_take_cluster_id', sa.Integer))


def downgrade() -> None:
    op.drop_column('issue', 'alt_take_cluster_id')
    op.drop_column('issue', 'prosody_features_json')
    op.drop_column('issue', 'audio_signals_json')
    op.drop_column('issue', 'audio_features_json')
    op.drop_table('calibrationprofile')
    op.drop_table('scoringresult')
    op.drop_table('alttakemember')
    op.drop_table('alttakecluster')
    op.drop_table('vadsegment')
    op.drop_table('audiosignal')
