"""LLM adapter. The provider is not yet agreed with RMB, so everything goes through `generate_answer`.

- extractive : no model. Quotes the best sentences from the retrieved passages. Works offline.
- gemini     : sends only the retrieved passages to a Google Gemini model (free tier available in Google AI Studio).
- anthropic  : sends only the retrieved passages to a Claude model with strict grounding instructions.
Adding another provider = one more class with the same `answer()` signature.
"""
from __future__ import annotations

import logging
import re

import httpx

from .config import settings
from .embeddings import content_tokens
from .store import Chunk

log = logging.getLogger("rmb.llm")
INSUFFICIENT = "INSUFFICIENT_CONTEXT"

SYSTEM = (
    "You are the RMB information assistant for the Rwanda Mines, Petroleum and Gas Board. "
    "Answer ONLY from the numbered passages provided. Never invent fees, deadlines, thresholds or legal positions. "
    "If the passages do not contain the answer, reply with exactly " + INSUFFICIENT + ". "
    "Do not interpret the law or give legal advice; describe what the passages say. "
    "Be concise (under 150 words), plain English, and cite passages as [1], [2] after the statements they support."
)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;:])\s+(?=[A-Z0-9(])|\n{2,}", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 25]


class ExtractiveLLM:
    name = "extractive"

    def answer(self, question: str, passages: list[Chunk]) -> str:
        qt = set(content_tokens(question))
        blocks = []
        for i, ch in enumerate(passages[:3], 1):
            sents = _sentences(ch.text) or [ch.text]
            ranked = sorted(range(len(sents)), key=lambda j: -len(qt & set(content_tokens(sents[j]))))[:2]
            picked = " ".join(sents[j] for j in sorted(ranked))
            if len(picked) > 420:
                picked = picked[:417].rsplit(" ", 1)[0] + "..."
            blocks.append(f"[{i}] {picked}")
        return "Here is what the loaded RMB documents say:\n\n" + "\n\n".join(blocks)


class AnthropicLLM:
    name = "anthropic"

    def answer(self, question: str, passages: list[Chunk]) -> str:
        ctx = "\n\n".join(f"[{i}] ({c.doc_title}, {c.section_ref})\n{c.text}" for i, c in enumerate(passages, 1))
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": settings.llm_model,
                "max_tokens": 600,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": f"Passages:\n{ctx}\n\nQuestion: {question}"}],
            },
            timeout=30,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"]).strip()


class GeminiLLM:
    name = "gemini"

    def answer(self, question: str, passages: list[Chunk]) -> str:
        ctx = "\n\n".join(f"[{i}] ({c.doc_title}, {c.section_ref})\n{c.text}" for i, c in enumerate(passages, 1))
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key, "content-type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": f"Passages:\n{ctx}\n\nQuestion: {question}"}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
            },
            timeout=30,
        )
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()


def generate_answer(question: str, passages: list[Chunk]) -> str | None:
    """Returns answer text, or None when the model says the passages are insufficient."""
    provider = None
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        provider = GeminiLLM()
    elif settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        provider = AnthropicLLM()
    if provider:
        try:
            text = provider.answer(question, passages)
            if not text:
                raise ValueError("empty model response")
            return None if INSUFFICIENT in text else text
        except Exception as exc:  # fall back to extractive so the demo never dies on a provider error
            log.warning("LLM provider failed (%s); using extractive answer", exc)
    return ExtractiveLLM().answer(question, passages)
