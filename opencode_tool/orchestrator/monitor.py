from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None


class RunMonitor:
    def __init__(
        self,
        pid: int,
        task_dir: Path,
        out_path: Path,
        sample_interval_s: float = 0.1,
        file_interval_s: float = 0.5,
    ) -> None:
        self.pid = pid
        self.task_dir = task_dir
        self.out_path = out_path
        self.sample_interval_s = sample_interval_s
        self.file_interval_s = file_interval_s

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_pids: set[int] = set()
        self._alive_children: dict[int, dict[str, Any]] = {}
        self._file_state: dict[str, tuple[float, int]] = {}
        self.start_epoch: float | None = None
        self.end_epoch: float | None = None

        self.out_path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, record: dict[str, Any]) -> None:
        with self.out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _snapshot_files(self) -> dict[str, tuple[float, int]]:
        state: dict[str, tuple[float, int]] = {}
        for path in self.task_dir.rglob("*.py"):
            if not path.is_file():
                continue
            try:
                st = path.stat()
                rel = str(path.relative_to(self.task_dir))
                state[rel] = (st.st_mtime, st.st_size)
            except OSError:
                continue
        return state

    def _emit_file_events(self, now_epoch: float) -> None:
        current = self._snapshot_files()

        prev_keys = set(self._file_state.keys())
        cur_keys = set(current.keys())

        for rel in sorted(cur_keys - prev_keys):
            self._append(
                {
                    "record_type": "file_event",
                    "timestamp_epoch": now_epoch,
                    "event": "add",
                    "path": rel,
                }
            )

        for rel in sorted(prev_keys - cur_keys):
            self._append(
                {
                    "record_type": "file_event",
                    "timestamp_epoch": now_epoch,
                    "event": "delete",
                    "path": rel,
                }
            )

        for rel in sorted(cur_keys & prev_keys):
            if current[rel] != self._file_state[rel]:
                self._append(
                    {
                        "record_type": "file_event",
                        "timestamp_epoch": now_epoch,
                        "event": "change",
                        "path": rel,
                    }
                )

        self._file_state = current

    @staticmethod
    def _safe_cmdline(proc: Any) -> list[str]:
        try:
            cmd = proc.cmdline()
            if isinstance(cmd, list):
                return [str(x) for x in cmd]
        except Exception:
            pass
        return []

    def _monitor_loop(self) -> None:
        last_sample = 0.0
        last_file = 0.0

        if psutil is not None:
            try:
                root = psutil.Process(self.pid)
                root.cpu_percent(interval=None)
            except Exception:
                root = None
        else:
            root = None

        while not self._stop.is_set():
            now = time.time()

            if now - last_sample >= self.sample_interval_s:
                if root is not None:
                    try:
                        rss_total = 0
                        cpu_total = 0.0
                        alive = [root] + root.children(recursive=True)
                        alive_map: dict[int, Any] = {proc.pid: proc for proc in alive}
                        for proc in alive:
                            try:
                                rss_total += int(proc.memory_info().rss)
                                cpu_total += float(proc.cpu_percent(interval=None))
                            except Exception:
                                continue

                        self._append(
                            {
                                "record_type": "process_sample",
                                "timestamp_epoch": now,
                                "cpu_percent": cpu_total,
                                "rss_bytes": rss_total,
                                "process_count": len(alive),
                            }
                        )

                        for proc in alive:
                            if proc.pid in self._seen_pids:
                                continue
                            self._seen_pids.add(proc.pid)
                            cmdline = self._safe_cmdline(proc)
                            started = {
                                "pid": proc.pid,
                                "ppid": proc.ppid() if hasattr(proc, "ppid") else None,
                                "cmdline": cmdline,
                                "start_timestamp_epoch": now,
                            }
                            self._alive_children[proc.pid] = started
                            self._append(
                                {
                                    "record_type": "child_process_start",
                                    "timestamp_epoch": now,
                                    **started,
                                }
                            )

                        ended_pids = sorted(set(self._alive_children.keys()) - set(alive_map.keys()))
                        for pid in ended_pids:
                            prior = self._alive_children.pop(pid, {})
                            self._append(
                                {
                                    "record_type": "child_process_end",
                                    "timestamp_epoch": now,
                                    "pid": pid,
                                    "ppid": prior.get("ppid"),
                                    "cmdline": prior.get("cmdline") or [],
                                    "start_timestamp_epoch": prior.get("start_timestamp_epoch"),
                                    "end_timestamp_epoch": now,
                                }
                            )
                    except Exception:
                        pass
                else:
                    alive = True
                    try:
                        os.kill(self.pid, 0)
                    except OSError:
                        alive = False
                    self._append(
                        {
                            "record_type": "process_sample",
                            "timestamp_epoch": now,
                            "cpu_percent": None,
                            "rss_bytes": None,
                            "process_count": 1 if alive else 0,
                        }
                    )

                last_sample = now

            if now - last_file >= self.file_interval_s:
                self._emit_file_events(now)
                last_file = now

            time.sleep(0.05)

    def start(self) -> None:
        self.start_epoch = time.time()
        self._file_state = self._snapshot_files()
        self._append(
            {
                "record_type": "monitor_run_start",
                "timestamp_epoch": self.start_epoch,
                "pid": self.pid,
            }
        )

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self, timed_out: bool, return_code: int) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

        self.end_epoch = time.time()
        # Flush any still-alive children as ended at monitor stop time.
        for pid in sorted(self._alive_children.keys()):
            prior = self._alive_children.get(pid) or {}
            self._append(
                {
                    "record_type": "child_process_end",
                    "timestamp_epoch": self.end_epoch,
                    "pid": pid,
                    "ppid": prior.get("ppid"),
                    "cmdline": prior.get("cmdline") or [],
                    "start_timestamp_epoch": prior.get("start_timestamp_epoch"),
                    "end_timestamp_epoch": self.end_epoch,
                }
            )
        self._alive_children = {}
        self._emit_file_events(self.end_epoch)
        self._append(
            {
                "record_type": "monitor_run_end",
                "timestamp_epoch": self.end_epoch,
                "timed_out": timed_out,
                "return_code": return_code,
            }
        )
