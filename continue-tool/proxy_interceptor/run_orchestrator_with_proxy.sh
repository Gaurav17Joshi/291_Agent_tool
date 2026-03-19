#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${LITELLM_PORT:-4000}"
HOST="${LITELLM_HOST:-127.0.0.1}"

export CONTINUE_OPENAI_API_BASE="${CONTINUE_OPENAI_API_BASE:-http://${HOST}:${PORT}/v1}"
export CONTINUE_OPENAI_API_KEY="${CONTINUE_OPENAI_API_KEY:-${LITELLM_MASTER_KEY:-}}"

if [ -z "${CONTINUE_OPENAI_API_KEY}" ]; then
  echo "Need proxy key."
  echo "Set LITELLM_MASTER_KEY or CONTINUE_OPENAI_API_KEY first."
  exit 1
fi

cd "${ROOT}"
python orchestrator.py "$@"
