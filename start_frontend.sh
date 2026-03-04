#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
streamlit run frontend/app.py --server.port 8501
