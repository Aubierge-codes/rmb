"""Client for the PHP case service. Failures are reported to the caller, never hidden."""
import hashlib
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("rmb.cases")


class CaseServiceError(Exception):
    pass


def _headers() -> dict:
    return {"X-Service-Key": settings.service_key, "Content-Type": "application/json"}


def create_case(case_type: str, summary: str, contact: str | None, anonymous: bool, excerpt: str) -> dict:
    if not settings.case_api_url:
        raise CaseServiceError("CASE_API_URL not configured")
    try:
        r = httpx.post(
            f"{settings.case_api_url}/api/v1/cases",
            headers=_headers(),
            json={"type": case_type, "summary": summary, "contact": contact, "anonymous": anonymous, "conversation_excerpt": excerpt},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.error("create_case failed: %s", exc)
        raise CaseServiceError(str(exc)) from exc


def log_unanswered(question: str, score: float, reason: str, session_id: str) -> None:
    if not settings.case_api_url:
        return
    try:
        # The unanswered-question report is useful for content review, but it
        # must not turn an arbitrary chat message into a contact-data log.
        safe_question = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email removed]", question[:1000])
        safe_question = re.sub(r"\+?\d[\d\s().-]{7,}\d", "[number removed]", safe_question)
        httpx.post(
            f"{settings.case_api_url}/api/v1/unanswered",
            headers=_headers(),
            json={"question": safe_question, "best_score": round(score, 3), "reason": reason,
                  "session_hash": hashlib.sha256(session_id.encode()).hexdigest()[:12]},
            timeout=5,
        )
    except Exception as exc:  # logging a gap must never break the chat
        log.warning("log_unanswered failed: %s", exc)
