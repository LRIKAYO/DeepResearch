from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import database
from .projects import router as projects_router
from .research_sessions import router as research_sessions_router


app = FastAPI()
app.include_router(projects_router)
app.include_router(research_sessions_router)


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
