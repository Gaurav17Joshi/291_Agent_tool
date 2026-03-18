from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _fmt_s(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}s"


def _event_sort_key(event: dict[str, Any]) -> float:
    ts = event.get("timestamp_epoch")
    if isinstance(ts, (int, float)):
        return float(ts)
    return float("inf")


def build_timeline(proxy_parsed: dict[str, Any], monitor_parsed: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    run_start = monitor_parsed.get("run_start_epoch")
    run_end = monitor_parsed.get("run_end_epoch")
    root_pid = monitor_parsed.get("root_pid")

    for rec in monitor_parsed.get("file_events", []):
        events.append(
            {
                "source": "monitor",
                "type": f"file_{rec.get('event')}",
                "timestamp_epoch": rec.get("timestamp_epoch"),
                "path": rec.get("path"),
            }
        )

    for rec in monitor_parsed.get("child_starts", []):
        cmdline = rec.get("cmdline") if isinstance(rec.get("cmdline"), list) else []
        events.append(
            {
                "source": "monitor",
                "type": "child_process_start",
                "timestamp_epoch": rec.get("timestamp_epoch"),
                "command": " ".join(str(x) for x in cmdline).strip(),
                "pid": rec.get("pid"),
            }
        )
    for rec in monitor_parsed.get("child_ends", []):
        cmdline = rec.get("cmdline") if isinstance(rec.get("cmdline"), list) else []
        events.append(
            {
                "source": "monitor",
                "type": "child_process_end",
                "timestamp_epoch": rec.get("timestamp_epoch"),
                "command": " ".join(str(x) for x in cmdline).strip(),
                "pid": rec.get("pid"),
            }
        )

    if isinstance(run_start, (int, float)):
        events.append(
            {
                "source": "monitor",
                "type": "run_start",
                "timestamp_epoch": float(run_start),
                "pid": root_pid if isinstance(root_pid, int) else None,
            }
        )
    if isinstance(run_end, (int, float)):
        events.append({"source": "monitor", "type": "run_end", "timestamp_epoch": float(run_end)})

    llm_total_latency = 0.0
    llm_latency_count = 0
    llm_call_rows: list[dict[str, Any]] = []
    for call in proxy_parsed.get("calls", []):
        if not call.get("is_llm"):
            continue
        req_ts = call.get("request_epoch")
        first_tok_ts = call.get("response_start_epoch")
        resp_ts = call.get("response_epoch")
        call_id = call.get("call_id")
        if isinstance(req_ts, (int, float)):
            events.append(
                {
                    "source": "proxy",
                    "type": "llm_request_dispatch",
                    "timestamp_epoch": float(req_ts),
                    "call_id": call_id,
                }
            )
        if isinstance(resp_ts, (int, float)):
            events.append(
                {
                    "source": "proxy",
                    "type": "llm_response_complete",
                    "timestamp_epoch": float(resp_ts),
                    "call_id": call_id,
                    "status_code": (call.get("response") or {}).get("status_code"),
                }
            )
        if isinstance(first_tok_ts, (int, float)):
            events.append(
                {
                    "source": "proxy",
                    "type": "llm_first_token",
                    "timestamp_epoch": float(first_tok_ts),
                    "call_id": call_id,
                }
            )

        latency = call.get("latency_s")
        if isinstance(latency, (int, float)):
            llm_total_latency += float(latency)
            llm_latency_count += 1
        llm_call_rows.append(
            {
                "call_id": call_id,
                "request_epoch": req_ts,
                "first_token_epoch": first_tok_ts,
                "response_epoch": resp_ts,
                "latency_s": latency,
                "ttft_s": call.get("ttft_s"),
                "status_code": (call.get("response") or {}).get("status_code"),
                "input_tokens": int(call.get("input_tokens") or 0),
                "output_tokens": int(call.get("output_tokens") or 0),
                "cost_usd": float(call.get("cost_usd") or 0.0),
            }
        )

    events = sorted(events, key=_event_sort_key)

    t0_candidates = [
        e.get("timestamp_epoch")
        for e in events
        if isinstance(e.get("timestamp_epoch"), (int, float))
    ]
    t0 = min(t0_candidates) if t0_candidates else 0.0

    for evt in events:
        ts = evt.get("timestamp_epoch")
        if isinstance(ts, (int, float)):
            evt["t_s"] = max(0.0, float(ts) - t0)

    for row in llm_call_rows:
        req_ts = row.get("request_epoch")
        first_tok_ts = row.get("first_token_epoch")
        resp_ts = row.get("response_epoch")
        row["request_t_s"] = max(0.0, float(req_ts) - t0) if isinstance(req_ts, (int, float)) else None
        row["first_token_t_s"] = (
            max(0.0, float(first_tok_ts) - t0) if isinstance(first_tok_ts, (int, float)) else None
        )
        row["response_t_s"] = max(0.0, float(resp_ts) - t0) if isinstance(resp_ts, (int, float)) else None

    duration_s = None
    if isinstance(run_start, (int, float)) and isinstance(run_end, (int, float)):
        duration_s = max(0.0, float(run_end) - float(run_start))
    elif events and isinstance(events[0].get("timestamp_epoch"), (int, float)) and isinstance(events[-1].get("timestamp_epoch"), (int, float)):
        duration_s = max(0.0, float(events[-1]["timestamp_epoch"]) - float(events[0]["timestamp_epoch"]))

    first_llm_req = next((e for e in events if e.get("type") == "llm_request_dispatch"), None)
    first_req_t = first_llm_req.get("t_s") if first_llm_req else None

    operations = [
        {
            "id": 1,
            "name": "Process Bootstrap",
            "source": "monitor",
            "start_s": 0.0,
            "end_s": first_req_t,
            "note": "from run start to first observed LLM dispatch",
        },
        {
            "id": 2,
            "name": "Environment Provisioning",
            "source": "monitor",
            "start_s": None,
            "end_s": None,
            "note": "left as N/A per current scope",
        },
        {
            "id": 8,
            "name": "LLM Request Dispatch",
            "source": "proxy",
            "count": proxy_parsed.get("count", 0),
        },
        {
            "id": 10,
            "name": "LLM Generation (request->response complete)",
            "source": "proxy",
            "count": llm_latency_count,
            "total_s": llm_total_latency,
            "avg_s": (llm_total_latency / llm_latency_count) if llm_latency_count else None,
        },
        {
            "id": 12,
            "name": "Apply File Changes",
            "source": "monitor",
            "count": len([e for e in monitor_parsed.get("file_events", []) if e.get("event") == "change"]),
        },
        {
            "id": 13,
            "name": "File Creation",
            "source": "monitor",
            "count": len([e for e in monitor_parsed.get("file_events", []) if e.get("event") == "add"]),
        },
        {
            "id": 14,
            "name": "Shell Command Execution",
            "source": "monitor",
            "count": monitor_parsed.get("summary", {}).get("shell_command_count", 0),
        },
        {
            "id": 15,
            "name": "Git Commit",
            "source": "monitor",
            "count": monitor_parsed.get("summary", {}).get("git_command_count", 0),
        },
        {
            "id": 16,
            "name": "Test / Validation Execution",
            "source": "monitor",
            "count": monitor_parsed.get("summary", {}).get("test_command_count", 0),
        },
        {
            "id": 20,
            "name": "Cleanup & Teardown",
            "source": "monitor",
            "start_s": duration_s,
            "end_s": duration_s,
            "note": "run end marker",
        },
    ]

    summary = {
        "duration_s": duration_s,
        "llm_calls": proxy_parsed.get("count", 0),
        "llm_total_latency_s": llm_total_latency,
        "llm_avg_latency_s": (llm_total_latency / llm_latency_count) if llm_latency_count else None,
        "total_input_tokens": proxy_parsed.get("token_guess", {}).get("input_tokens", 0),
        "total_output_tokens": proxy_parsed.get("token_guess", {}).get("output_tokens", 0),
        "total_tokens": proxy_parsed.get("token_guess", {}).get("input_tokens", 0)
        + proxy_parsed.get("token_guess", {}).get("output_tokens", 0),
        "total_cost_usd": float(proxy_parsed.get("cost_usd", 0.0) or 0.0),
        "cost_available": bool(proxy_parsed.get("cost_available", False)),
        "monitor_file_events": monitor_parsed.get("summary", {}).get("file_event_count", 0),
        "monitor_shell_commands": monitor_parsed.get("summary", {}).get("shell_command_count", 0),
        "monitor_test_commands": monitor_parsed.get("summary", {}).get("test_command_count", 0),
        "monitor_git_commands": monitor_parsed.get("summary", {}).get("git_command_count", 0),
        "peak_cpu_percent": monitor_parsed.get("summary", {}).get("peak_cpu_percent", 0.0),
        "peak_rss_mb": round(monitor_parsed.get("summary", {}).get("peak_rss_bytes", 0) / (1024 * 1024), 2),
        "proxy_token_guess": proxy_parsed.get("token_guess", {}),
    }

    return {"summary": summary, "operations": operations, "events": events, "llm_calls": llm_call_rows}


def write_timeline_outputs(timeline: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")

    summary = timeline.get("summary", {})
    lines = ["# Execution Timeline (Monitor + Proxy)", "", "## Summary", ""]
    lines.append(f"- Duration: {_fmt_s(summary.get('duration_s'))}")
    lines.append(f"- LLM calls: {summary.get('llm_calls', 0)}")
    lines.append(f"- LLM total latency: {_fmt_s(summary.get('llm_total_latency_s'))}")
    lines.append(f"- LLM avg latency: {_fmt_s(summary.get('llm_avg_latency_s'))}")
    lines.append(f"- Input tokens (proxy): {summary.get('total_input_tokens', 0)}")
    lines.append(f"- Output tokens (proxy): {summary.get('total_output_tokens', 0)}")
    lines.append(f"- Total tokens (proxy): {summary.get('total_tokens', 0)}")
    if summary.get("cost_available"):
        lines.append(f"- Total cost (USD, proxy): ${summary.get('total_cost_usd', 0.0):.6f}")
    else:
        lines.append("- Total cost (USD, proxy): n/a (not present in captured responses)")
    lines.append(f"- File events: {summary.get('monitor_file_events', 0)}")
    lines.append(f"- Shell commands: {summary.get('monitor_shell_commands', 0)}")
    lines.append(f"- Test/validation commands: {summary.get('monitor_test_commands', 0)}")
    lines.append(f"- Git commands: {summary.get('monitor_git_commands', 0)}")
    lines.append(f"- Peak CPU%: {summary.get('peak_cpu_percent', 0.0):.2f}")
    lines.append(f"- Peak RSS (MB): {summary.get('peak_rss_mb', 0.0):.2f}")

    events = timeline.get("events", [])
    llm_calls = timeline.get("llm_calls", [])
    root_pid = next(
        (e.get("pid") for e in events if e.get("type") == "run_start" and isinstance(e.get("pid"), int)),
        None,
    )
    cmd_events = [e for e in events if e.get("type") == "child_process_start"]
    file_events = [e for e in events if str(e.get("type", "")).startswith("file_")]

    duration = summary.get("duration_s")
    first_llm_req = min(
        (row.get("request_t_s") for row in llm_calls if isinstance(row.get("request_t_s"), (int, float))),
        default=None,
    )

    def _t(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float)) else None

    def _short(text: str, limit: int = 90) -> str:
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def _key(t: float) -> float:
        return round(t, 6)

    events_by_time: dict[float, list[dict[str, Any]]] = {}
    for evt in events:
        t = _t(evt.get("t_s"))
        if t is None:
            continue
        events_by_time.setdefault(_key(t), []).append(evt)

    # Build real command intervals from explicit start/end events.
    cmd_starts: dict[int, list[tuple[float, str]]] = {}
    cmd_intervals: list[tuple[float, float, int, str]] = []
    has_cmd_end_events = any(e.get("type") == "child_process_end" for e in events)
    for evt in events:
        t = _t(evt.get("t_s"))
        pid = evt.get("pid")
        if t is None or not isinstance(pid, int):
            continue
        if evt.get("type") == "child_process_start":
            cmd = str(evt.get("command") or "").strip()
            cmd_starts.setdefault(pid, []).append((t, cmd))
        elif evt.get("type") == "child_process_end":
            queue = cmd_starts.get(pid) or []
            if queue:
                start_t, cmd = queue.pop(0)
                end_t = max(start_t, t)
                cmd_intervals.append((start_t, end_t, pid, cmd))

    if isinstance(duration, (int, float)) and has_cmd_end_events:
        for pid, queue in cmd_starts.items():
            for start_t, cmd in queue:
                cmd_intervals.append((start_t, float(duration), pid, cmd))
    elif isinstance(duration, (int, float)):
        # Backward compatibility for old runs where child_process_end was not captured.
        for pid, queue in cmd_starts.items():
            for start_t, cmd in queue:
                cmd_intervals.append((start_t, min(float(duration), start_t + 0.1), pid, cmd))
    cmd_intervals.sort(key=lambda x: (x[0], x[1]))

    llm_wait_intervals: list[tuple[float, float, int | None]] = []
    llm_gen_intervals: list[tuple[float, float, int | None, int]] = []
    for row in llm_calls:
        req = _t(row.get("request_t_s"))
        first = _t(row.get("first_token_t_s"))
        resp = _t(row.get("response_t_s"))
        if req is None or resp is None or resp <= req:
            continue
        call_id = row.get("call_id")
        out_tok = int(row.get("output_tokens") or 0)
        if first is not None and req < first < resp:
            llm_wait_intervals.append((req, first, call_id))
            llm_gen_intervals.append((first, resp, call_id, out_tok))
        else:
            llm_gen_intervals.append((req, resp, call_id, out_tok))
    llm_wait_intervals.sort(key=lambda x: (x[0], x[1]))
    llm_gen_intervals.sort(key=lambda x: (x[0], x[1]))

    # File changes are sampled; group nearby events into short write bursts.
    file_write_intervals: list[tuple[float, float, str, str]] = []
    file_evt_rows = [
        (float(e.get("t_s")), str(e.get("type", "")).replace("file_", ""), str(e.get("path") or ""))
        for e in file_events
        if isinstance(e.get("t_s"), (int, float))
    ]
    file_evt_rows.sort(key=lambda x: x[0])
    if file_evt_rows:
        burst_gap_s = 0.75
        burst_start, prev_t = file_evt_rows[0][0], file_evt_rows[0][0]
        burst_items: list[tuple[float, str, str]] = [file_evt_rows[0]]
        for row in file_evt_rows[1:]:
            t, kind, path = row
            if (t - prev_t) <= burst_gap_s:
                burst_items.append(row)
                prev_t = t
                continue
            kinds = {item[1] for item in burst_items}
            label = "File Creation" if kinds == {"add"} else "Apply File Changes"
            paths = sorted({item[2] for item in burst_items if item[2]})
            desc = ", ".join(paths[:3]) + (" ..." if len(paths) > 3 else "")
            burst_end = max(prev_t, burst_start + 0.05)
            file_write_intervals.append((burst_start, burst_end, label, desc or "file write"))
            burst_start, prev_t = t, t
            burst_items = [row]
        kinds = {item[1] for item in burst_items}
        label = "File Creation" if kinds == {"add"} else "Apply File Changes"
        paths = sorted({item[2] for item in burst_items if item[2]})
        desc = ", ".join(paths[:3]) + (" ..." if len(paths) > 3 else "")
        burst_end = max(prev_t, burst_start + 0.05)
        file_write_intervals.append((burst_start, burst_end, label, desc or "file write"))

    strip_segments: list[tuple[float, float, str, str]] = []
    if isinstance(duration, (int, float)):
        duration_f = float(duration)
        time_points = {0.0, duration_f}
        for start, end, _, _ in cmd_intervals:
            time_points.add(start)
            time_points.add(end)
        for start, end, _ in llm_wait_intervals:
            time_points.add(start)
            time_points.add(end)
        for start, end, _, _ in llm_gen_intervals:
            time_points.add(start)
            time_points.add(end)
        for start, end, _, _ in file_write_intervals:
            time_points.add(start)
            time_points.add(end)
        points = sorted(time_points)

        def _active(interval_start: float, interval_end: float, t: float) -> bool:
            return interval_start <= t < interval_end

        max_observed_end = 0.0
        for s, e, _, _ in cmd_intervals:
            max_observed_end = max(max_observed_end, e)
        for s, e, _ in llm_wait_intervals:
            max_observed_end = max(max_observed_end, e)
        for s, e, _, _ in llm_gen_intervals:
            max_observed_end = max(max_observed_end, e)
        for s, e, _, _ in file_write_intervals:
            max_observed_end = max(max_observed_end, e)

        for i in range(len(points) - 1):
            start = points[i]
            end = points[i + 1]
            if end <= start:
                continue
            mid = (start + end) / 2.0

            active_wait = [(cid,) for req, first, cid in llm_wait_intervals if _active(req, first, mid)]
            if active_wait:
                call_ids = ", ".join(str(x[0]) for x in active_wait)
                strip_segments.append((start, end, "LLM Wait", f"Call(s) {call_ids} waiting for first token"))
                continue

            active_gen = [
                (cid, out_tok)
                for gen_start, gen_end, cid, out_tok in llm_gen_intervals
                if _active(gen_start, gen_end, mid)
            ]
            if active_gen:
                call_ids = ", ".join(str(c[0]) for c in active_gen)
                out_sum = sum(c[1] for c in active_gen)
                desc = f"Call(s) {call_ids} active; output tokens in call(s): {out_sum}"
                strip_segments.append((start, end, "LLM Generation", desc))
                continue

            def _is_background_cmd(pid: int, cmd: str, cmd_start: float, cmd_end: float) -> bool:
                low = cmd.lower()
                if isinstance(root_pid, int) and pid == root_pid:
                    return True
                if "pyright-langserver" in low and "--stdio" in low:
                    return True
                if (cmd_end - cmd_start) >= max(5.0, duration_f * 0.8):
                    return True
                return False

            active_cmds = [
                (pid, cmd)
                for cmd_start, cmd_end, pid, cmd in cmd_intervals
                if _active(cmd_start, cmd_end, mid) and not _is_background_cmd(pid, cmd, cmd_start, cmd_end)
            ]
            if active_cmds:
                if len(active_cmds) == 1:
                    strip_segments.append((start, end, "Shell Command Execution", _short(active_cmds[0][1])))
                else:
                    strip_segments.append(
                        (start, end, "Shell Command Execution", f"{len(active_cmds)} commands active")
                    )
                continue

            active_file = [
                (label, desc)
                for f_start, f_end, label, desc in file_write_intervals
                if _active(f_start, f_end, mid)
            ]
            if active_file:
                label, desc = active_file[0]
                strip_segments.append((start, end, label, desc))
                continue

            if max_observed_end < duration_f and start >= max_observed_end:
                strip_segments.append((start, end, "Cleanup & Teardown", "Finalize run and persist artifacts"))
            elif isinstance(first_llm_req, (int, float)) and end <= float(first_llm_req):
                strip_segments.append(
                    (start, end, "Process Bootstrap", "Launch opencode, initialize runtime and session")
                )
            else:
                strip_segments.append(
                    (start, end, "Prompt Construction", "Agent internal orchestration / no external event")
                )

    if strip_segments:
        cleaned: list[tuple[float, float, str, str]] = []
        min_window = 0.01
        for seg in strip_segments:
            start, end, op_name, desc = seg
            if (end - start) < min_window:
                continue
            if cleaned:
                p_start, p_end, p_name, p_desc = cleaned[-1]
                if p_name == op_name and p_desc == desc and abs(start - p_end) <= min_window:
                    cleaned[-1] = (p_start, end, p_name, p_desc)
                    continue
            cleaned.append(seg)
        strip_segments = cleaned

    lines.extend(["", "## Timeline Strip (Relative)", "", "```text"])
    if isinstance(duration, (int, float)):
        lines.append(f"0.0s --------------------------------------- {duration:.1f}s")
    else:
        lines.append("0.0s --------------------------------------- n/as")
    lines.append("")
    if strip_segments:
        for start, end, op_name, desc in strip_segments:
            lines.append(f" {start:>6.3f} - {end:<6.3f}s [{op_name}] {desc}")
    else:
        lines.append(" (no phase data available)")
    lines.append("```")

    # Aggregate strip segments into higher-level phases for paper/report use.
    phase_order = [
        "Startup (Python imports)",
        "Coordination (Repo scan)",
        "LLM Inference (Network + Gen)",
        "Tool Execution (File writes)",
        "Cleanup (Git commit)",
    ]
    phase_totals: dict[str, float] = {name: 0.0 for name in phase_order}

    for start, end, op_name, _desc in strip_segments:
        seg_dur = max(0.0, end - start)
        if seg_dur <= 0.0:
            continue
        if op_name == "Process Bootstrap":
            phase_totals["Startup (Python imports)"] += seg_dur
        elif op_name == "Prompt Construction":
            phase_totals["Coordination (Repo scan)"] += seg_dur
        elif op_name in {"LLM Wait", "LLM Generation"}:
            phase_totals["LLM Inference (Network + Gen)"] += seg_dur
        elif op_name in {"Apply File Changes", "File Creation", "Shell Command Execution"}:
            phase_totals["Tool Execution (File writes)"] += seg_dur
        elif op_name == "Cleanup & Teardown":
            phase_totals["Cleanup (Git commit)"] += seg_dur

    phase_total_time = float(duration) if isinstance(duration, (int, float)) and duration > 0 else sum(phase_totals.values())
    if phase_total_time > 0:
        lines.extend(["", "## Phase Breakdown", ""])
        lines.append("| Phase | Time | % |")
        lines.append("| --- | ---: | ---: |")
        for phase_name in phase_order:
            sec = phase_totals[phase_name]
            pct = (sec / phase_total_time) * 100.0 if phase_total_time > 0 else 0.0
            lines.append(f"| {phase_name} | {sec:.1f}s | {pct:.0f}% |")
        lines.append(f"| **Total** | **{phase_total_time:.1f}s** | **100%** |")

    lines.extend(["", "## Operation Coverage (Monitor/Proxy only)", ""])
    for op in timeline.get("operations", []):
        op_id = op.get("id")
        name = op.get("name")
        if "count" in op:
            lines.append(f"- [{op_id}] {name}: count={op.get('count', 0)}")
            continue
        start_s = _fmt_s(op.get("start_s"))
        end_s = _fmt_s(op.get("end_s"))
        note = op.get("note")
        suffix = f" ({note})" if note else ""
        lines.append(f"- [{op_id}] {name}: {start_s} -> {end_s}{suffix}")

    lines.extend(["", "## Event Trace (relative)", ""])

    llm_calls = timeline.get("llm_calls", [])
    lines.extend(["", "### LLM Calls", ""])
    lines.append("| Call | Dispatch | First Token | Complete | TTFT | Latency | Status | In Tok | Out Tok | Cost (USD) |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    if llm_calls:
        has_any_cost = any(float(row.get("cost_usd", 0.0) or 0.0) > 0 for row in llm_calls)
        for row in llm_calls:
            if has_any_cost:
                cost_cell = f"${float(row.get('cost_usd', 0.0)):.6f}"
            else:
                cost_cell = "n/a"
            lines.append(
                f"| {row.get('call_id')} | "
                f"+{(row.get('request_t_s') or 0.0):.3f}s | "
                f"{('+' + f'{row.get('first_token_t_s'):.3f}s') if isinstance(row.get('first_token_t_s'), (int, float)) else 'n/a'} | "
                f"{('+' + f'{row.get('response_t_s'):.3f}s') if isinstance(row.get('response_t_s'), (int, float)) else 'n/a'} | "
                f"{_fmt_s(row.get('ttft_s'))} | "
                f"{_fmt_s(row.get('latency_s'))} | "
                f"{row.get('status_code', 'n/a')} | "
                f"{row.get('input_tokens', 0)} | "
                f"{row.get('output_tokens', 0)} | "
                f"{cost_cell} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - | - |")

    command_events = [e for e in events if e.get("type") in {"child_process_start", "child_process_end"}]
    cmd_starts: dict[int, list[dict[str, Any]]] = {}
    cmd_rows: list[tuple[float, float, int, str]] = []
    has_cmd_end_events = any(e.get("type") == "child_process_end" for e in command_events)
    for evt in command_events:
        t = evt.get("t_s")
        pid = evt.get("pid")
        if not isinstance(t, (int, float)) or not isinstance(pid, int):
            continue
        if evt.get("type") == "child_process_start":
            cmd_starts.setdefault(pid, []).append(evt)
        elif evt.get("type") == "child_process_end":
            queue = cmd_starts.get(pid) or []
            if queue:
                start_evt = queue.pop(0)
                cmd = str(start_evt.get("command") or evt.get("command") or "")
                cmd_rows.append((float(start_evt.get("t_s") or 0.0), float(t), pid, cmd))
    if isinstance(duration, (int, float)) and has_cmd_end_events:
        for pid, queue in cmd_starts.items():
            for start_evt in queue:
                cmd = str(start_evt.get("command") or "")
                cmd_rows.append((float(start_evt.get("t_s") or 0.0), float(duration), pid, cmd))
    elif isinstance(duration, (int, float)):
        for pid, queue in cmd_starts.items():
            for start_evt in queue:
                cmd = str(start_evt.get("command") or "")
                start_t = float(start_evt.get("t_s") or 0.0)
                cmd_rows.append((start_t, min(float(duration), start_t + 0.1), pid, cmd))
    cmd_rows.sort(key=lambda x: (x[0], x[1]))

    lines.extend(["", "### Commands", ""])
    lines.append("| Start | End | Duration | PID | Command |")
    lines.append("| --- | --- | --- | --- | --- |")
    if cmd_rows:
        for start_t, end_t, pid, cmd in cmd_rows:
            safe_cmd = cmd.replace("|", "\\|")
            lines.append(
                f"| +{start_t:.3f}s | +{end_t:.3f}s | {_fmt_s(max(0.0, end_t - start_t))} | {pid} | `{safe_cmd}` |"
            )
    else:
        lines.append("| - | - | - | - | - |")

    file_events = [e for e in events if str(e.get("type", "")).startswith("file_")]
    lines.extend(["", "### File Events", ""])
    lines.append("| Time | Event | Path |")
    lines.append("| --- | --- | --- |")
    if file_events:
        for evt in file_events:
            kind = str(evt.get("type", "")).replace("file_", "")
            path = str(evt.get("path") or "").replace("|", "\\|")
            lines.append(f"| +{evt.get('t_s', 0.0):.3f}s | {kind} | `{path}` |")
    else:
        lines.append("| - | - | - |")

    lifecycle = [e for e in events if e.get("type") in {"run_start", "run_end"}]
    lines.extend(["", "### Lifecycle", ""])
    for evt in lifecycle:
        lines.append(f"- +{evt.get('t_s', 0.0):.3f}s `{evt.get('type')}`")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
