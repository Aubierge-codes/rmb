"""Case-collection dialogue: asks only what is needed, offers anonymity for sensitive reports, then creates a case."""
from __future__ import annotations

import json
import re

from . import case_client

from .config import settings

with open(settings.placeholders_path, encoding="utf-8") as _f:
    PH = json.load(_f)

EMAIL = r"[\w.+-]+@[\w-]+\.[\w.-]+"
PHONE = r"\+?\d[\d\s().-]{7,}\d"

SPECS = {
    "grievance": {"label": "complaint or grievance", "steps": ["contact_choice", "contact_text"], "anon": True},
    "illegal_mining": {"label": "report of illegal mining", "steps": ["contact_choice", "contact_text"], "anon": True},
    "legal_question": {"label": "question for the legal unit", "steps": ["contact_choice", "contact_text"], "anon": False},
    "export_traceability": {"label": "export or traceability enquiry", "steps": ["contact_choice", "contact_text"], "anon": False},
    "general_enquiry": {"label": "enquiry", "steps": ["contact_choice", "contact_text"], "anon": False},
    "meeting_request": {"label": "meeting request", "steps": ["details"],
                        "prompt": "Please tell me your preferred dates or times, and an email address or phone number where the investment promotion team can reach you."},
    "geo_data_request": {"label": "geological data request", "steps": ["details"],
                         "prompt": "Please tell me which area, mineral or type of geological data you need, and an email address or phone number where the geology team can reach you."},
    "license_query": {"label": "licensing query", "steps": ["details"],
                      "prompt": "Please give your application reference (if you have one) and an email address or phone number so the licensing department can reply."},
}

QR_ANON = ["Stay anonymous", "Share my contact details"]
QR_CONTACT = ["Share my contact details", "No, I will use the reference number"]


def _result(answer: str, **kw) -> dict:
    return {"answer": answer, "sources": [], "disclaimer": None, "action": "none", "case_reference": None,
            "routed_to": None, "expected_response_time": None, "quick_replies": [], "emergency_contacts": [], **kw}


def start_flow(session: dict, case_type: str, summary: str, intro: str = "", disclaimer: str | None = None) -> dict:
    spec = SPECS[case_type]
    session["flow"] = {"type": case_type, "summary": summary, "step": 0, "data": {}}
    return _prompt(session, intro, disclaimer)


def _prompt(session: dict, intro: str = "", disclaimer: str | None = None) -> dict:
    flow = session["flow"]
    spec = SPECS[flow["type"]]
    step = spec["steps"][flow["step"]]
    pre = (intro + "\n\n") if intro else ""
    if step == "contact_choice":
        if spec["anon"]:
            text = pre + f"I can log this as a case ({spec['label']}). Reports like this can be sensitive, so you may stay anonymous. Would you like to remain anonymous, or share contact details so RMB can follow up?"
            return _result(text, action="collect_info", quick_replies=QR_ANON, disclaimer=disclaimer)
        text = pre + f"I can create a demonstration case ({spec['label']}). The routing shown is a placeholder and does not confirm delivery to RMB. Would you like to share contact details for the case record?"
        return _result(text, action="collect_info", quick_replies=QR_CONTACT, disclaimer=disclaimer)
    if step == "contact_text":
        return _result("Please type your name and an email address or phone number. You can type 'cancel' to stop.", action="collect_info", disclaimer=disclaimer)
    return _result(pre + spec["prompt"] + " You can type 'cancel' to stop.", action="collect_info", disclaimer=disclaimer)


def _finish(session: dict, anonymous: bool, contact: str | None) -> dict:
    flow = session["flow"]
    spec = SPECS[flow["type"]]
    summary = flow["summary"]
    if flow["data"].get("details"):
        summary += "\n\nDetails provided: " + flow["data"]["details"]
    excerpt = "\n".join(f"{t['role']}: {t['text']}" for t in session["history"][-10:])
    try:
        res = case_client.create_case(flow["type"], summary, None if anonymous else contact, anonymous, excerpt)
    except case_client.CaseServiceError:
        session["flow"] = None
        return _result("Sorry, I could not reach the case service just now, so no case was created. Please try again in a few minutes.")
    session["flow"] = None
    ref = res["reference"]
    note = " Your report is anonymous: no contact details were stored." if anonymous else ""
    extra = " If anyone is in immediate danger, please contact emergency services now." if flow["type"] == "illegal_mining" else ""
    text = (f"Thank you. The demonstration system created case {ref} ({spec['label']}). Placeholder routing: {res['routed_to']}. "
            f"Placeholder expected response: {res['expected_response_time']}. {PH['case_reference_notice']} Please keep this reference number.{note}{extra}")
    action = "handover" if flow["type"] == "legal_question" else "case"
    return _result(text, action=action, case_reference=ref, routed_to=res["routed_to"],
                   expected_response_time=res["expected_response_time"],
                   disclaimer=PH["disclaimer"] if flow["type"] == "legal_question" else None)


def handle_flow(session: dict, message: str) -> dict:
    flow = session["flow"]
    spec = SPECS[flow["type"]]
    t = message.lower().strip()
    if t in {"cancel", "stop", "never mind", "nevermind", "no case"}:
        session["flow"] = None
        return _result("Okay, I have not created a case. What else can I help you with?")
    step = spec["steps"][flow["step"]]
    if step == "contact_choice":
        has_contact = re.search(EMAIL, message) or re.search(PHONE, message)
        if "anonym" in t and spec["anon"]:
            return _finish(session, True, None)
        if has_contact:
            return _finish(session, False, message[:300])
        if re.match(r"^(no|skip|reference)", t) or "reference number" in t:
            return _finish(session, False, None)
        if re.search(r"\b(share|yes|contact|sure|ok|okay)\b", t):
            flow["step"] = spec["steps"].index("contact_text")
            return _prompt(session)
        return _prompt(session, "Sorry, I did not catch that.")
    if step == "contact_text":
        return _finish(session, False, message[:300])
    # details step
    flow["data"]["details"] = message[:1000]
    found = re.findall(EMAIL, message) + re.findall(PHONE, message)
    return _finish(session, False, ", ".join(found)[:300] if found else None)
