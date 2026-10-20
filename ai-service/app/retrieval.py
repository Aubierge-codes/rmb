"""Retrieve passages and decide whether the answer is actually grounded in the documents."""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

from .config import settings
from .embeddings import content_tokens, embed
from .store import Chunk, get_store

log = logging.getLogger("rmb.retrieval")

# If the question asks for fees / timelines, the retrieved text must actually contain such figures.
# This stops the bot answering "what is the fee?" with unrelated text about the licence.
CRITICAL = [
    ("fees or costs", r"\b(fees?|costs?|prices?|how much|charges?)\b",
     r"\b(fees?|charges?|rwf|frw|payable|payment|royalt\w+|tax(es)?)\b"),
    ("timelines or deadlines", r"\b(deadlines?|timelines?|how long|processing time|turnaround|how many days|time ?frame)\b",
     r"\b(\d+|\w+ \(\d+\))\s*(working |calendar )?(days?|weeks?|months?|years?)\b"),
]


@dataclass
class Retrieval:
    passages: list[Chunk] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    grounded: bool = False
    missing: list[str] = field(default_factory=list)
    best_score: float = 0.0


def retrieve(question: str, previous_question: str | None = None) -> Retrieval:
    q = question
    if len(set(content_tokens(question))) < 3 and previous_question:
        q = previous_question + " " + question  # short follow-up: reuse the previous topic
    qt = set(content_tokens(q))
    store = get_store()
    cands = store.search(embed(q), 15)
    scored = []
    for ch, sim in cands:
        ct = set(content_tokens(ch.section_ref + " " + ch.text))
        cov = len(qt & ct) / len(qt) if qt else 0.0
        scored.append((0.4 * max(sim, 0.0) + 0.6 * cov, cov, ch))
    scored.sort(key=lambda x: -x[0])
    top = scored[: settings.top_k]
    r = Retrieval(passages=[t[2] for t in top], scores=[t[0] for t in top])
    if not top:
        log.info("retrieval_result store=%s candidates=0 query_tokens=%d reason=no_candidates", store.kind, len(qt))
        return r
    r.best_score = top[0][0]
    r.grounded = top[0][0] >= settings.min_score and top[0][1] >= 0.34
    if r.grounded:
        joined = " ".join(c.text for c in r.passages).lower()
        for label, q_re, p_re in CRITICAL:
            if re.search(q_re, q.lower()) and not re.search(p_re, joined):
                r.missing.append(label)
        if r.missing:
            r.grounded = False
    log.info(
        "retrieval_result store=%s candidates=%d selected=%d query_tokens=%d best_score=%.3f best_coverage=%.3f grounded=%s missing=%s",
        store.kind, len(cands), len(top), len(qt), r.best_score, top[0][1], r.grounded, ",".join(r.missing) or "none",
    )
    return r
