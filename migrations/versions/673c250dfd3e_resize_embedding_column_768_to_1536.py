"""resize embedding column 768 to 1536

Revision ID: 673c250dfd3e
Revises: 3340ae9bbdc1
Create Date: 2026-02-22 23:33:06.990061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy.vector


# revision identifiers, used by Alembic.
revision: str = '673c250dfd3e'
down_revision: Union[str, Sequence[str], None] = '3340ae9bbdc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Resize embedding column from 768 to 1536 dimensions."""
    # Must clear existing 768-dim data before ALTER, otherwise pgvector rejects the cast
    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.alter_column('document_chunks', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
               existing_nullable=True)


def downgrade() -> None:
    """Resize embedding column back to 768 dimensions."""
    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.alter_column('document_chunks', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               existing_nullable=True)
