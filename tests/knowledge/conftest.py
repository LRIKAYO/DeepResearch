"""Database-free knowledge tests.

``researchflow.knowledge.retrieval`` imports the ORM models and the Project
mapping because the SQL statement filters by Project and owner. Importing those
modules constructs a SQLAlchemy ``Engine``, which requires a database URL at
import time. These tests never open a connection; the URL below only lets engine
construction succeed so the ranking math can run without PostgreSQL.
"""

import os

os.environ.setdefault(
    "RESEARCHFLOW_DATABASE_URL",
    "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow",
)
