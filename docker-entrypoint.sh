#!/bin/sh
set -eu

if ! python -c "from src.db import database_ready; raise SystemExit(0 if database_ready() else 1)"; then
    python -m src.data_pipeline
fi
python -m src.signals

exec streamlit run app/main.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
