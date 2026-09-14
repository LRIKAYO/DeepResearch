import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import database
from .documents import router as documents_router
from .knowledge_search import router as knowledge_router
from .projects import router as projects_router
from .research_sessions import router as research_sessions_router


def create_app() -> FastAPI:
    app = FastAPI()
    cors_origins = [
        origin.strip()
        for origin in os.getenv("RESEARCHFLOW_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-ResearchFlow-User-Id"],
        )

    app.include_router(projects_router)
    app.include_router(research_sessions_router)
    app.include_router(documents_router)
    app.include_router(knowledge_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            with database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            ) from None
        return {"status": "ok"}

    return app


app = create_app()
