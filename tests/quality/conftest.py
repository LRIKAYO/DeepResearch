"""Test fixtures for the offline quality suite.

``tmp_path`` is pytest's built-in on any normal machine. Some restricted
sandboxes deny writes to the platform temp directory, so this module provides a
workspace-local fallback *only when* the platform temp is not writable. The
built-in fixture is left untouched everywhere else.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

_TMP_ROOT = Path(__file__).resolve().parent / "_tmp"


def _platform_temp_writable() -> bool:
    try:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "probe").write_text("ok", encoding="utf-8")
    except OSError:
        return False
    return True


if not _platform_temp_writable():

    @pytest.fixture
    def tmp_path():
        path = _TMP_ROOT / uuid.uuid4().hex
        path.mkdir(parents=True)
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)
            try:
                _TMP_ROOT.rmdir()
            except OSError:
                pass
