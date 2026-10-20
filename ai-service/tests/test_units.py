import os, sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from app import intents
from app.lang import detect_language
from ingest.chunkers import chunk_articles, chunk_html, read_pdf_pages, tag_language

HERE = os.path.dirname(__file__)


@pytest.fixture(scope="module")
def kb(tmp_path_factory):
    from tests.make_fixture import make
    from app.config import settings
    from app import store
    from ingest.chunkers import chunk_pages
    make()
    settings.kb_path = str(tmp_path_factory.mktemp("kb") / "kb.json")
    store.reset_store_cache()
    s = store.get_store()
    for did, fn, kind in [("test-law", "test-law.pdf", "a"), ("test-prospectus", "test-prospectus.pdf", "p")]:
        pages = read_pdf_pages(os.path.join(HERE, "fixtures", fn))
        raw = tag_language(chunk_articles(pages) if kind == "a" else chunk_pages(pages))
        s.replace_document(did, [store.Chunk(did, did, "regulatory" if kind == "a" else "promotion", "", c["section_ref"], c["page"], c["language"], c["text"]) for c in raw])
    return s


@pytest.mark.parametrize("msg,expected", [
    ("There has been a collapse and people are trapped", True),
    ("Someone is injured, please help, there was an explosion", True),
    ("gas leak right now at the site", True),
    ("What are the requirements for a mine safety plan?", False),
    ("How do I prevent a spill?", False),
    ("What is the fire safety policy?", False),
    ("What should I do if a miner faces an emergency?", True),
    ("A miner is traped after a collpase, please help", True),
    ("Toxic gas leaking underground right now", True),
    ("There was an accident at the quarry and workers are injured", True),
    ("How can mining investors apply for a licence?", False),
])
def test_emergency(msg, expected):
    assert intents.is_emergency(msg) is expected


@pytest.mark.parametrize("msg,expected", [
    ("I want to file a complaint about noise", "grievance"),
    ("I want to report illegal mining near the lake", "illegal_mining"),
    ("What is the penalty for illegal mining?", None),
    ("I would like to request a meeting with RMB", "meeting_request"),
    ("Where can I get geological data? I need a map", "geo_data_request"),
    ("What is the status of my application?", "license_query"),
    ("What types of licenses exist?", None),
])
def test_case_intent(msg, expected):
    assert intents.case_intent(msg) == expected


def test_legal():
    assert intents.is_legal_interpretation("Can you interpret Article 3 legally?")
    assert not intents.is_legal_interpretation("What types of licenses exist?")


def test_language():
    assert detect_language("What types of licenses are granted under the law?") == "en"
    assert detect_language("Quelle est la licence pour exploiter une mine dans le pays?") == "fr"


def test_chunker_cites_articles(kb):
    refs = [c.section_ref for c in kb.chunks if c.doc_id == "test-law"]
    assert any(r.startswith("Article 2") for r in refs) and len(refs) == 8
    assert {c.language for c in kb.chunks if c.section_ref.startswith("Article 8")} == {"fr"}


def test_html_chunker():
    html = "<html><nav>skip me</nav><h2>Alerts</h2><p>Landslide monitoring information is published here for the public to read.</p><script>x()</script></html>"
    c = chunk_html(html)
    assert c and c[0]["section_ref"] == "Alerts" and "skip" not in c[0]["text"]


def test_retrieval_grounded_and_guards(kb):
    from app.retrieval import retrieve
    assert retrieve("What types of mining licenses are there?").grounded
    r = retrieve("What is the fee for an exploration license?")
    assert not r.grounded and "fees or costs" in r.missing
    assert not retrieve("What is the weather in Kigali today?").grounded
    assert not retrieve("How long does approval take for a license?").grounded


def test_chat_emergency_precedes_retrieval_and_model(monkeypatch):
    from app import main, sessions

    sessions._sessions.clear()
    monkeypatch.setattr(main, "retrieve", lambda *args: (_ for _ in ()).throw(AssertionError("retrieval must not run")))
    monkeypatch.setattr(main, "generate_answer", lambda *args: (_ for _ in ()).throw(AssertionError("model must not run")))
    response = main.chat(main.ChatRequest(message="A miner is traped after a collpase, help now"))

    assert response["action"] == "emergency"
    assert response["grounded"] is False
    assert response["sources"] == []
    assert all(contact["placeholder"] for contact in response["emergency_contacts"])
    assert "not verified" in response["answer"].lower()


def test_chat_greeting_and_honest_empty_kb_fallback(tmp_path, monkeypatch):
    from app import main, sessions, store
    from app.config import settings

    old_path = settings.kb_path
    try:
        settings.kb_path = str(tmp_path / "empty-kb.json")
        store.reset_store_cache()
        sessions._sessions.clear()
        monkeypatch.setattr(main.case_client, "log_unanswered", lambda *args: None)
        greeting = main.chat(main.ChatRequest(message="Hello"))
        fallback = main.chat(main.ChatRequest(message="What is the weather in Kigali today?"))
        assert "RMB information assistant" in greeting["answer"]
        assert fallback["grounded"] is False
        assert "verified documents currently loaded" in fallback["answer"]
        assert "Create a case for this question" in fallback["quick_replies"]
    finally:
        settings.kb_path = old_path
        store.reset_store_cache()


def test_chat_grounded_answer_has_synthetic_source(kb, monkeypatch):
    from app import main, sessions

    sessions._sessions.clear()
    monkeypatch.setattr(main.case_client, "log_unanswered", lambda *args: None)
    response = main.chat(main.ChatRequest(message="What types of mining licenses are there?"))
    assert response["grounded"] is True
    assert response["sources"]
    assert response["sources"][0]["section"].startswith("Article")


def test_case_flow_labels_demo_reference(monkeypatch):
    from app import flows

    session = {"history": [], "flow": None}
    flows.start_flow(session, "general_enquiry", "Synthetic test question")
    monkeypatch.setattr(flows.case_client, "create_case", lambda *args: {
        "reference": "RMB-260101-ABCDE", "routed_to": "Information desk (placeholder)",
        "expected_response_time": "5 working days (placeholder)",
    })
    response = flows.handle_flow(session, "No, I will use the reference number")
    assert response["case_reference"] == "RMB-260101-ABCDE"
    assert "demonstration system" in response["answer"]
    assert "placeholder" in response["answer"].lower()


def test_ingestion_failure_is_reported_without_chunks(tmp_path, monkeypatch):
    from ingest import ingest
    from app import store
    from app.config import settings

    sources = {"sources": [{"id": "synthetic-failure", "title": "SYNTHETIC TEST SOURCE", "category": "public_info", "kind": "web", "url": "https://example.invalid/fail"}]}
    source_file = tmp_path / "sources.json"
    source_file.write_text(json.dumps(sources), encoding="utf-8")
    old_path = settings.kb_path
    try:
        settings.kb_path = str(tmp_path / "kb.json")
        store.reset_store_cache()
        monkeypatch.setattr(ingest.httpx, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic download failure")))
        monkeypatch.setattr(sys, "argv", ["ingest", "--sources", str(source_file), "--pdf-dir", str(tmp_path / "downloads")])
        assert ingest.main() == 1
        assert store.get_store().count() == 0
    finally:
        settings.kb_path = old_path
        store.reset_store_cache()
