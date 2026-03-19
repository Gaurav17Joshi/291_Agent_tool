# Continue 

This repo runs Continue CLI on SWE-bench Lite tasks and captures runtime, CPU / RSS peaks, LLM wait + generation timeline from `cn.log`, patch/file edit summary, method comparison table (baseline, alternating, router, confidence, phase, tool_complexity)

---

## What this repo runs

Main runners:

- `orchestrator.py`
  - `alternating`
  - `complexity`
  - `normal` (single model, `gpt-5.2`)
- `run_reference_table_test.py`
  - picks a random SWE-bench Lite task (or fixed index)
  - runs all 6 methods
  - prints a table with time / tokens / cost / total calls

Relavent files:

- `run.py` — launches Continue CLI (`continue/extensions/cli/dist/cn.js`)
- `timeline_processor.py` — timeline + CPU/RSS + patch stats
- `model_alteration_experiments.py` — method logic + table metrics parsing

---

## Requirements

- Python 3.10+
- Node.js 18+
- Continue CLI build present at:
  - `continue/extensions/cli/dist/cn.js`
- OpenAI key configured either:
  - in `continue/.continue-debug/config.yaml` (`apiKey`)
  - or via env override (`CONTINUE_OPENAI_API_KEY`)

Python deps:

```bash
pip install datasets psutil
