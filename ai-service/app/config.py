"""Runtime settings, read from environment variables (see .env.example)."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self) -> None:
        e = os.environ.get
        # Knowledge base: Postgres + pgvector when DATABASE_URL is set, otherwise a local JSON file.
        self.database_url = e("DATABASE_URL", "")
        self.kb_path = e("KB_PATH", str(BASE / "data" / "kb.json"))
        # Case service (PHP)
        self.case_api_url = e("CASE_API_URL", "").rstrip("/")
        self.service_key = e("SERVICE_KEY", "dev-service-key")
        # LLM adapter: "extractive" (no model, quotes the documents), "gemini" or "anthropic"
        self.llm_provider = e("LLM_PROVIDER", "extractive")  # extractive | gemini | anthropic
        self.gemini_api_key = e("GEMINI_API_KEY", "")
        self.gemini_model = e("GEMINI_MODEL", "gemini-2.5-flash")
        self.llm_model = e("LLM_MODEL", "claude-sonnet-5-5")
        self.anthropic_api_key = e("ANTHROPIC_API_KEY", "")
        # API behaviour
        self.allowed_origins = [o.strip() for o in e("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
        self.min_score = float(e("MIN_SCORE", "0.30"))
        self.top_k = int(e("TOP_K", "4"))
        self.rate_limit_per_min = int(e("RATE_LIMIT_PER_MIN", "30"))
        self.placeholders_path = e("PLACEHOLDERS_PATH", str(BASE / "data" / "placeholders.json"))
        self.static_dir = e("STATIC_DIR", "")  # local mode only: serve the mock page and widget


settings = Settings()
