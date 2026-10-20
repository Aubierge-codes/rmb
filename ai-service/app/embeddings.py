"""Prototype embedding: deterministic hashed bag-of-words (unigrams + bigrams), 512 dimensions.

Needs no model download or API key, so the demo runs anywhere. It is deliberately simple.
For production, swap `embed()` for a real embedding model and change the vector size in db/init.sql.
"""
import hashlib
import math
import re
from collections import Counter

import numpy as np

DIM = 512
STOP = set(
    """a an the and or of to in on for with by at from as is are was were be been being this that these those it its
    what which who whom how when where why do does did can could should would will shall may might must i you we they he she
    me my our your their them us about into than then there here also any all some such not no if so
    tell give please need want know like get""".split()
)


def stem(tok: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "es", "ed", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            tok = tok[: -len(suf)]
            break
    if len(tok) > 3 and tok.endswith("e"):
        tok = tok[:-1]
    return tok


def content_tokens(text: str) -> list[str]:
    text = text.lower().replace("licence", "license")
    toks = re.findall(r"[a-z0-9]+", text)
    return [stem(t) for t in toks if t not in STOP and len(t) > 1]


def _h(s: str) -> int:
    return int.from_bytes(hashlib.md5(s.encode()).digest()[:4], "little")


def embed(text: str) -> np.ndarray:
    toks = content_tokens(text)
    feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
    v = np.zeros(DIM, dtype=np.float32)
    for f, c in Counter(feats).items():
        h = _h(f)
        v[h % DIM] += (1.0 if (h >> 20) & 1 else -1.0) * (1 + math.log(c))
    n = float(np.linalg.norm(v))
    return v / n if n else v
