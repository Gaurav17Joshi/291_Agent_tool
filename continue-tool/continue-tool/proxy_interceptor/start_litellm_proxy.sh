#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="$ROOT/proxy_interceptor/litellm_config.yaml"
PORT="${LITELLM_PORT:-4000}"
HOST="${LITELLM_HOST:-127.0.0.1}"

if ! command -v litellm >/dev/null 2>&1; then
  echo "litellm not found."
  echo "Run: pip install 'litellm[proxy]'"
  exit 1
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "OPENAI_API_KEY is not set."
  exit 1
fi

if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
  echo "LITELLM_MASTER_KEY is not set."
  exit 1
fi

echo "Starting LiteLLM proxy on http://${HOST}:${PORT}"
echo "Config file: ${CFG}"

litellm --config "${CFG}" --host "${HOST}" --port "${PORT}"
