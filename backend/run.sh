#!/usr/bin/env bash
# EchoShield backend startup (Linux/macOS).
# Sets demo-safe defaults, then serves the API on http://localhost:${PORT}/docs
#
# Usage:
#   ./run.sh                    # port 8000, local-first Argo provider
#   PORT=9000 ./run.sh
#   ARGO_PROVIDER=auto ./run.sh # override any default via env

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$BACKEND_DIR")"

export DATA_ROOT="${DATA_ROOT:-$REPO_ROOT/data}"
export NETCDF_DATA_ROOT="${NETCDF_DATA_ROOT:-$DATA_ROOT/sample_netcdf}"
export ARGO_CACHE_DIR="${ARGO_CACHE_DIR:-$DATA_ROOT/argo_cache}"
export GLIDER_CACHE_DIR="${GLIDER_CACHE_DIR:-$DATA_ROOT/glider_cache}"

# Demo default: prefer cached local Argo profiles (no network needed).
export ARGO_PROVIDER="${ARGO_PROVIDER:-local}"

PORT="${PORT:-8000}"
HOSTADDR="${HOSTADDR:-0.0.0.0}"

echo "EchoShield backend"
echo "  DATA_ROOT         = $DATA_ROOT"
echo "  NETCDF_DATA_ROOT  = $NETCDF_DATA_ROOT"
echo "  ARGO_CACHE_DIR    = $ARGO_CACHE_DIR"
echo "  ARGO_PROVIDER     = $ARGO_PROVIDER"
echo "  http://localhost:$PORT/docs"

exec uv run --project "$BACKEND_DIR" uvicorn app.main:app --host "$HOSTADDR" --port "$PORT"
