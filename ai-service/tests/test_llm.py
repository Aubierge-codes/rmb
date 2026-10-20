import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import llm
from app.config import settings
from app.store import Chunk

P = [Chunk("d", "Doc", "regulatory", "", "Article 2", 1, "en", "An exploration license authorises prospecting.")]


class R:
    def __init__(self, text): self._t = text
    def raise_for_status(self): pass
    def json(self): return {"candidates": [{"content": {"parts": [{"text": self._t}]}}]}


def test_gemini_answer_and_request_shape(monkeypatch):
    seen = {}
    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return R("An exploration license authorises prospecting [1].")
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setattr(settings, "llm_provider", "gemini"); monkeypatch.setattr(settings, "gemini_api_key", "k")
    out = llm.generate_answer("what is an exploration license?", P)
    assert "prospecting" in out and ":generateContent" in seen["url"] and seen["headers"]["x-goog-api-key"] == "k"
    assert "ONLY from the numbered passages" in seen["body"]["system_instruction"]["parts"][0]["text"]
    assert "key" not in seen["url"].lower().split("?")[-1]  # key goes in a header, never the URL


def test_gemini_insufficient_returns_none(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: R("INSUFFICIENT_CONTEXT"))
    monkeypatch.setattr(settings, "llm_provider", "gemini"); monkeypatch.setattr(settings, "gemini_api_key", "k")
    assert llm.generate_answer("q", P) is None


def test_gemini_failure_falls_back_to_extractive(monkeypatch):
    def boom(*a, **k): raise RuntimeError("quota exceeded")
    monkeypatch.setattr(llm.httpx, "post", boom)
    monkeypatch.setattr(settings, "llm_provider", "gemini"); monkeypatch.setattr(settings, "gemini_api_key", "k")
    assert "loaded RMB documents say" in llm.generate_answer("exploration license", P)
