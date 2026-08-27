#!/usr/bin/env bash
# One-command startup: backend (FastAPI) + frontend (Vite) together.
#
#   ./run.sh            start both, open http://localhost:5173
#   ./run.sh setup      create the venv, install everything, build claims.csv
#   ./run.sh pipeline   run the pipeline once from the CLI and write exports
#   ./run.sh test       run the test suite
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
cd "$ROOT"

setup() {
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r backend/requirements.txt
  (cd frontend && npm install --silent)
  (cd backend && "$PY" -m rq3.cli build-claims)
  echo
  echo "Setup complete."
  echo "Next: fill the RQ2 evidence labels in data/claims_evidence.csv, then ./run.sh"
}

case "${1:-serve}" in
  setup)    setup ;;
  test)     cd backend && exec "$PY" -m pytest tests/ -v ;;
  pipeline) cd backend && exec "$PY" -m rq3.cli run "${@:2}" ;;
  serve)
    [ -x "$PY" ] || { echo "No venv found — run ./run.sh setup first."; exit 1; }
    [ -f "$ROOT/data/claims.csv" ] || { echo "data/claims.csv missing — run ./run.sh setup"; exit 1; }

    # Pick the first free API port from RQ3_API_PORT (default 8000) upwards, so
    # an unrelated local server on 8000 does not silently break the frontend
    # proxy. The chosen port is handed to Vite through .env.local.
    API_PORT="${RQ3_API_PORT:-8000}"
    while lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; do
      echo "port $API_PORT is in use, trying $((API_PORT + 1))"
      API_PORT=$((API_PORT + 1))
    done
    UI_PORT="${RQ3_UI_PORT:-5173}"
    echo "VITE_API_PORT=$API_PORT" > frontend/.env.local

    cleanup() { kill 0 2>/dev/null || true; }
    trap cleanup EXIT INT TERM

    ( cd backend && "$PY" -m uvicorn rq3.api:app --host 127.0.0.1 --port "$API_PORT" ) &
    ( cd frontend && npm run dev -- --port "$UI_PORT" --strictPort ) &

    echo
    echo "  backend   http://127.0.0.1:$API_PORT/docs"
    echo "  frontend  http://localhost:$UI_PORT      <- open this"
    echo "  Ctrl-C to stop both."
    wait
    ;;
  *) echo "usage: ./run.sh [serve|setup|pipeline|test]"; exit 1 ;;
esac
