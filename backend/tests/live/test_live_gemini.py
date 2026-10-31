"""Calls the REAL Gemini API with LLM_API_KEY from .env. Skipped unless LIVE_TESTS=1 and the key is set.

Run:  cd backend && LIVE_TESTS=1 .venv/bin/pytest tests/live/test_live_gemini.py -v
"""

import os

import pytest

from app.ai import features
from app.ai.client import LLMClient

pytestmark = pytest.mark.skipif(os.environ.get("LIVE_TESTS") != "1" or not os.environ.get("LLM_API_KEY"),
                                reason="set LIVE_TESTS=1 and LLM_API_KEY to call Gemini")


def test_gemini_answers():
    llm = LLMClient.from_settings()
    assert "ok" in llm.generate("Reply with the single word ok.", "ping").lower()


def test_gemini_drafts_a_valid_config_from_a_sample_response():
    llm = LLMClient.from_settings()
    text = ("Service: Acme Directory. Base URL https://api.acme.example/v2. Auth: Bearer token.\n"
            "GET /users returns a JSON list: [{\"id\": 7, \"login\": \"ada\", \"mail\": \"ada@acme.example\", \"active\": true}]")
    out = features.generate_config(llm, text)
    assert out["config"] is not None and not [e for e in out["errors"] if e["severity"] == "error"], out["attempts"]
