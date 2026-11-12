"""Retrieval evaluation tooling for ResearchFlow.

The package is intentionally import-safe offline: importing it never connects to
a database, a model provider, or the Product Backend. Live evaluation only
happens inside ``python -m evaluations.run_eval`` when ``--api`` is passed.
"""
