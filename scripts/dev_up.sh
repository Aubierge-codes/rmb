#!/usr/bin/env bash
# Local mode without Docker: SQLite for cases, JSON file for the knowledge base.
# Usage: scripts/dev_up.sh [kb_path]     Chat+demo page: http://localhost:8000   Admin: http://localhost:8081/admin
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KB="${1:-$ROOT/ai-service/data/kb.json}"
export SERVICE_KEY="${SERVICE_KEY:-dev-service-key}"
export DEMO_ADMIN_PASSWORD="${DEMO_ADMIN_PASSWORD:-change-me-admin}"
export DEMO_OFFICER_PASSWORD="${DEMO_OFFICER_PASSWORD:-change-me-officer}"
(cd "$ROOT/case-service" && DB_DSN="${DB_DSN:-sqlite:$ROOT/case-service/data/cases.sqlite}" setsid nohup php -S 127.0.0.1:8081 -t public public/router.php > /tmp/rmb-php.log 2>&1 < /dev/null &)
(cd "$ROOT/ai-service" && KB_PATH="$KB" CASE_API_URL=http://127.0.0.1:8081 STATIC_DIR="$ROOT" setsid nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/rmb-api.log 2>&1 < /dev/null &)
sleep 3
echo "Chat API + mock RMB page: http://localhost:8000"
echo "Admin portal:             http://localhost:8081/admin  (admin / officer, passwords from env)"
