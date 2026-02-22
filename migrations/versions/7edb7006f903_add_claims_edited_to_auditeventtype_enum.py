"""add CLAIMS_EDITED to auditeventtype enum

Revision ID: 7edb7006f903
Revises: d5a2f3e81b94
Create Date: 2026-02-22 18:40:03.445131

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7edb7006f903'
down_revision: Union[str, Sequence[str], None] = 'd5a2f3e81b94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'CLAIMS_EDITED' BEFORE 'MATTER_LOCKED'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enums.
    pass
