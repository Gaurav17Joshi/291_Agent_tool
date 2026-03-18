from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Any


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_tree(root: Path) -> Dict[str, Dict[str, Any]]:
    snap: Dict[str, Dict[str, Any]] = {}
    for p in root.rglob("*.py"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        try:
            lines = len(p.read_text(encoding="utf-8").splitlines())
            snap[rel] = {"hash": _sha256(p), "lines": lines}
        except OSError:
            continue
    return snap


def diff_snapshots(before: Dict[str, Dict[str, Any]], after: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    before_keys = set(before.keys())
    after_keys = set(after.keys())

    added = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    common = sorted(before_keys & after_keys)

    modified = []
    line_delta_total = 0

    for key in common:
        if before[key]["hash"] != after[key]["hash"]:
            delta = int(after[key]["lines"]) - int(before[key]["lines"])
            modified.append({"path": key, "line_delta": delta})
            line_delta_total += delta

    for key in added:
        line_delta_total += int(after[key]["lines"])

    for key in deleted:
        line_delta_total -= int(before[key]["lines"])

    return {
        "added": added,
        "deleted": deleted,
        "modified": modified,
        "line_delta_total": line_delta_total,
    }


def write_markdown(diff: Dict[str, Any], out_path: Path) -> None:
    lines = ["# File Changes", "", f"- Line delta total: {diff['line_delta_total']}", ""]

    lines.append("## Added")
    lines.append("")
    if diff["added"]:
        lines.extend([f"- `{p}`" for p in diff["added"]])
    else:
        lines.append("- None")

    lines.extend(["", "## Modified", ""])
    if diff["modified"]:
        for item in diff["modified"]:
            lines.append(f"- `{item['path']}` (line delta: {item['line_delta']})")
    else:
        lines.append("- None")

    lines.extend(["", "## Deleted", ""])
    if diff["deleted"]:
        lines.extend([f"- `{p}`" for p in diff["deleted"]])
    else:
        lines.append("- None")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
