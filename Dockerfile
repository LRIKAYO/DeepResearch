# ResearchFlow development image.
#
# One image serves both Python services described in docker-compose.yml:
#   * backend -> default CMD (uvicorn researchflow.backend.app:app on :8000)
#   * agent   -> compose overrides the command with `langgraph dev --port 2024`
#
# No secrets are baked in. Runtime configuration is supplied by the environment
# (docker-compose passes it through with `env_file: .env`).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies are declared in pyproject.toml: `backend` (FastAPI, SQLAlchemy,
# psycopg, alembic, pgvector) and `dev` (langgraph CLI/API, pytest).
COPY pyproject.toml ./
COPY src ./src

# `langgraph dev` reads langgraph.json from the working directory, so the agent
# service needs it in the image.
COPY langgraph.json ./

RUN pip install --upgrade pip \
    && pip install -e ".[backend,dev]"

EXPOSE 8000 2024

# Default process: the FastAPI backend. The agent service overrides this.
CMD ["uvicorn", "researchflow.backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
