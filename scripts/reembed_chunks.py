"""
Re-embed all document chunks using the current embedding provider.

Usage:
    cd backend && uv run python -m scripts.reembed_chunks
"""

import asyncio
import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Import the app to ensure all models are registered with SQLAlchemy
import src.main  # noqa: F401

from src.config import settings
from src.documents.models import DocumentChunk
from src.llm.factory import get_embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50


async def reembed_all():
    engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    embeddings = get_embeddings()

    async with async_session() as db:
        # Count chunks needing re-embedding (NULL embedding)
        count_result = await db.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.embedding.is_(None))
        )
        total = count_result.scalar()
        logger.info(f"Found {total} chunks with NULL embeddings to re-embed")

        if total == 0:
            logger.info("Nothing to do")
            return

        # Process in batches
        offset = 0
        processed = 0
        while True:
            result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.embedding.is_(None))
                .order_by(DocumentChunk.id)
                .limit(BATCH_SIZE)
            )
            chunks = list(result.scalars().all())
            if not chunks:
                break

            texts = [c.content for c in chunks]
            vectors = await embeddings.aembed_documents(texts)

            for chunk, vector in zip(chunks, vectors):
                chunk.embedding = vector

            await db.commit()
            processed += len(chunks)
            logger.info(f"Re-embedded {processed}/{total} chunks")

        logger.info(f"Done. Re-embedded {processed} chunks total.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reembed_all())
