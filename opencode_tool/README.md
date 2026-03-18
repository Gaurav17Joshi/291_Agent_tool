# OpenCode Evaluation Tool

This tool evaluates OpenCode on two debugging tasks:
- Task 6: order pipeline
- Task 7: account billing pipeline

For each run, the tool:
- restores the task to its buggy starting state
- runs OpenCode on the task
- captures LLM HTTP traffic through `mitmproxy`
- records process and file activity
- generates timelines, file-change summaries, and a markdown report

## Requirements

- Python 3.10 or newer
- `OPENAI_API_KEY` set in your shell
- OpenCode available either as `opencode` in `PATH`, or via `npx`

The script creates its own virtual environment and installs the required Python packages automatically.

## How to run

From inside this folder:

```bash
export OPENAI_API_KEY="your-key-here"
./run_opencode_tool.sh
```

This runs both Task 6 and Task 7.

To run a single task:

```bash
./run_opencode_tool.sh 6
./run_opencode_tool.sh 7
```

## Optional settings

You can override the default timeout, proxy port, or OpenCode command:

```bash
TIMEOUT_SECONDS=300 PROXY_PORT=8081 ./run_opencode_tool.sh all
OPENCODE_CMD="opencode" ./run_opencode_tool.sh 6
```

If `opencode` is not installed but `npx` is available, the script automatically falls back to `npx opencode-ai@latest`.

## Output files

Each run creates a new folder under `runs/<run_id>/` with:
- `opencode/events.jsonl`
- `opencode/raw.log`
- `proxy/raw_http.jsonl`
- `monitor/raw_monitor.jsonl`
- `analysis/timeline.json`
- `analysis/timeline.md`
- `analysis/llm_messages.json`
- `analysis/llm_messages.md`
- `analysis/HR_llm_messages.md`
- `analysis/file_changes.json`
- `analysis/file_changes.md`

A run summary is also written to:

```bash
reports/summary_<run_id>.md
```

## Notes

- Before each run, the tool restores Task 6 and Task 7 from their buggy seed versions so runs are reproducible.
- This folder only contains the Task 6 and Task 7 evaluation workflow.
