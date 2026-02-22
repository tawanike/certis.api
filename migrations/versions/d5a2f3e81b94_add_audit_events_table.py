"""add audit_events table

Revision ID: d5a2f3e81b94
Revises: c4a8f2e71d93
Create Date: 2026-02-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5a2f3e81b94'
down_revision: Union[str, Sequence[str], None] = 'c4a8f2e71d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDIT_EVENT_VALUES = (
    'BRIEF_UPLOADED', 'BRIEF_APPROVED',
    'CLAIMS_GENERATED', 'CLAIMS_COMMITTED',
    'RISK_ANALYZED', 'RISK_COMMITTED',
    'SPEC_GENERATED', 'SPEC_COMMITTED',
    'RISK_RE_EVALUATED', 'RISK_RE_EVAL_COMMITTED',
    'QA_VALIDATED', 'QA_COMMITTED',
    'MATTER_LOCKED', 'EXPORT_GENERATED',
)


def upgrade() -> None:
    # Create the enum type using raw SQL to avoid conflicts with metadata
    enum_values = ", ".join(f"'{v}'" for v in AUDIT_EVENT_VALUES)
    op.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auditeventtype') THEN CREATE TYPE auditeventtype AS ENUM ({enum_values}); END IF; END $$;")

    op.create_table(
        'audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('matter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('matters.id'), nullable=False),
        sa.Column('event_type', postgresql.ENUM(*AUDIT_EVENT_VALUES, name='auditeventtype', create_type=False), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('artifact_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('artifact_type', sa.String(), nullable=True),
        sa.Column('detail', postgresql.JSONB(), nullable=True),
    )
    op.create_index('ix_audit_events_matter_id', 'audit_events', ['matter_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_events_matter_id', table_name='audit_events')
    op.drop_table('audit_events')
    op.execute("DROP TYPE IF EXISTS auditeventtype")
