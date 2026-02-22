"""add qa_report_versions table

Revision ID: c4a8f2e71d93
Revises: af6657e265aa
Create Date: 2026-02-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4a8f2e71d93'
down_revision: Union[str, Sequence[str], None] = 'af6657e265aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create qa_report_versions table
    op.create_table('qa_report_versions',
    sa.Column('matter_id', sa.UUID(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('is_authoritative', sa.Boolean(), nullable=True),
    sa.Column('report_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('claim_version_id', sa.UUID(), nullable=True),
    sa.Column('spec_version_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['claim_version_id'], ['claim_graph_versions.id'], ),
    sa.ForeignKeyConstraint(['matter_id'], ['matters.id'], ),
    sa.ForeignKeyConstraint(['spec_version_id'], ['spec_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_qa_report_versions_matter_id'), 'qa_report_versions', ['matter_id'], unique=False)

    # Add active_qa_version_id to workstreams
    op.add_column('workstreams', sa.Column('active_qa_version_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_workstreams_active_qa_version_id',
        'workstreams', 'qa_report_versions',
        ['active_qa_version_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_workstreams_active_qa_version_id', 'workstreams', type_='foreignkey')
    op.drop_column('workstreams', 'active_qa_version_id')
    op.drop_index(op.f('ix_qa_report_versions_matter_id'), table_name='qa_report_versions')
    op.drop_table('qa_report_versions')
