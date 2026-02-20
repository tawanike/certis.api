from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
    )

    # Routers
    from src.routes.v1.api import api_router
    from src.auth.router import router as auth_router
    
    app.include_router(api_router, prefix=settings.API_V1_STR)
    app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])

    # Set all CORS enabled origins
    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Health Check
    @app.get("/health")
    def health_check():
        return {"status": "ok", "version": settings.VERSION}

    return app

app = create_app()
