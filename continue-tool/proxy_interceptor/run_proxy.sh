#!/usr/bin/env bash
set -e

# beginner-friendly alias script
bash "$(cd "$(dirname "$0")" && pwd)/run_orchestrator_with_proxy.sh" "$@"

