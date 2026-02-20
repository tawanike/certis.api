"""add_matter_jurisdictions_table

Revision ID: e1e3b25fcab0
Revises: 07660360fb69
Create Date: 2026-02-19 21:32:40.699855

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e1e3b25fcab0'
down_revision: Union[str, Sequence[str], None] = '07660360fb69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new enum values to the existing jurisdictionenum type
    op.execute("ALTER TYPE jurisdictionenum ADD VALUE IF NOT EXISTS 'JPO'")
    op.execute("ALTER TYPE jurisdictionenum ADD VALUE IF NOT EXISTS 'KIPO'")
    op.execute("ALTER TYPE jurisdictionenum ADD VALUE IF NOT EXISTS 'CNIPA'")
    
    # Create the association table, reusing the existing enum type
    op.create_table('matter_jurisdictions',
        sa.Column('matter_id', sa.UUID(), nullable=False),
        sa.Column('jurisdiction', postgresql.ENUM('USPTO', 'EPO', 'WIPO', 'JPO', 'KIPO', 'CNIPA', name='jurisdictionenum', create_type=False), nullable=False),
        sa.ForeignKeyConstraint(['matter_id'], ['matters.id'], ),
        sa.PrimaryKeyConstraint('matter_id', 'jurisdiction')
    )
    
    # Migrate existing jurisdiction data to the new table
    op.execute("""
        INSERT INTO matter_jurisdictions (matter_id, jurisdiction)
        SELECT id, jurisdiction FROM matters WHERE jurisdiction IS NOT NULL
    """)
    
    # Drop the old single-jurisdiction column
    op.drop_column('matters', 'jurisdiction')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('matters', sa.Column('jurisdiction', postgresql.ENUM('USPTO', 'EPO', 'WIPO', name='jurisdictionenum', create_type=False), server_default=sa.text("'USPTO'::jurisdictionenum"), autoincrement=False, nullable=False))
    
    # Migrate first jurisdiction back
    op.execute("""
        UPDATE matters SET jurisdiction = (
            SELECT jurisdiction FROM matter_jurisdictions WHERE matter_id = matters.id LIMIT 1
        )
    """)
    
    op.drop_table('matter_jurisdictions')
