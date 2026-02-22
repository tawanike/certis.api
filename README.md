# Certis Backend

FastAPI backend for the Certis patent drafting platform.

## Tech Stack

- **Framework**: FastAPI (async)
- **Database**: PostgreSQL + asyncpg, pgvector for embeddings, tsvector for full-text search
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **LLM**: Ollama (local) via LangChain
- **Agents**: LangGraph-based AI agents

## Module Structure

Domain-driven organization -- each domain has its own models, schemas, services, and routers:

```
src/
├── agents/         # LangGraph AI agents (claims, risk, QA, specs)
│   ├── base.py     # BaseAgent abstract class
│   ├── state.py    # Shared agent state
│   └── claims/     # Claims generation agent
├── artifacts/      # Generated outputs (briefs, claims, specifications)
├── auth/           # JWT authentication, RBAC, invitation-based registration, multi-tenancy
├── briefing/       # Patent brief upload and structure extraction
├── chat/           # Matter-specific conversational interface with SSE streaming
├── clients/        # Patent applicant management
├── core/           # WebSocket manager, shared infrastructure
├── documents/      # PDF upload, processing, chunking, hybrid search (semantic + FTS)
├── drafting/       # Claim graph generation, risk scoring, claim versioning
├── ingestion/      # PDF text extraction via PyPDF
├── llm/            # LLM factory (Ollama models for reasoning, chat, vision, embeddings)
├── matter/         # Core patent case entity, state machine, jurisdictions
├── routes/         # v1 API versioning, aggregates all domain routers
├── scripts/        # Utility scripts
├── shared/         # Base mixins (AuditMixin, UUIDMixin, TimestampMixin)
├── suggestions/    # AI-powered suggestions
├── workstreams/    # Workflow orchestration
├── config.py       # Pydantic settings (env-based config)
├── database.py     # Async engine, session factory
└── main.py         # FastAPI app factory
```

## API Routes

All routes are mounted under `/v1/`:

| Route | Module |
|---|---|
| `/v1/auth/*` | Authentication, registration, invitations |
| `/v1/matters/*` | Patent matters CRUD, state transitions |
| `/v1/matters/{id}/chat/*` | Matter-specific chat with RAG |
| `/v1/matters/{id}/documents/*` | Document upload, search |
| `/v1/matters/{id}/drafting/*` | Claim generation, risk scoring |
| `/v1/matters/{id}/briefing/*` | Brief analysis |
| `/v1/clients/*` | Client management |
| `/v1/suggestions/*` | AI suggestions |
| `/v1/ws/*` | WebSocket/SSE endpoints |

## Development

### Setup

```bash
uv sync
cp .env.example .env  # configure database, Ollama, etc.
```

### Run

```bash
uv run uvicorn src.main:app --port 8001 --reload
```

### Database

```bash
uv run alembic upgrade head                       # Apply migrations
uv run alembic revision --autogenerate -m "msg"   # Create migration
```

### Tests

```bash
uv run pytest                                     # All tests
uv run pytest tests/test_auth.py                  # Specific file
uv run pytest tests/test_auth.py::test_login -v   # Single test
```

Tests use pytest-asyncio in strict mode. All async fixtures and tests must be explicitly marked.

## Configuration

All config is via environment variables (or `.env` file). Key settings:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_SERVER` | `localhost` | Postgres host |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `POSTGRES_USER` | `postgres` | Postgres user |
| `POSTGRES_PASSWORD` | `postgres` | Postgres password |
| `POSTGRES_DB` | `certis` | Database name |
| `SECRET_KEY` | -- | JWT signing key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL_PRIMARY` | `gpt-oss:20b` | Primary reasoning model |
| `OLLAMA_MODEL_EMBEDDING` | `embeddinggemma` | Embedding model |

## Document Processing

Upload flow uses FastAPI `BackgroundTasks`:

1. `POST /v1/matters/{id}/documents` returns `202 Accepted` immediately
2. Background task: extract pages -> chunk text -> generate embeddings -> store
3. Client polls document status until `READY`

Search uses hybrid retrieval:
- Semantic search (pgvector cosine distance)
- Full-text search (PostgreSQL tsvector + GIN index)
- Reciprocal Rank Fusion (RRF) to merge results
- Page-number boosting when user references specific pages


