"""Shared fixtures.

Unit tests exercise pure domain logic (no database / Redis needed). The API smoke tests
(`tests/test_api_smoke.py`) run against a live stack when `E2E_BASE_URL` is set, e.g.

    E2E_BASE_URL=http://localhost:8000 pytest -q tests/test_api_smoke.py

and are skipped otherwise, so `make test` stays fast and hermetic.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
for p in (str(REPO), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("IMAGE_PROVIDER", "mock")
os.environ.setdefault("TTS_PROVIDER", "mock")


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    url = os.environ.get("E2E_BASE_URL")
    if not url:
        pytest.skip("E2E_BASE_URL not set - live API smoke tests skipped")
    return url.rstrip("/")
