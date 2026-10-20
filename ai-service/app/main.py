"""RMB AI Chatbot: chat API (FastAPI)."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import case_client, flows, intents
from .config import settings
from .lang import detect_language
from .llm import generate_answer
from .retrieval import retrieve
from .sessions import add_turn, get_session
from .store import get_store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rmb.chat")
PH = flows.PH

app = FastAPI(title="RMB AI Chatbot API", version="0.1.0-prototype")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"], max_age=600,
)

_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path == "/api/v1/chat" and request.method == "POST":
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
        q, now = _hits[ip], time.time()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_min:
            return JSONResponse({"detail": "Too many messages. Please wait a moment."}, status_code=429)
        q.append(now)
    return await call_next(request)


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=1000)
    language: str | None = "en"


def _sources(passages) -> list[dict]:
    out = []
    for i, c in enumerate(passages[:3], 1):
        snippet = c.text.strip().replace("\n", " ")
        out.append({"n": i, "title": c.doc_title, "section": c.section_ref, "page": c.page, "url": c.source_url,
                    "category": c.category, "snippet": snippet[:240] + ("..." if len(snippet) > 240 else "")})
    return out


def _finalise(session: dict, res: dict, **extra) -> dict:
    res = {**res, **extra}
    add_turn(session, "assistant", res["answer"])
    return {"session_id": session["id"], "language": "en", "placeholder_notice": PH["notice"], "grounded": res.pop("grounded", False), **res}


def _answer(session: dict, message: str) -> dict:
    prev = session.get("last_question")
    r = retrieve(message, prev)
    if not r.grounded:
        reason = "missing:" + ",".join(r.missing) if r.missing else "no_match"
        log.info("chat_fallback reason=%s best_score=%.3f passages=%d", reason, r.best_score, len(r.passages))
        case_client.log_unanswered(message, r.best_score, reason, session["id"])
        session["last_unanswered"] = message
        text = PH["not_found_partial"].format(missing=" and ".join(r.missing)) if r.missing else PH["not_found"]
        text += " Would you like me to create a demonstration case for this question?"
        return _finalise(session, flows._result(text, quick_replies=["Create a case for this question", "Ask something else"],
                                                sources=_sources(r.passages) if r.missing else []), grounded=False)
    session["last_question"] = message
    text = generate_answer(message, r.passages)
    if text is None:  # the model judged the passages insufficient
        log.info("chat_fallback reason=model_insufficient best_score=%.3f passages=%d", r.best_score, len(r.passages))
        case_client.log_unanswered(message, r.best_score, "model_insufficient", session["id"])
        session["last_unanswered"] = message
        return _finalise(session, flows._result(PH["not_found"] + " Would you like me to create a demonstration case for this question?",
                                                quick_replies=["Create a case for this question", "Ask something else"]), grounded=False)
    regulatory = any(c.category == "regulatory" for c in r.passages[:3])
    return _finalise(session, flows._result(text, sources=_sources(r.passages), disclaimer=PH["disclaimer"] if regulatory else None), grounded=True)


@app.post("/api/v1/chat")
def chat(req: ChatRequest):
    session = get_session(req.session_id)
    message = req.message.strip()
    add_turn(session, "user", message)

    # 1. Emergencies first, always, and never via a model
    if intents.is_emergency(message):
        log.info("chat_emergency_detected")
        session["flow"] = None
        return _finalise(session, flows._result(PH["emergency_message"], action="emergency", emergency_contacts=PH["emergency_contacts"]))

    # 2. Continue an active case-collection flow
    if session["flow"]:
        return _finalise(session, flows.handle_flow(session, message))

    # 3. Quick replies after a "not found" answer
    low = message.lower()
    if low == "create a case for this question" and session.get("last_unanswered"):
        q = session["last_unanswered"]
        return _finalise(session, flows.start_flow(session, intents.guess_case_type(q), q))
    if low == "ask something else":
        return _finalise(session, flows._result("Sure. What would you like to know?"))

    # 4. Language: this demo is English only
    lang = detect_language(message)
    if intents.is_greeting(message):
        res = flows._result(PH["welcome"] + ("\n\n" + PH["language_notice"] if lang in ("fr", "rw") else ""))
        return _finalise(session, res)
    if lang in ("fr", "rw"):
        return _finalise(session, flows._result(PH["language_notice"]))

    # 5. Legal interpretation: decline and hand over
    if intents.is_legal_interpretation(message):
        intro = "I cannot interpret the law or give legal advice. I can describe what the documents say, but only RMB's legal unit can advise on how they apply to you."
        return _finalise(session, flows.start_flow(session, "legal_question", message, intro=intro, disclaimer=PH["disclaimer"]))

    # 6. Requests that should become cases
    ctype = intents.case_intent(message)
    if ctype:
        return _finalise(session, flows.start_flow(session, ctype, message))

    # 7. Answer from the knowledge base
    return _answer(session, message)


@app.get("/api/v1/health")
def health():
    store = get_store()
    return {"status": "ok", "knowledge_base": store.kind, "chunks": store.count(), "llm": settings.llm_provider if (settings.llm_provider == "extractive" or (settings.llm_provider == "gemini" and settings.gemini_api_key) or (settings.llm_provider == "anthropic" and settings.anthropic_api_key)) else "extractive (no API key set)",
            "case_service": bool(settings.case_api_url)}


# Local mode only: serve the mock RMB page and widget from the same origin.
if settings.static_dir and Path(settings.static_dir).exists():
    root = Path(settings.static_dir)

    @app.get("/widget.js")
    def widget():
        return FileResponse(root / "widget" / "widget.js", media_type="application/javascript")

    app.mount("/", StaticFiles(directory=root / "web", html=True), name="web")
