import time
import uuid

TTL = 3600
MAX_SESSIONS = 5000
_sessions: dict[str, dict] = {}


def get_session(session_id: str | None) -> dict:
    now = time.time()
    if len(_sessions) > MAX_SESSIONS:
        for k in [k for k, v in _sessions.items() if now - v["seen"] > TTL]:
            _sessions.pop(k, None)
    if session_id and session_id in _sessions and now - _sessions[session_id]["seen"] < TTL:
        s = _sessions[session_id]
    else:
        sid = uuid.uuid4().hex
        s = {"id": sid, "history": [], "flow": None, "last_unanswered": None, "last_question": None, "seen": now}
        _sessions[sid] = s
    s["seen"] = now
    return s


def add_turn(s: dict, role: str, text: str) -> None:
    s["history"].append({"role": role, "text": text[:1500]})
    s["history"] = s["history"][-20:]
