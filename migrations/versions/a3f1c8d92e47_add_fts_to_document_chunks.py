"""add_fts_to_document_chunks

Revision ID: a3f1c8d92e47
Revises: 96cb835f696b
Create Date: 2026-02-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR


# revision identifiers, used by Alembic.
revision: str = 'a3f1c8d92e47'
down_revision: Union[str, Sequence[str], None] = '96cb835f696b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add full-text search support to document_chunks."""
    # 1. Add tsvector column
    op.add_column('document_chunks', sa.Column('search_vector', TSVECTOR, nullable=True))

    # 2. Create GIN index for fast full-text search
    op.execute(
        'CREATE INDEX ix_document_chunks_search ON document_chunks USING GIN(search_vector)'
    )

    # 3. Backfill existing rows
    op.execute(
        "UPDATE document_chunks SET search_vector = to_tsvector('english', content)"
    )

    # 4. Create trigger function for auto-update on INSERT/UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION update_chunk_search_vector()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', NEW.content);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_chunk_search_vector
        BEFORE INSERT OR UPDATE OF content ON document_chunks
        FOR EACH ROW EXECUTE FUNCTION update_chunk_search_vector();
    """)


def downgrade() -> None:
    """Remove full-text search support from document_chunks."""
    op.execute('DROP TRIGGER IF EXISTS trg_chunk_search_vector ON document_chunks')
    op.execute('DROP FUNCTION IF EXISTS update_chunk_search_vector()')
    op.execute('DROP INDEX IF EXISTS ix_document_chunks_search')
    op.drop_column('document_chunks', 'search_vector')
