#!/bin/bash
cd "$(dirname "$0")" || exit 1
mkdir -p data
if ! curl -fsS http://127.0.0.1:8767/api/status >/dev/null 2>&1; then
  nohup .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8767 > data/server.log 2>&1 &
  for i in {1..40}; do
    if curl -fsS http://127.0.0.1:8767/api/status >/dev/null 2>&1; then break; fi
    sleep .5
  done
fi
open http://127.0.0.1:8767
