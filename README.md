# RMB AI Chatbot: prototype (Phase 1 demo)

A working vertical slice of the proposal: an embeddable chat widget, a grounded-answer API, a case-tracking service and an admin portal.
English only. Contacts, emergency numbers, routing units and response times are **placeholders** until RMB confirms them.

```
widget/widget.js      Embeddable chat widget (Shadow DOM, no dependencies)          Role 5
web/                  Mock RMB page + hostile-CSS isolation test page               Role 5
ai-service/           Python + FastAPI: chat API, retrieval, guardrails, ingestion  Roles 2, 3
case-service/         PHP: case API, routing table, admin portal (no TYPO3 needed)  Role 4
db/init.sql           PostgreSQL + pgvector knowledge base table                    Roles 2, 6
nginx/, docker-compose.yml, .env.example                                            Role 6
scripts/e2e.py        Runs the 7 demo scenarios against a running stack             Roles 1, 6
```

## 1. Run with Docker (the intended stack)
```bash
cp .env.example .env            # change the passwords and SERVICE_KEY
docker compose up -d --build
mkdir -p downloads
docker compose --profile tools run --rm ingest     # downloads and ingests the 6 RMB sources (needs internet)
```
Demo page: http://localhost:8088  |  Admin: http://localhost:8088/admin (users `admin` and `officer`)

## 2. Run without Docker (laptop mode)
Needs Python 3.12 and PHP 8.2+ with `pdo_sqlite`. Uses SQLite for cases and a JSON file for the knowledge base.
```bash
pip install -r ai-service/requirements.txt
(cd ai-service && python -m ingest.ingest --pdf-dir ../downloads)     # real RMB documents
scripts/dev_up.sh                                                     # chat + demo page :8000, admin :8081/admin
python scripts/e2e.py                                                 # 26 checks
```
Default demo passwords are `change-me-admin` / `change-me-officer` unless you set `DEMO_ADMIN_PASSWORD` / `DEMO_OFFICER_PASSWORD`.
The chat API allows 30 messages per minute per IP, so wait a minute between repeated `e2e.py` runs.

## 3. Embed in TYPO3 (later)
Paste into an HTML content element or the page template:
```html
<script src="https://HOST/widget.js" data-api="https://HOST/api/v1" data-lang="en" data-title="RMB Assistant" data-accent="#1f3864"></script>
```
Set `ALLOWED_ORIGINS` to the RMB site's origin. Check `web/conflict-test.html` to see the widget unaffected by hostile site CSS.

## 4. How answers stay grounded
1. Emergency messages are detected by rules first: contacts shown, no model call, no advice.
2. Legal interpretation requests are declined, a disclaimer is shown and a case is created for the legal unit.
3. Retrieval ranks document sections; if the best match is weak the bot says "I don't have that yet" and logs the question for the admin report.
4. Fee and timeline questions require fee or timeline wording in the retrieved text, otherwise they are treated as not covered.
5. `LLM_PROVIDER=extractive` (default) quotes the documents and needs no key. `gemini` (free tier via Google AI Studio, set `GEMINI_API_KEY`) and `anthropic` send only the retrieved passages to a model with strict instructions. If a provider fails or has no key, the bot falls back to extractive answers. Add other providers in `ai-service/app/llm.py`. Free-tier Gemini usage may be used by Google to improve its products, so use only public demo data until a paid or approved tier is agreed with RMB.

## 5. Known limitations (be upfront about these in the demo)
- **Not tested here:** the Docker stack, Postgres and pgvector paths. Everything else was tested in laptop mode (18 unit tests, 26 end-to-end checks, browser test of the widget). Run `docker compose up` once and the e2e script against port 8088 before the demo.
- **Real RMB documents were not ingested during development** (the build environment could not reach rmb.gov.rw). Tests used clearly labelled synthetic fixtures in `ai-service/tests/fixtures`. Never load those into a demo knowledge base.
- Embeddings are a simple hashed bag-of-words (no model download, no key) combined with keyword coverage. Replace `app/embeddings.py` with a real embedding model for better recall, and change the vector size in `db/init.sql`.
- Gazetted laws are usually trilingual. Chunks are language-tagged and only English is used. Check the ingest output for chunks tagged `mixed` and for OCR warnings on scanned PDFs.
- Law numbers come from file names and are shown as "to be confirmed". The geohazards page needs a manual re-run of ingestion to refresh.
- Intent detection is rule-based English. Emergency numbers (112, 912) are placeholders to confirm.
- PHP's built-in server and in-memory chat sessions are prototype choices. Production needs php-fpm, HTTPS, a session store, hosting and data-residency decisions, and a security review.
- No real personal data should be used. Anonymous cases have contact details and any emails or phone numbers in the text removed server-side.

## 6. Tests
```bash
pip install -r ai-service/requirements-dev.txt && (cd ai-service && python -m pytest tests -q)
```
