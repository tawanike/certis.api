"""add spec_version_id to risk_analysis_versions and RISK_RE_REVIEWED state

Revision ID: af6657e265aa
Revises: 7117eec8d379
Create Date: 2026-02-22 10:21:17.082714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af6657e265aa'
down_revision: Union[str, Sequence[str], None] = '7117eec8d379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add spec_version_id column to risk_analysis_versions
    op.add_column('risk_analysis_versions', sa.Column('spec_version_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_risk_analysis_versions_spec_version_id',
        'risk_analysis_versions', 'spec_versions',
        ['spec_version_id'], ['id'],
    )

    # Add RISK_RE_REVIEWED to matterstate enum
    op.execute("ALTER TYPE matterstate ADD VALUE IF NOT EXISTS 'RISK_RE_REVIEWED' AFTER 'SPEC_GENERATED'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_risk_analysis_versions_spec_version_id', 'risk_analysis_versions', type_='foreignkey')
    op.drop_column('risk_analysis_versions', 'spec_version_id')
    # Note: PostgreSQL does not support removing enum values
