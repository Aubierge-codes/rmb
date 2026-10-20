"""End-to-end check of the seven demo scenarios against a running stack.
   python scripts/e2e.py [chat_base_url] [admin_base_url]
Passes only if every scenario behaves as specified in the proposal (Section 5.1)."""
import re
import sys

import httpx

CHAT = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
ADMIN = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8081").rstrip("/")
ADMIN_PW = __import__("os").environ.get("DEMO_ADMIN_PASSWORD", "change-me-admin")
results = []


def check(name, cond, detail=""):
    cond = bool(cond)
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))


def say(sid, msg):
    r = httpx.post(f"{CHAT}/api/v1/chat", json={"session_id": sid, "message": msg}, timeout=30)
    r.raise_for_status()
    return r.json()


# 1 Investor: license types with sources, then meeting request creates a case
a = say(None, "What types of mining licenses are there?")
sid = a["session_id"]
check("1a investor answer is grounded with sources", a["grounded"] and len(a["sources"]) > 0 and bool(re.search(r"licen[cs]", a["answer"].lower())), a)
check("1b regulatory answer carries disclaimer", bool(a["disclaimer"]))
b = say(sid, "I would like to request a meeting with RMB")
check("1c meeting request asks for details", b["action"] == "collect_info", b)
c = say(sid, "Next week Tuesday or Wednesday, jane.investor@example.com")
check("1d meeting case created with reference", c["action"] == "case" and re.match(r"RMB-\d{6}-[A-Z0-9]{5}$", c["case_reference"] or ""), c)
meeting_ref = c["case_reference"]

# 2 Exporter: honest about what is not covered
a = say(None, "What are the fees for an exploration license?")
check("2a fee question is NOT answered from unrelated text", a["grounded"] is False and "fees" in a["answer"].lower(), a)
check("2b offers to create a case", "Create a case for this question" in a["quick_replies"])
sid2 = a["session_id"]
b = say(sid2, "Create a case for this question")
check("2c case flow starts", b["action"] == "collect_info", b)
c = say(sid2, "No, I will use the reference number")
check("2d case created without contact", c["action"] == "case" and c["case_reference"], c)

# 3 ASM miner
a = say(None, "How does a cooperative register and what safety training is needed?")
check("3 ASM answer is grounded or honestly identifies a knowledge gap",
      (a["grounded"] and any("Article" in s["section"] for s in a["sources"])) or
      (not a["grounded"] and "verified documents currently loaded" in a["answer"]), a)

# 4 Community member: grievance with anonymity
a = say(None, "I want to file a complaint about dust from a mine near my village")
sid4 = a["session_id"]
check("4a grievance offers anonymity", a["action"] == "collect_info" and "Stay anonymous" in a["quick_replies"], a)
b = say(sid4, "Stay anonymous")
check("4b grievance case with reference", b["action"] == "case" and b["case_reference"], b)
griev_ref = b["case_reference"]

# 4b illegal mining report, anonymous, with contact details typed earlier must be redacted server-side
a = say(None, "I want to report illegal mining happening at the river, call me on +250 788 123 456")
sid5 = a["session_id"]
b = say(sid5, "Stay anonymous")
check("4c illegal mining anonymous case", b["action"] == "case" and "anonymous" in b["answer"].lower(), b)
illegal_ref = b["case_reference"]

# 5 Legal question: decline + handover
a = say(None, "Can you interpret Article 3 legally for my company?")
check("5a legal question declined with disclaimer", a["disclaimer"] and "cannot interpret" in a["answer"].lower(), a)
b = say(a["session_id"], "No, I will use the reference number")
check("5b handed over as case to legal unit", b["action"] == "handover" and "Legal" in (b["routed_to"] or ""), b)

# 6 Emergency
a = say(None, "There has been a collapse at the mine and people are trapped")
check("6 emergency shows contacts immediately", a["action"] == "emergency" and len(a["emergency_contacts"]) >= 2 and not a["sources"], a)
a = say(None, "What are the requirements for a mine safety plan?")
check("6b informational safety question is not treated as an emergency", a["action"] != "emergency", a)

# language handling and out-of-scope
a = say(None, "Quelle est la licence pour exploiter une mine?")
check("L French gets honest English-only notice", "English only" in a["answer"], a)
a = say(None, "What is the weather like in Kigali today?")
check("O out-of-scope not answered from documents", a["grounded"] is False, a)

# 7 Admin view
s = httpx.Client(base_url=ADMIN, follow_redirects=True)
r = s.post("/admin/login", data={"username": "admin", "password": "wrong"})
check("7a wrong password rejected", "Sign-in failed" in r.text)
r = s.post("/admin/login", data={"username": "admin", "password": ADMIN_PW})
check("7b admin signs in", "Cases" in r.text and "Sign-in failed" not in r.text)
r = s.get("/admin/cases")
check("7c case list shows created cases", meeting_ref in r.text and griev_ref in r.text)
r = s.get(f"/admin/case?ref={illegal_ref}")
check("7d anonymous case stores no contact", "no contact stored" in r.text and "788" not in r.text, r.text[:300])
r = s.get("/admin/unanswered")
check("7e unanswered report lists the gap questions", "fees" in r.text.lower() and "weather" in r.text.lower())
r = s.get("/admin/review")
check("7f content review list reachable for admin", r.status_code == 200 and "Content review" in r.text)
unauth = httpx.post(f"{ADMIN}/api/v1/cases", json={"summary": "x"})
check("7g case API rejects calls without the service key", unauth.status_code == 401)
o = httpx.Client(base_url=ADMIN, follow_redirects=True)
o.post("/admin/login", data={"username": "officer", "password": __import__("os").environ.get("DEMO_OFFICER_PASSWORD", "change-me-officer")})
check("7h officer role cannot open admin-only pages", o.get("/admin/review").status_code == 403)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
