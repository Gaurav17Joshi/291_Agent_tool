from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _preview_text(text: Any, limit: int = 220) -> str:
    if not isinstance(text, str):
        return ""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _parse_sse_events(response_text: str | None) -> list[dict[str, Any]]:
    if not response_text:
        return []

    events: list[dict[str, Any]] = []
    current_event: str | None = None
    for raw_line in response_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
            continue
        if not line.startswith("data:"):
            continue
        payload_text = line[len("data:") :].strip()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        events.append(
            {
                "event": current_event or payload.get("type"),
                "data": payload,
            }
        )
        current_event = None
    return events


def _extract_completed_response(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        data = event.get("data")
        if isinstance(data, dict) and data.get("type") == "response.completed":
            response = data.get("response")
            if isinstance(response, dict):
                return response
    return None


def _extract_function_args_done(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict) or data.get("type") != "response.function_call_arguments.done":
            continue
        parsed_args: Any = data.get("arguments")
        if isinstance(parsed_args, str):
            try:
                parsed_args = json.loads(parsed_args)
            except json.JSONDecodeError:
                pass
        result.append(
            {
                "item_id": data.get("item_id"),
                "arguments": parsed_args,
            }
        )
    return result


def _extract_assistant_texts(completed_response: dict[str, Any] | None) -> list[str]:
    texts: list[str] = []
    if not isinstance(completed_response, dict):
        return texts
    for output in completed_response.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for part in output.get("content", []):
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    return texts


def _extract_tool_calls(completed_response: dict[str, Any] | None) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    if not isinstance(completed_response, dict):
        return tool_calls
    for output in completed_response.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "function_call":
            continue
        parsed_args: Any = output.get("arguments")
        if isinstance(parsed_args, str):
            try:
                parsed_args = json.loads(parsed_args)
            except json.JSONDecodeError:
                pass
        tool_calls.append(
            {
                "name": output.get("name"),
                "call_id": output.get("call_id"),
                "arguments": parsed_args,
            }
        )
    return tool_calls


def _extract_message_summary(message: dict[str, Any]) -> str:
    role = message.get("role")
    if not isinstance(role, str) or not role.strip():
        role = str(message.get("type") or "message")
    content = message.get("content")
    if isinstance(content, str):
        return f"{role}: {_preview_text(content)}"
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(_preview_text(text, limit=140))
        if text_parts:
            return f"{role}: {len(content)} item(s), first: {text_parts[0]}"
        return f"{role}: {len(content)} item(s)"
    if isinstance(message.get("type"), str):
        return f"{role}: type={message.get('type')}"
    return f"{role}: <unrecognized content>"


def write_llm_messages(
    proxy_parsed: dict[str, Any],
    json_path: Path,
    md_path: Path,
    hr_md_path: Path | None = None,
) -> None:
    records = []
    lines = ["# LLM Messages", ""]
    hr_lines = ["# Human-Readable LLM Messages", ""]

    for call in proxy_parsed.get("calls", []):
        req = call.get("request") or {}
        resp = call.get("response") or {}
        rec = {
            "call_id": call.get("call_id"),
            "timestamp_request": req.get("timestamp"),
            "timestamp_response": resp.get("timestamp"),
            "request_epoch": call.get("request_epoch"),
            "response_epoch": call.get("response_epoch"),
            "latency_s": call.get("latency_s"),
            "url": req.get("url"),
            "request_json": req.get("request_body_json"),
            "response_json": resp.get("response_body_json"),
            "request_text": req.get("request_body_text"),
            "response_text": resp.get("response_body_text"),
            "status_code": resp.get("status_code"),
        }
        records.append(rec)

        lines.append(f"## Call {rec['call_id']}")
        lines.append("")
        lines.append(f"- Request time: `{rec['timestamp_request']}`")
        lines.append(f"- Response time: `{rec['timestamp_response']}`")
        lines.append(f"- Latency: `{rec['latency_s']}` s")
        lines.append(f"- URL: `{rec['url']}`")
        lines.append(f"- Status: `{rec['status_code']}`")
        lines.append("")
        lines.append("### Request JSON")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(rec["request_json"], indent=2) if rec["request_json"] is not None else "null")
        lines.append("```")
        lines.append("")
        lines.append("### Response JSON")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(rec["response_json"], indent=2) if rec["response_json"] is not None else "null")
        lines.append("```")
        lines.append("")

        # Human-readable output.
        hr_lines.append(f"## Call {rec['call_id']}")
        hr_lines.append("")
        hr_lines.append(f"- Request time: `{rec['timestamp_request']}`")
        hr_lines.append(f"- Response time: `{rec['timestamp_response']}`")
        hr_lines.append(f"- Latency: `{rec['latency_s']}` s")
        hr_lines.append(f"- URL: `{rec['url']}`")
        hr_lines.append(f"- Status: `{rec['status_code']}`")
        hr_lines.append("")

        request_json = rec.get("request_json")
        if isinstance(request_json, dict):
            hr_lines.append("### Request Summary")
            hr_lines.append("")
            hr_lines.append(f"- Model: `{request_json.get('model')}`")
            hr_lines.append(f"- Max output tokens: `{request_json.get('max_output_tokens')}`")
            tools = request_json.get("tools")
            if isinstance(tools, list):
                tool_names = [str(t.get("name")) for t in tools if isinstance(t, dict) and t.get("name")]
                hr_lines.append(
                    "- Tools in request: "
                    + (", ".join(f"`{name}`" for name in tool_names) if tool_names else "`none`")
                )
            else:
                hr_lines.append("- Tools in request: `none`")

            inputs = request_json.get("input")
            if isinstance(inputs, list):
                hr_lines.append("- Input messages:")
                for msg in inputs:
                    if isinstance(msg, dict):
                        hr_lines.append(f"  - {_extract_message_summary(msg)}")
            hr_lines.append("")

        events = _parse_sse_events(rec.get("response_text"))
        event_counts: dict[str, int] = {}
        for event in events:
            event_name = event.get("event")
            if isinstance(event_name, str) and event_name:
                event_counts[event_name] = event_counts.get(event_name, 0) + 1

        if event_counts:
            hr_lines.append("### Response Event Summary")
            hr_lines.append("")
            for event_name in sorted(event_counts):
                hr_lines.append(f"- `{event_name}`: `{event_counts[event_name]}`")
            hr_lines.append("")

        completed = _extract_completed_response(events)
        assistant_texts = _extract_assistant_texts(completed)
        tool_calls = _extract_tool_calls(completed)
        function_args_done = _extract_function_args_done(events)

        hr_lines.append("### Extracted Outcome")
        hr_lines.append("")
        if assistant_texts:
            hr_lines.append("#### Assistant Text")
            hr_lines.append("")
            for idx, text in enumerate(assistant_texts, start=1):
                hr_lines.append(f"{idx}. {text}")
            hr_lines.append("")
        else:
            hr_lines.append("- Assistant text: `none`")

        if tool_calls:
            hr_lines.append("#### Tool Calls (from `response.completed`)")
            hr_lines.append("")
            for tc in tool_calls:
                hr_lines.append(f"- Name: `{tc.get('name')}`")
                hr_lines.append(f"- Call ID: `{tc.get('call_id')}`")
                hr_lines.append("- Arguments:")
                hr_lines.append("```json")
                hr_lines.append(json.dumps(tc.get("arguments"), indent=2))
                hr_lines.append("```")
            hr_lines.append("")
        else:
            hr_lines.append("- Tool calls: `none`")

        if function_args_done:
            hr_lines.append("#### Tool Payloads (from `response.function_call_arguments.done`)")
            hr_lines.append("")
            for fc in function_args_done:
                hr_lines.append(f"- Item ID: `{fc.get('item_id')}`")
                hr_lines.append("```json")
                hr_lines.append(json.dumps(fc.get("arguments"), indent=2))
                hr_lines.append("```")
            hr_lines.append("")

        if isinstance(completed, dict):
            usage = completed.get("usage")
            hr_lines.append("#### Response Metadata")
            hr_lines.append("")
            hr_lines.append(f"- Response ID: `{completed.get('id')}`")
            hr_lines.append(f"- Model (actual): `{completed.get('model')}`")
            hr_lines.append(f"- Status: `{completed.get('status')}`")
            hr_lines.append("- Usage:")
            hr_lines.append("```json")
            hr_lines.append(json.dumps(usage, indent=2))
            hr_lines.append("```")
            hr_lines.append("")

    json_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    if hr_md_path is not None:
        hr_md_path.write_text("\n".join(hr_lines), encoding="utf-8")


def write_run_summary(
    run_id: str,
    task_name: str,
    run_dir: Path,
    success: bool,
    return_code: int,
    timeline: dict[str, Any],
    report_path: Path,
) -> None:
    summary = timeline.get("summary", {})

    lines = [
        f"# Run Summary {run_id}",
        "",
        f"- Task: `{task_name}`",
        f"- Success: `{success}`",
        f"- Return code: `{return_code}`",
        f"- Duration: `{summary.get('duration_s')}` s",
        f"- LLM calls: `{summary.get('llm_calls', 0)}`",
        f"- LLM total latency: `{summary.get('llm_total_latency_s', 0.0)}` s",
        f"- LLM avg latency: `{summary.get('llm_avg_latency_s', 0.0)}` s",
        f"- File events: `{summary.get('monitor_file_events', 0)}`",
        f"- Shell commands: `{summary.get('monitor_shell_commands', 0)}`",
        f"- Test/validation commands: `{summary.get('monitor_test_commands', 0)}`",
        f"- Git commands: `{summary.get('monitor_git_commands', 0)}`",
        f"- Peak CPU%: `{summary.get('peak_cpu_percent', 0.0)}`",
        f"- Peak RSS MB: `{summary.get('peak_rss_mb', 0.0)}`",
        "",
        "## Artifacts",
        "",
        f"- `{run_dir / 'opencode' / 'events.jsonl'}`",
        f"- `{run_dir / 'proxy' / 'raw_http.jsonl'}`",
        f"- `{run_dir / 'monitor' / 'raw_monitor.jsonl'}`",
        f"- `{run_dir / 'analysis' / 'timeline.md'}`",
        f"- `{run_dir / 'analysis' / 'llm_messages.md'}`",
        f"- `{run_dir / 'analysis' / 'HR_llm_messages.md'}`",
        f"- `{run_dir / 'analysis' / 'file_changes.md'}`",
    ]

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
