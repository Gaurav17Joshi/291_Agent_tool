#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from file_changes import diff_snapshots, snapshot_tree, write_markdown
from monitor import RunMonitor
from parse_events import parse_monitor_events, parse_proxy_events
from report import write_llm_messages, write_run_summary
from timeline import build_timeline, write_timeline_outputs

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"
RUNS_DIR = ROOT / "runs"
REPORTS_DIR = ROOT / "reports"
PROXY_SCRIPT = ROOT / "proxy" / "mitm_capture.py"


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


def check_prerequisites(opencode_cmd: str) -> None:
    executable = shlex.split(opencode_cmd)[0] if shlex.split(opencode_cmd) else ""
    if not executable or shutil.which(executable) is None:
        raise RuntimeError(f"`{executable or opencode_cmd}` not found in PATH")
    if shutil.which("mitmdump") is None:
        raise RuntimeError("`mitmdump` not found in PATH")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")


def task6_prompt() -> str:
    return (
        "Fix the failing order pipeline. Ensure money units are consistent, "
        "discount/tax order follows spec, inventory reservations rollback on payment failure, "
        "and persistence remains consistent. Add type hints and docstrings, and update tests "
        "to validate success + rollback paths. Do not change public function names. "
        "Run the tests to verify."
    )


def task7_prompt() -> str:
    return (
        "Fix the failing account billing pipeline. Ensure money units are consistent, "
        "apply discount before tax, rollback ledger debits on payment/persistence failure, "
        "and keep cache/database persistence consistent. Add type hints and docstrings, "
        "and update tests to validate success + rollback paths. Do not change public "
        "function names. Run the tests to verify."
    )


def ensure_task_seed(task: int) -> Path:
    path = TASKS_DIR / f"task{task}"
    if not path.exists():
        raise RuntimeError(f"tasks/task{task} does not exist. Seed files are missing.")
    return path


def restore_task_from_buggy_seed(task: int) -> Path:
    src = TASKS_DIR / f"task{task}_buggy_seed"
    dst = TASKS_DIR / f"task{task}"
    if not src.exists():
        raise RuntimeError(f"tasks/task{task}_buggy_seed does not exist. Create buggy snapshot first.")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def start_proxy(run_dir: Path, task_name: str, trace_id: str, port: int) -> subprocess.Popen[str]:
    proxy_dir = run_dir / "proxy"
    proxy_dir.mkdir(parents=True, exist_ok=True)

    out_file = proxy_dir / "raw_http.jsonl"
    env = os.environ.copy()
    env["MITM_CAPTURE_OUT"] = str(out_file)
    env["MITM_TASK_NAME"] = task_name
    env["MITM_TRACE_ID"] = trace_id

    cmd = [
        "mitmdump",
        "-q",
        "-p",
        str(port),
        "-s",
        str(PROXY_SCRIPT),
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.0)
    if proc.poll() is not None:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"mitmdump failed to start: {stderr}")
    return proc


def stop_proxy(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def build_opencode_env(proxy_port: int) -> dict[str, str]:
    env = os.environ.copy()
    proxy = f"http://127.0.0.1:{proxy_port}"
    env["HTTP_PROXY"] = proxy
    env["HTTPS_PROXY"] = proxy
    env["NO_PROXY"] = "localhost,127.0.0.1"

    runtime_root = ROOT / ".runtime"
    (runtime_root / "xdg_data").mkdir(parents=True, exist_ok=True)
    (runtime_root / "xdg_config").mkdir(parents=True, exist_ok=True)
    (runtime_root / "xdg_cache").mkdir(parents=True, exist_ok=True)
    env["XDG_DATA_HOME"] = str(runtime_root / "xdg_data")
    env["XDG_CONFIG_HOME"] = str(runtime_root / "xdg_config")
    env["XDG_CACHE_HOME"] = str(runtime_root / "xdg_cache")

    ca = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
    if ca.exists():
        env["NODE_EXTRA_CA_CERTS"] = str(ca)
    return env


def run_opencode(
    task_dir: Path,
    prompt: str,
    files: list[str],
    run_dir: Path,
    proxy_port: int,
    timeout_s: int,
    extra_env: dict[str, str] | None = None,
    opencode_cmd: str = "opencode",
) -> tuple[int, bool, float, float]:
    opencode_dir = run_dir / "opencode"
    opencode_dir.mkdir(parents=True, exist_ok=True)
    events_path = opencode_dir / "events.jsonl"
    raw_log = opencode_dir / "raw.log"

    monitor_dir = run_dir / "monitor"
    monitor_dir.mkdir(parents=True, exist_ok=True)
    monitor_log = monitor_dir / "raw_monitor.jsonl"

    cmd = shlex.split(opencode_cmd) + ["run", prompt, "--format", "json", "--dir", str(task_dir)]
    model = os.environ.get("OPENCODE_MODEL")
    if model:
        cmd.extend(["-m", model])
    for f in files:
        cmd.extend(["-f", f])

    env = build_opencode_env(proxy_port)
    if extra_env:
        env.update(extra_env)

    with events_path.open("w", encoding="utf-8") as evf, raw_log.open("w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            cmd,
            cwd=str(task_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        monitor = RunMonitor(pid=proc.pid, task_dir=task_dir, out_path=monitor_log)
        monitor.start()

        timed_out = False
        start_epoch = monitor.start_epoch or time.time()

        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                logf.write(line)
                if line.lstrip().startswith("{"):
                    evf.write(line)
            if proc.poll() is not None:
                break
            if (time.time() - start_epoch) > timeout_s:
                timed_out = True
                proc.kill()
                break

        rc = proc.poll() if proc.poll() is not None else 1
        monitor.stop(timed_out=timed_out, return_code=rc)
        end_epoch = monitor.end_epoch or time.time()

    return rc, timed_out, start_epoch, end_epoch


def run_task(task: int, timeout_s: int, proxy_port: int, opencode_cmd: str) -> dict[str, Any]:
    tasks: dict[int, dict[str, Any]] = {
        6: {
            "name": "task6_order_pipeline",
            "prompt": task6_prompt(),
            "files": [
                "order_service.py",
                "pricing.py",
                "discounts.py",
                "inventory.py",
                "persistence.py",
                "test_order_flow.py",
            ],
        },
        7: {
            "name": "task7_account_billing_pipeline",
            "prompt": task7_prompt(),
            "files": [
                "account_service.py",
                "billing.py",
                "ledger.py",
                "notifier.py",
                "persistence.py",
                "test_account_flow.py",
            ],
        },
    }
    if task not in tasks:
        raise RuntimeError(f"Unsupported task {task}. Supported tasks: {sorted(tasks.keys())}")

    config = tasks[task]
    task_name = str(config["name"])
    task_dir = restore_task_from_buggy_seed(task)
    ensure_task_seed(task)
    prompt = str(config["prompt"])
    files = list(config["files"])

    run_id = f"{utc_now()}_{task_name}"
    run_dir = RUNS_DIR / run_id
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    trace_id = run_id
    before = snapshot_tree(task_dir)

    proxy_proc = start_proxy(run_dir=run_dir, task_name=task_name, trace_id=trace_id, port=proxy_port)
    try:
        rc, timed_out, _start_epoch, _end_epoch = run_opencode(
            task_dir=task_dir,
            prompt=prompt,
            files=files,
            run_dir=run_dir,
            proxy_port=proxy_port,
            timeout_s=timeout_s,
            opencode_cmd=opencode_cmd,
        )
    finally:
        stop_proxy(proxy_proc)

    after = snapshot_tree(task_dir)
    file_diff = diff_snapshots(before, after)
    (analysis_dir / "file_changes.json").write_text(json.dumps(file_diff, indent=2), encoding="utf-8")
    write_markdown(file_diff, analysis_dir / "file_changes.md")

    proxy_parsed = parse_proxy_events(run_dir / "proxy" / "raw_http.jsonl")
    monitor_parsed = parse_monitor_events(run_dir / "monitor" / "raw_monitor.jsonl")

    timeline = build_timeline(proxy_parsed, monitor_parsed)
    write_timeline_outputs(
        timeline,
        analysis_dir / "timeline.json",
        analysis_dir / "timeline.md",
    )

    write_llm_messages(
        proxy_parsed,
        analysis_dir / "llm_messages.json",
        analysis_dir / "llm_messages.md",
        analysis_dir / "HR_llm_messages.md",
    )

    success = rc == 0 and not timed_out
    summary_path = REPORTS_DIR / f"summary_{run_id}.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_run_summary(
        run_id=run_id,
        task_name=task_name,
        run_dir=run_dir,
        success=success,
        return_code=rc,
        timeline=timeline,
        report_path=summary_path,
    )

    summary = timeline.get("summary", {})
    return {
        "run_id": run_id,
        "task_name": task_name,
        "task_dir": str(task_dir),
        "run_dir": str(run_dir),
        "summary_report": str(summary_path),
        "return_code": rc,
        "timed_out": timed_out,
        "success": success,
        "duration_s": summary.get("duration_s"),
        "llm_calls": summary.get("llm_calls", 0),
        "llm_total_latency_s": summary.get("llm_total_latency_s", 0.0),
        "peak_cpu_percent": summary.get("peak_cpu_percent", 0.0),
        "peak_rss_mb": summary.get("peak_rss_mb", 0.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpenCode task with external profiling")
    parser.add_argument("--task", type=int, default=6, help="Task number to run (default: 6)")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per task in seconds")
    parser.add_argument("--proxy-port", type=int, default=8081, help="mitmproxy port")
    parser.add_argument(
        "--opencode-cmd",
        default=os.environ.get("OPENCODE_CMD", "opencode"),
        help="Command used to invoke OpenCode CLI (default: OPENCODE_CMD or `opencode`)",
    )
    args = parser.parse_args()

    check_prerequisites(args.opencode_cmd)
    result = run_task(
        task=args.task,
        timeout_s=args.timeout,
        proxy_port=args.proxy_port,
        opencode_cmd=args.opencode_cmd,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
