from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or not text.startswith("{"):
            continue
        try:
            events.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return events


def _iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _extract_usage(obj: Any) -> tuple[int, int]:
    in_total = 0
    out_total = 0

    def walk(x: Any) -> None:
        nonlocal in_total, out_total
        if isinstance(x, dict):
            for k, v in x.items():
                lk = k.lower()
                if isinstance(v, int):
                    if lk in {"prompt_tokens", "input_tokens"}:
                        in_total += v
                    elif lk in {"completion_tokens", "output_tokens"}:
                        out_total += v
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return in_total, out_total


def _extract_cost(obj: Any) -> float:
    total = 0.0

    def walk(x: Any) -> None:
        nonlocal total
        if isinstance(x, dict):
            for k, v in x.items():
                lk = k.lower()
                if isinstance(v, (int, float)) and lk in {"cost", "total_cost", "usd_cost", "price"}:
                    total += float(v)
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return total


def _extract_tokens_from_text(text: str | None) -> tuple[int, int]:
    if not text:
        return 0, 0
    in_total = 0
    out_total = 0
    for key in ("input_tokens", "prompt_tokens"):
        for match in re.finditer(rf'"{key}"\s*:\s*(\d+)', text):
            in_total += int(match.group(1))
    for key in ("output_tokens", "completion_tokens"):
        for match in re.finditer(rf'"{key}"\s*:\s*(\d+)', text):
            out_total += int(match.group(1))
    return in_total, out_total


def _extract_cost_from_text(text: str | None) -> float:
    if not text:
        return 0.0
    total = 0.0
    for key in ("total_cost", "usd_cost", "cost", "price"):
        for match in re.finditer(rf'"{key}"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text):
            try:
                total += float(match.group(1))
            except ValueError:
                continue
    return total


def _is_llm_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return any(
        token in u
        for token in [
            "/v1/chat/completions",
            "/v1/responses",
            "/v1/messages",
            "/v1/completions",
            "api.openai.com/v1/",
            "openrouter.ai/api/v1/",
            "anthropic.com/v1/",
            "googleapis.com/v1beta/models/",
        ]
    )


def parse_proxy_events(path: Path) -> dict[str, Any]:
    raw = load_jsonl(path)
    req_by_call: dict[int, dict[str, Any]] = {}
    resp_by_call: dict[int, dict[str, Any]] = {}

    for rec in raw:
        call_id = rec.get("call_id")
        if not isinstance(call_id, int):
            continue
        if rec.get("record_type") == "http_request":
            req_by_call[call_id] = rec
        elif rec.get("record_type") == "http_response":
            resp_by_call[call_id] = rec

    calls = []
    total_in = 0
    total_out = 0
    total_cost = 0.0
    llm_count = 0
    calls_with_cost = 0

    for call_id in sorted(set(req_by_call.keys()) | set(resp_by_call.keys())):
        req = req_by_call.get(call_id) or {}
        resp = resp_by_call.get(call_id) or {}
        url = req.get("url")
        is_llm = _is_llm_url(url)

        req_epoch = _iso_to_epoch(req.get("timestamp"))
        resp_epoch = _iso_to_epoch(resp.get("timestamp"))
        resp_start_epoch = _iso_to_epoch(resp.get("timestamp_start"))
        resp_end_epoch = _iso_to_epoch(resp.get("timestamp_end"))
        if isinstance(resp_end_epoch, (int, float)):
            resp_epoch = resp_end_epoch
        latency = None
        if req_epoch is not None and resp_epoch is not None:
            latency = max(0.0, resp_epoch - req_epoch)
        ttft_s = None
        if req_epoch is not None and resp_start_epoch is not None:
            ttft_s = max(0.0, resp_start_epoch - req_epoch)

        req_json = req.get("request_body_json")
        resp_json = resp.get("response_body_json")
        req_text = req.get("request_body_text")
        resp_text = resp.get("response_body_text")

        in_tokens_req, out_tokens_req = _extract_usage(req_json)
        in_tokens_resp, out_tokens_resp = _extract_usage(resp_json)
        in_tokens_text_req, out_tokens_text_req = _extract_tokens_from_text(req_text)
        in_tokens_text_resp, out_tokens_text_resp = _extract_tokens_from_text(resp_text)

        input_tokens = in_tokens_req + in_tokens_resp
        output_tokens = out_tokens_req + out_tokens_resp
        if input_tokens == 0 and output_tokens == 0:
            input_tokens = in_tokens_text_req + in_tokens_text_resp
            output_tokens = out_tokens_text_req + out_tokens_text_resp

        call_cost = _extract_cost(req_json) + _extract_cost(resp_json)
        if call_cost == 0.0:
            call_cost = _extract_cost_from_text(req_text) + _extract_cost_from_text(resp_text)

        if is_llm:
            llm_count += 1
            total_in += input_tokens
            total_out += output_tokens
            total_cost += call_cost
            if call_cost > 0:
                calls_with_cost += 1

        calls.append(
            {
                "call_id": call_id,
                "request": req,
                "response": resp,
                "request_epoch": req_epoch,
                "response_epoch": resp_epoch,
                "response_start_epoch": resp_start_epoch,
                "response_end_epoch": resp_end_epoch,
                "latency_s": latency,
                "ttft_s": ttft_s,
                "is_llm": is_llm,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": call_cost,
            }
        )

    return {
        "calls": calls,
        "count": llm_count,
        "token_guess": {
            "input_tokens": total_in,
            "output_tokens": total_out,
        },
        "cost_usd": total_cost,
        "cost_available": calls_with_cost > 0,
    }


def parse_monitor_events(path: Path) -> dict[str, Any]:
    raw = load_jsonl(path)

    run_start = None
    run_end = None
    root_pid = None
    samples = []
    file_events = []
    child_starts = []
    child_ends = []

    for rec in raw:
        kind = rec.get("record_type")
        ts = rec.get("timestamp_epoch")
        if not isinstance(ts, (int, float)):
            continue

        if kind == "monitor_run_start":
            run_start = float(ts)
            pid = rec.get("pid")
            if isinstance(pid, int):
                root_pid = pid
        elif kind == "monitor_run_end":
            run_end = float(ts)
        elif kind == "process_sample":
            samples.append(rec)
        elif kind == "file_event":
            file_events.append(rec)
        elif kind == "child_process_start":
            child_starts.append(rec)
        elif kind == "child_process_end":
            child_ends.append(rec)

    peak_cpu = 0.0
    peak_rss = 0
    for sample in samples:
        cpu = sample.get("cpu_percent")
        rss = sample.get("rss_bytes")
        if isinstance(cpu, (int, float)):
            peak_cpu = max(peak_cpu, float(cpu))
        if isinstance(rss, int):
            peak_rss = max(peak_rss, rss)

    shell_cmds = []
    test_cmds = []
    git_cmds = []
    test_cmd_re = re.compile(
        r"(^|\s)(pytest|py\.test|tox|nox|unittest|ruff|mypy|flake8)\b|"
        r"\bpython(\d+(\.\d+)?)?\s+-m\s+pytest\b|"
        r"\b(npm|pnpm|bun)\s+test\b"
    )

    for child in child_starts:
        cmdline = child.get("cmdline")
        if not isinstance(cmdline, list):
            continue
        cmd = " ".join(str(x) for x in cmdline).strip()
        if not cmd:
            continue
        low = cmd.lower()
        # Ignore the root launcher command; it may contain prompt text like "pytest".
        if "opencode run" in low:
            continue
        shell_cmds.append({"timestamp_epoch": child.get("timestamp_epoch"), "command": cmd})

        if "git " in low or low.startswith("git"):
            git_cmds.append({"timestamp_epoch": child.get("timestamp_epoch"), "command": cmd})
        if test_cmd_re.search(low):
            test_cmds.append({"timestamp_epoch": child.get("timestamp_epoch"), "command": cmd})

    return {
        "run_start_epoch": run_start,
        "run_end_epoch": run_end,
        "root_pid": root_pid,
        "samples": samples,
        "file_events": file_events,
        "child_starts": child_starts,
        "child_ends": child_ends,
        "summary": {
            "peak_cpu_percent": peak_cpu,
            "peak_rss_bytes": peak_rss,
            "shell_command_count": len(shell_cmds),
            "test_command_count": len(test_cmds),
            "git_command_count": len(git_cmds),
            "file_event_count": len(file_events),
            "child_process_end_count": len(child_ends),
        },
        "shell_commands": shell_cmds,
        "test_commands": test_cmds,
        "git_commands": git_cmds,
    }
