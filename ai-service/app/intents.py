"""Rule-based intent detection. Deliberately simple and predictable: emergencies and legal questions
must never depend on a language model deciding to behave."""
import re
import unicodedata

INFORMATIONAL = r"\b(what is|what are|what does|define|explain|policy|policies|law|laws|regulation|regulations|requirements?|procedure|prevent|prevention|training|guidelines?|standards?|plan)\b"

# Emergency terms are intentionally specific to an active mining incident.  A
# mining topic by itself (for example, a safety-plan question) must still reach
# ordinary document retrieval.
MINING_CONTEXT = {"mine", "mines", "miner", "miners", "mining", "quarry", "quarries", "underground", "shaft", "pit", "site"}
INCIDENT_TERMS = {
    "accident", "collapse", "collapsed", "cavein", "trapped", "injured", "injury", "bleeding",
    "explosion", "exploded", "fire", "burning", "gas", "gases", "leak", "leaking", "toxic",
    "poisoning", "landslide", "flood", "rescue", "emergency", "dead", "dying", "fatality",
}
IMMEDIATE_TERMS = {"help", "urgent", "urgently", "now", "happening", "happened", "emergency", "trapped", "injured", "bleeding", "collapse", "collapsed", "explosion", "exploded", "fire", "burning", "gas", "leak", "toxic", "dead", "dying"}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").lower().replace("licence", "license").strip()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+", _norm(text))


def _within_one_typo(token: str, term: str) -> bool:
    """Small edit-distance check for incident words, without fuzzy matching short words."""
    if token == term or len(token) < 5 or len(term) < 5 or abs(len(token) - len(term)) > 1:
        return token == term
    # A transposed pair (for example, "collpase") is a common mobile typo.
    if len(token) == len(term):
        for i in range(len(token) - 1):
            if token[i] != term[i] and token[i + 1] == term[i] and token[i] == term[i + 1] and token[:i] == term[:i] and token[i + 2:] == term[i + 2:]:
                return True
    previous = list(range(len(term) + 1))
    for i, left in enumerate(token, 1):
        current = [i]
        for j, right in enumerate(term, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
        if min(previous) > 1:
            return False
    return previous[-1] <= 1


def _matches(tokens: list[str], terms: set[str]) -> bool:
    return any(any(_within_one_typo(token, term) for term in terms) for token in tokens)


def is_emergency(text: str) -> bool:
    t = _norm(text)
    tokens = _tokens(t)
    incident = _matches(tokens, INCIDENT_TERMS)
    immediate = _matches(tokens, IMMEDIATE_TERMS)
    mining = _matches(tokens, MINING_CONTEXT)

    # "A miner faces an emergency" is intentionally caught, while an abstract
    # question about emergency policy is not.
    active_description = bool(re.search(r"\b(there is|there are|someone|people|a miner|at the|our)\b", t))
    if re.search(INFORMATIONAL, t) and not active_description and not re.search(r"\b(what should i do|help)\b", t):
        return False
    return incident and (mining or active_description) and (immediate or active_description)


LEGAL = [
    r"\binterpret", r"\blegal advice\b", r"\blegally\b", r"\blawsuit\b", r"\bsue\b", r"\bliable\b", r"\bliability\b",
    r"\bappeal\b", r"\bcourt\b", r"\bis it legal\b", r"\bam i allowed to ignore\b", r"\bloophole\b", r"\bwill i be prosecuted\b",
    r"\blawyer\b", r"\bmean legally\b", r"\bhow should the law\b", r"\bwhat does article .* mean\b",
]


def is_legal_interpretation(text: str) -> bool:
    t = _norm(text)
    return any(re.search(p, t) for p in LEGAL)


REPORT_MARK = r"\b(report|reporting|witness|witnessed|saw|seen|noticed|happening|going on|operating|there is|there are|i want to tell)\b"


def case_intent(text: str) -> str | None:
    """Returns a case type if the message is a request to log something, else None."""
    t = _norm(text)
    if re.search(r"\b(illegal|unlicensed|unauthori[sz]ed)\s+(mining|miners?|quarry|quarrying|mine|excavation)\b", t) and re.search(REPORT_MARK, t):
        return "illegal_mining"
    if re.search(r"\b(complain|complaint|grievance|grievances)\b", t) and not re.search(r"\b(how|what|where|procedure|process|can i)\b.*\b(complaint|grievance)\b.*\?$", t):
        return "grievance"
    if re.search(r"\b(request|schedule|book|arrange|set up|want|would like|like)\b.{0,40}\b(meeting|meet)\b", t) or re.search(r"\bmeet (with )?(rmb|an officer|someone|the team)\b", t):
        return "meeting_request"
    if re.search(r"\b(geological|geoscience|geology|survey)\b.{0,20}\b(data|map|maps|information)\b", t) and re.search(r"\b(request|access|get|obtain|need|want|download|where can|can i)\b", t):
        return "geo_data_request"
    if re.search(r"\b(status of my|my application|application status|license status|where is my application|check my application)\b", t):
        return "license_query"
    return None


GREETING = r"^(hi|hello|hey|good (morning|afternoon|evening)|muraho|bonjour|salut)\b[\s!.,]*$"


def is_greeting(text: str) -> bool:
    return bool(re.match(GREETING, _norm(text)))


def guess_case_type(question: str) -> str:
    t = _norm(question)
    if re.search(r"\b(export|traceab|certificat|customs|tantalum|tin|tungsten|gold)\b", t) and re.search(r"\b(export|traceab|customs|certificat)", t):
        return "export_traceability"
    if re.search(r"\b(license|application|permit|renew)", t):
        return "license_query"
    return "general_enquiry"
