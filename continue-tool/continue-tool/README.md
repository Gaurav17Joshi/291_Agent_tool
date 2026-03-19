# Continue

Run Continue on SWE-bench Lite tasks with:

- Runtime per run
- Peak CPU and peak RSS (memory)
- LLM wait vs generation timeline from `continue/.continue/logs/cn.log`
- Patch/file edit summary from model output
- Method comparison table across 6 model-routing strategies

## Important Warnings

- `timeline_processor.py` is currently unstable for some multi-step strategies and can fail intermittently across runs.
- In practice, those strategies often work when run separately again, but timeline parsing/reporting is not fully reliable yet.
- Anything other than `normal` can take a long time. Multi-step methods (`alternating`, `complexity`, and the 6-method reference-table run) are much slower than a single `normal` run.

## What Is In This Repo

Main entrypoints:

- `orchestrator.py`
- `run_reference_table_test.py`

Relavent modules:

- `run.py` - launches Continue CLI (`continue/extensions/cli/dist/cn.js`)
- `methods.py` - alternating + complexity strategies used by `orchestrator.py`
- `model_alteration_experiments.py` - 6-method experiment logic + token/cost aggregation
- `timeline_processor.py` - timeline extraction, peak CPU/RSS sampling, patch stats

Helpers Files:

- `install_dataset.py` - downloads/validates SWE-bench Lite via Hugging Face
- `download.py` - saves SWE-bench Lite locally to `./swe-bench-lite`

## Requirements

- Python 3.10+
- Node.js 18+
- Continue CLI build at `continue/extensions/cli/dist/cn.js`
- Continue config at `continue/.continue-debug/config.yaml`

Python packages:

```bash
pip install datasets psutil
```

## Continue Directory Expectations

The code assumes this structure exists:

- `continue/extensions/cli/dist/cn.js`
- `continue/.continue-debug/config.yaml`
- `continue/.continue/logs/cn.log` (created during runs)

If `continue/.continue-debug/config.yaml` is missing, runs will fail before invoking the model.


Auth sources:

- Primary: values in `continue/.continue-debug/config.yaml`
- Overrides via env vars: `CONTINUE_OPENAI_API_BASE`, `CONTINUE_OPENAI_API_KEY`

If env vars are set, `run.py` rewrites generated runtime config to use those values.

## Quick Start

1. Validate dataset access:

```bash
python install_dataset.py
```

2. Run one orchestrator strategy:

```bash
python orchestrator.py alternating 0
```

3. Run all 6 reference-table methods on one task:

```bash
python run_reference_table_test.py 0
```

If you omit task index for `run_reference_table_test.py`, it chooses a random SWE-bench Lite test item.

## Script Usage

### `orchestrator.py`

```bash
python orchestrator.py [alternating|complexity|normal] [task_index]
```

Defaults:

- mode: `alternating`
- task index: `0`

Modes:

- `alternating`: 3-step chain cycling models `gpt-4o -> gpt-4o-mini -> gpt-5.2`
- `complexity`: picks model from issue complexity (`gpt-4o-mini` or `gpt-5.2`)
- `normal`: single call using `gpt-5.2`

Printed outputs include:

- `(total_time, output, return_code)`
- `Peak CPU`
- `Peak RSS`
- patch/file summary from returned patch text
- timeline breakdown from `cn.log`

### `run_reference_table_test.py`

```bash
python run_reference_table_test.py [task_index]
```

Runs these methods from `model_alteration_experiments.py`:

- `baseline`
- `alternating`
- `router`
- `confidence`
- `phase`
- `tool_complexity`

Prints a markdown table:

- time (s)
- GPT-5 tokens
- GPT-5-mini tokens
- GPT-5 cost
- GPT-5-mini cost
- total cost
- total LLM calls

### Table Limitations

Running all methods with `run_reference_table_test.py` produces a useful comparison table, but it has important limitations:

- It is a single-task, single-run snapshot by default, so variance is high.
- `900s` entries usually indicate timeout ceiling effects, which makes direct time comparisons less fair.
- Token/cost values come from `cn.log` parsing and may be undercounted if log lines are missing or parse fallback is used.
- The table does not include a correctness metric (for example: tests passed, patch applied, or issue resolved).
- Multi-step strategies can behave inconsistently across runs due to timeline/log instability noted above.

## Runtime Controls (Environment Variables)

Used by `run.py`:

- `CONTINUE_TIMEOUT_SEC` (default `900`)
- `CONTINUE_MAX_RETRIES` (default `2`)
- `CONTINUE_RETRY_BACKOFF_SEC` (default `2`)
- `CONTINUE_OPENAI_API_BASE` (optional endpoint override)
- `CONTINUE_OPENAI_API_KEY` (optional API key override)

## Notes On Metrics

- CPU/RSS are sampled from the local Continue CLI process (`psutil`), then max values are reported.
- Timeline parsing reads `continue/.continue/logs/cn.log`.
- Token/cost accounting prefers `Stream complete` records, with a fallback parser for usage chunks.
- Patch stats parser supports both `git diff` format and `*** Update/Add/Delete File:` style patches.

## Known Behavior

- Model names differ across scripts.
- `orchestrator.py` strategies use `gpt-5.2`, `gpt-4o`, `gpt-4o-mini`.
- Reference-table methods use `gpt-5` and `gpt-5-mini`.
- Ensure your Continue config supports all model names you plan to run.

LLM Usage: LLM was used only to format and style the README. The implementation and design are mine.
