#!/usr/bin/env sh
set -e

# The DB is gated by Compose's service_healthy condition, so it's reachable here.
echo "Applying database migrations..."
alembic upgrade head

echo "Starting API server..."
exec uvicorn pragya_assistant.main:app --host 0.0.0.0 --port 8000
