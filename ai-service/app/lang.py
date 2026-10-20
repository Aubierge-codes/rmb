"""Very small language detector (English / French / Kinyarwanda) for routing and ingestion filtering."""
import re

EN = set("the and of to in is shall be for with that by on or as are this any which not may have has from an it its their".split())
FR = set("le la les des du de et est pour par sur au aux une un que qui dans ou ne pas sont ce ces je vous nous avec comment quelle quel bonjour licence".split())
RW = set("ni mu ku na cyangwa kandi ibyo uwo iyo bya ya wa za ba cya rya mbere ikigo amategeko ubwo igihe muraho murakoze ndashaka uruhushya amabuye ese yego oya nabona gukora".split())


def detect_language(text: str) -> str:
    """Returns 'en', 'fr', 'rw', 'mixed' or 'unknown'."""
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿ]+", text.lower())
    if len(words) < 3:
        # very short: check for greeting-like markers only
        w = set(words)
        if w & {"muraho", "murakoze"}:
            return "rw"
        if w & {"bonjour", "salut", "merci"}:
            return "fr"
        return "en" if words else "unknown"
    hits = {"en": sum(w in EN for w in words), "fr": sum(w in FR for w in words), "rw": sum(w in RW for w in words)}
    total = sum(hits.values())
    if total < 2:
        return "unknown"
    best = max(hits, key=hits.get)
    if hits[best] / total < 0.6:
        return "mixed"
    return best
