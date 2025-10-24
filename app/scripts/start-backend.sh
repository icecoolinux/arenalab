#!/bin/bash
cd /app/backend
if [ "$BACKEND_MODE" = "dev" ]; then
    exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
else
    exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
fi
