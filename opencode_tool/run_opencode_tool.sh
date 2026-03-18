#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
TASK_SELECTOR="${1:-all}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
PROXY_PORT="${PROXY_PORT:-8081}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is not set."
  echo "Export it first, for example: export OPENAI_API_KEY=\"your-key-here\""
  exit 1
fi

if command -v opencode >/dev/null 2>&1; then
  OPENCODE_CMD_DEFAULT="opencode"
elif command -v npx >/dev/null 2>&1; then
  OPENCODE_CMD_DEFAULT="npx opencode-ai@latest"
else
  echo "Neither \`opencode\` nor \`npx\` is available."
  echo "Install OpenCode first, or make npx available."
  exit 1
fi

export OPENCODE_CMD="${OPENCODE_CMD:-$OPENCODE_CMD_DEFAULT}"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

run_task() {
  local task_number="$1"
  echo "Running task ${task_number} with: ${OPENCODE_CMD}"
  python "$ROOT_DIR/orchestrator/run_task.py" \
    --task "$task_number" \
    --timeout "$TIMEOUT_SECONDS" \
    --proxy-port "$PROXY_PORT" \
    --opencode-cmd "$OPENCODE_CMD"
}

case "$TASK_SELECTOR" in
  6|7)
    run_task "$TASK_SELECTOR"
    ;;
  all)
    task6_status=0
    task7_status=0
    run_task 6 || task6_status=$?
    run_task 7 || task7_status=$?
    if [[ "$task6_status" -ne 0 || "$task7_status" -ne 0 ]]; then
      echo "One or more task runs failed."
      exit 1
    fi
    ;;
  *)
    echo "Usage: ./run_opencode_tool.sh [6|7|all]"
    exit 1
    ;;
esac
