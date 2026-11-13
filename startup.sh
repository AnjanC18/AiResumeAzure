#!/bin/bash
# Azure App Service Linux startup script
PORT="${PORT:-${WEBSITES_PORT:-8000}}"
echo "[*] Starting AI Resume Screening MVP on port $PORT..."
gunicorn --bind "0.0.0.0:$PORT" --workers 2 --timeout 120 "app:app"

