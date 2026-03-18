"""mitmproxy addon that captures raw request/response payloads as JSONL."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mitmproxy import http


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _decode(content: bytes | None) -> str | None:
    if content is None:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="replace")


def _parse_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class CaptureAddon:
    def __init__(self) -> None:
        out = os.environ.get("MITM_CAPTURE_OUT")
        if not out:
            raise RuntimeError("MITM_CAPTURE_OUT is required")
        self.out_path = Path(out)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.task_name = os.environ.get("MITM_TASK_NAME", "unknown_task")
        self.trace_id = os.environ.get("MITM_TRACE_ID", "unknown_trace")
        self.call_counter = 0
        self.flow_to_call_id: dict[str, int] = {}

    def _append(self, payload: dict[str, Any]) -> None:
        with self.out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def request(self, flow: http.HTTPFlow) -> None:
        self.call_counter += 1
        call_id = self.call_counter
        self.flow_to_call_id[flow.id] = call_id

        request_text = _decode(flow.request.raw_content)
        headers_subset = {
            "content-type": flow.request.headers.get("content-type"),
            "authorization": "<redacted>" if flow.request.headers.get("authorization") else None,
            "x-request-id": flow.request.headers.get("x-request-id"),
            "openai-organization": flow.request.headers.get("openai-organization"),
        }

        rec = {
            "record_type": "http_request",
            "trace_id": self.trace_id,
            "task_name": self.task_name,
            "call_id": call_id,
            "turn_guess": call_id,
            "flow_id": flow.id,
            "timestamp": _iso(flow.request.timestamp_start),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "headers": headers_subset,
            "request_body_text": request_text,
            "request_body_json": _parse_json(request_text),
        }
        self._append(rec)

    def response(self, flow: http.HTTPFlow) -> None:
        call_id = self.flow_to_call_id.get(flow.id, -1)
        response_text = _decode(flow.response.raw_content if flow.response else None)

        rec = {
            "record_type": "http_response",
            "trace_id": self.trace_id,
            "task_name": self.task_name,
            "call_id": call_id,
            "turn_guess": call_id,
            "flow_id": flow.id,
            "timestamp": _iso(flow.response.timestamp_end if flow.response else None),
            "timestamp_start": _iso(flow.response.timestamp_start if flow.response else None),
            "timestamp_end": _iso(flow.response.timestamp_end if flow.response else None),
            "status_code": flow.response.status_code if flow.response else None,
            "reason": flow.response.reason if flow.response else None,
            "response_body_text": response_text,
            "response_body_json": _parse_json(response_text),
        }
        self._append(rec)


addons = [CaptureAddon()]
