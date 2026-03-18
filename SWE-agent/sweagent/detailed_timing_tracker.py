# """Detailed timing tracker for SWE-agent execution profiling.

# Produces a per-task JSON with fine-grained timing entries, each recording
# the exact start/end time (relative to the task start), duration, and
# contextual detail (commands, prompts, responses, etc.).
# """

# import threading
# import time
# from dataclasses import dataclass, field
# from pathlib import Path
# from typing import Any, Optional
# import json


# @dataclass
# class TimingEntry:
#     """A single timed event."""
#     start_time_abs: float  # absolute time (time.perf_counter)
#     end_time_abs: float = 0.0
#     detail: str = ""
#     extra: dict = field(default_factory=dict)  # prompt, response, command, etc.

#     def to_dict(self, task_start_abs: float) -> dict:
#         rel_start = self.start_time_abs - task_start_abs
#         rel_end = self.end_time_abs - task_start_abs if self.end_time_abs > 0 else 0.0
#         duration = self.end_time_abs - self.start_time_abs if self.end_time_abs > 0 else 0.0
#         result = {
#             "start_time": round(rel_start, 4),
#             "end_time": round(rel_end, 4),
#             "duration": round(duration, 4),
#             "detail": self.detail,
#         }
#         result.update(self.extra)
#         return result


# DETAILED_CATEGORIES = [
#     "process_bootstrap",
#     "environment_provisioning",
#     "workspace_initialization",
#     "repository_scan",
#     "diff_computation",
#     "prompt_construction",
#     "context_compaction",
#     "llm_generation",
#     "patch_edit_parsing",
#     "apply_file_changes",
#     "file_creation",
#     "shell_command_execution",
#     "git_operations",
#     "test_validation_execution",
#     "retry_backoff",
#     "cleanup_and_teardown",
# ]

# # Commands that indicate test execution
# TEST_COMMAND_PATTERNS = [
#     "pytest", "python -m pytest", "python -m unittest",
#     "nosetests", "tox", "./test", "make test", "make check",
#     "python -m nose", "unittest", "py.test",
# ]

# # Commands that are git operations
# GIT_COMMAND_PATTERNS = [
#     "git ",
# ]


# @dataclass
# class TaskDetailedTimings:
#     """All detailed timing data for a single task."""
#     task_id: str
#     task_start_abs: float = 0.0
#     task_end_abs: float = 0.0
#     categories: dict[str, list[TimingEntry]] = field(default_factory=dict)

#     def __post_init__(self):
#         for cat in DETAILED_CATEGORIES:
#             if cat not in self.categories:
#                 self.categories[cat] = []

#     def add_entry(self, category: str, entry: TimingEntry) -> None:
#         if category not in self.categories:
#             self.categories[category] = []
#         self.categories[category].append(entry)

#     def remove_last_entry(self, category: str) -> Optional[TimingEntry]:
#         """Remove and return the last entry from a category."""
#         if category in self.categories and self.categories[category]:
#             return self.categories[category].pop()
#         return None

#     def _build_timeline_string(self) -> str:
#         """Build the 'overall_runtime' timeline string."""
#         if self.task_end_abs <= 0 or self.task_start_abs <= 0:
#             return ""

#         total_duration = self.task_end_abs - self.task_start_abs

#         # Collect all entries with their relative times and categories
#         all_events: list[tuple[float, float, str]] = []
#         for cat, entries in self.categories.items():
#             for entry in entries:
#                 rel_start = entry.start_time_abs - self.task_start_abs
#                 rel_end = entry.end_time_abs - self.task_start_abs if entry.end_time_abs > 0 else rel_start
#                 all_events.append((rel_start, rel_end, cat))

#         # Sort by start time
#         all_events.sort(key=lambda x: x[0])

#         lines = [f"0.0s ----------------------- {total_duration:.1f}s"]
#         for rel_start, rel_end, cat in all_events:
#             lines.append(f"{rel_start:.1f} - {rel_end:.1f}s [{cat}]")

#         return "\n".join(lines)

#     def to_dict(self) -> dict:
#         total_duration = (self.task_end_abs - self.task_start_abs) if self.task_end_abs > 0 else 0.0

#         categories_dict = {}
#         for cat in DETAILED_CATEGORIES:
#             entries = self.categories.get(cat, [])
#             total_cat_duration = sum(
#                 (e.end_time_abs - e.start_time_abs) for e in entries if e.end_time_abs > 0
#             )
#             entries_dict = {}
#             for idx, entry in enumerate(entries, 1):
#                 entries_dict[str(idx)] = entry.to_dict(self.task_start_abs)
#             categories_dict[cat] = {
#                 "total_duration": round(total_cat_duration, 4),
#                 "count": len(entries),
#                 "entries": entries_dict,
#             }

#         # Compute accounted time
#         accounted = sum(categories_dict[cat]["total_duration"] for cat in DETAILED_CATEGORIES)

#         return {
#             "task_id": self.task_id,
#             "overall_duration": round(total_duration, 4),
#             "accounted_time": round(accounted, 4),
#             "unaccounted_time": round(total_duration - accounted, 4) if total_duration > 0 else 0.0,
#             "categories": categories_dict,
#             "overall_runtime": self._build_timeline_string(),
#         }


# class DetailedTimingTracker:
#     """Thread-safe detailed timing tracker.

#     Usage:
#         tracker.start_task("task-id")
#         key = tracker.start_entry("llm_generation", detail="LLM call", extra={...})
#         # ... do work ...
#         tracker.end_entry(key, "llm_generation", extra={...})
#         tracker.end_task()
#         tracker.save_to_file(path)
#     """

#     def __init__(self):
#         self._lock = threading.Lock()
#         self.task_timings: dict[str, TaskDetailedTimings] = {}
#         # Thread -> task_id mapping
#         self._thread_task_ids: dict[int, str] = {}
#         # Pending timers: key -> (start_time_abs, task_id, detail, extra)
#         self._pending: dict[str, tuple[float, str, str, dict]] = {}

#     @property
#     def current_task_id(self) -> Optional[str]:
#         return self._thread_task_ids.get(threading.get_ident())

#     def start_task(self, task_id: str) -> None:
#         tid = threading.get_ident()
#         with self._lock:
#             self._thread_task_ids[tid] = task_id
#             if task_id not in self.task_timings:
#                 self.task_timings[task_id] = TaskDetailedTimings(task_id=task_id)
#             self.task_timings[task_id].task_start_abs = time.perf_counter()

#     def end_task(self) -> None:
#         tid = threading.get_ident()
#         with self._lock:
#             task_id = self._thread_task_ids.get(tid)
#             if task_id and task_id in self.task_timings:
#                 self.task_timings[task_id].task_end_abs = time.perf_counter()
#                 del self._thread_task_ids[tid]

#     def start_entry(self, category: str, detail: str = "", extra: dict | None = None) -> str:
#         """Start timing an entry. Returns a key to pass to end_entry."""
#         now = time.perf_counter()
#         key = f"{category}_{now}_{threading.get_ident()}"
#         with self._lock:
#             task_id = self.current_task_id or ""
#             self._pending[key] = (now, task_id, detail, extra or {})
#         return key

#     def end_entry(self, key: str, category: str, extra: dict | None = None) -> None:
#         """End a timed entry and record it."""
#         now = time.perf_counter()
#         with self._lock:
#             if key not in self._pending:
#                 return
#             start_abs, task_id, detail, start_extra = self._pending.pop(key)
#             if not task_id or task_id not in self.task_timings:
#                 return
#             merged_extra = {**start_extra, **(extra or {})}
#             entry = TimingEntry(
#                 start_time_abs=start_abs,
#                 end_time_abs=now,
#                 detail=detail,
#                 extra=merged_extra,
#             )
#             self.task_timings[task_id].add_entry(category, entry)

#     def add_completed_entry(
#         self, category: str, start_abs: float, end_abs: float,
#         detail: str = "", extra: dict | None = None
#     ) -> None:
#         """Add an already-completed timing entry directly."""
#         with self._lock:
#             task_id = self.current_task_id
#             if not task_id or task_id not in self.task_timings:
#                 return
#             entry = TimingEntry(
#                 start_time_abs=start_abs,
#                 end_time_abs=end_abs,
#                 detail=detail,
#                 extra=extra or {},
#             )
#             self.task_timings[task_id].add_entry(category, entry)

#     def move_last_entry(self, from_category: str, to_category: str, rename_detail: str | None = None) -> None:
#         """Move the last entry from one category to another.
#         Used for retroactively reclassifying LLM calls as retry/backoff.
#         """
#         with self._lock:
#             task_id = self.current_task_id
#             if not task_id or task_id not in self.task_timings:
#                 return
#             entry = self.task_timings[task_id].remove_last_entry(from_category)
#             if entry is not None:
#                 if rename_detail is not None:
#                     entry.detail = rename_detail
#                 self.task_timings[task_id].add_entry(to_category, entry)

#     def get_retry_count(self) -> int:
#         """Get current count of retry entries for the current task."""
#         with self._lock:
#             task_id = self.current_task_id
#             if not task_id or task_id not in self.task_timings:
#                 return 0
#             return len(self.task_timings[task_id].categories.get("retry_backoff", []))

#     def save_to_file(self, output_path: Path) -> None:
#         """Save all task timings to a JSON file."""
#         data = {}
#         for task_id, timings in self.task_timings.items():
#             data[task_id] = timings.to_dict()
#         output_path.parent.mkdir(parents=True, exist_ok=True)
#         output_path.write_text(json.dumps(data, indent=2))


# # Global instance
# _global_detailed_tracker: Optional[DetailedTimingTracker] = None
# _global_detailed_lock = threading.Lock()


# def get_detailed_timing_tracker() -> DetailedTimingTracker:
#     global _global_detailed_tracker
#     with _global_detailed_lock:
#         if _global_detailed_tracker is None:
#             _global_detailed_tracker = DetailedTimingTracker()
#     return _global_detailed_tracker


# def reset_detailed_timing_tracker() -> None:
#     global _global_detailed_tracker
#     with _global_detailed_lock:
#         _global_detailed_tracker = DetailedTimingTracker()



















# """Detailed timing tracker for SWE-agent execution profiling.

# Produces a per-task JSON with fine-grained timing entries, each recording
# the exact start/end time (relative to the task start), duration, and
# contextual detail (commands, prompts, responses, etc.).
# """

# import threading
# import time
# from dataclasses import dataclass, field
# from pathlib import Path
# from typing import Any, Optional
# import json


# @dataclass
# class TimingEntry:
#     """A single timed event."""
#     start_time_abs: float  # absolute time (time.perf_counter)
#     end_time_abs: float = 0.0
#     detail: str = ""
#     extra: dict = field(default_factory=dict)  # prompt, response, command, etc.

#     def to_dict(self, task_start_abs: float) -> dict:
#         rel_start = self.start_time_abs - task_start_abs
#         rel_end = self.end_time_abs - task_start_abs if self.end_time_abs > 0 else 0.0
#         duration = self.end_time_abs - self.start_time_abs if self.end_time_abs > 0 else 0.0
#         result = {
#             "start_time": round(rel_start, 4),
#             "end_time": round(rel_end, 4),
#             "duration": round(duration, 4),
#             "detail": self.detail,
#         }
#         result.update(self.extra)
#         return result


# DETAILED_CATEGORIES = [
#     "process_bootstrap",
#     "environment_provisioning",
#     "workspace_initialization",
#     "repository_scan",
#     "diff_computation",
#     "prompt_construction",
#     "context_compaction",
#     "llm_generation",
#     "apply_file_changes",
#     "file_creation",
#     "shell_command_execution",
#     "git_operations",
#     "test_validation_execution",
#     "retry_backoff",
#     "cleanup_and_teardown",
# ]

# # Commands that indicate test execution
# TEST_COMMAND_PATTERNS = [
#     "pytest", "python -m pytest", "python -m unittest",
#     "nosetests", "tox", "./test", "make test", "make check",
#     "python -m nose", "unittest", "py.test",
# ]

# # Commands that are git operations
# GIT_COMMAND_PATTERNS = [
#     "git ",
# ]


# @dataclass
# class TaskDetailedTimings:
#     """All detailed timing data for a single task."""
#     task_id: str
#     task_start_abs: float = 0.0
#     task_end_abs: float = 0.0
#     categories: dict[str, list[TimingEntry]] = field(default_factory=dict)

#     def __post_init__(self):
#         for cat in DETAILED_CATEGORIES:
#             if cat not in self.categories:
#                 self.categories[cat] = []

#     def add_entry(self, category: str, entry: TimingEntry) -> None:
#         if category not in self.categories:
#             self.categories[category] = []
#         self.categories[category].append(entry)

#     def remove_last_entry(self, category: str) -> Optional[TimingEntry]:
#         """Remove and return the last entry from a category."""
#         if category in self.categories and self.categories[category]:
#             return self.categories[category].pop()
#         return None

#     def _build_timeline_string(self) -> str:
#         """Build the 'overall_runtime' timeline string."""
#         if self.task_end_abs <= 0 or self.task_start_abs <= 0:
#             return ""

#         total_duration = self.task_end_abs - self.task_start_abs

#         # Collect all entries with their relative times and categories
#         all_events: list[tuple[float, float, str]] = []
#         for cat, entries in self.categories.items():
#             for entry in entries:
#                 rel_start = entry.start_time_abs - self.task_start_abs
#                 rel_end = entry.end_time_abs - self.task_start_abs if entry.end_time_abs > 0 else rel_start
#                 all_events.append((rel_start, rel_end, cat))

#         # Sort by start time
#         all_events.sort(key=lambda x: x[0])

#         lines = [f"0.0s ----------------------- {total_duration:.1f}s"]
#         for rel_start, rel_end, cat in all_events:
#             lines.append(f"{rel_start:.1f} - {rel_end:.1f}s [{cat}]")

#         return "\n".join(lines)

#     def to_dict(self) -> dict:
#         total_duration = (self.task_end_abs - self.task_start_abs) if self.task_end_abs > 0 else 0.0

#         categories_dict = {}
#         for cat in DETAILED_CATEGORIES:
#             entries = self.categories.get(cat, [])
#             total_cat_duration = sum(
#                 (e.end_time_abs - e.start_time_abs) for e in entries if e.end_time_abs > 0
#             )
#             entries_dict = {}
#             for idx, entry in enumerate(entries, 1):
#                 entries_dict[str(idx)] = entry.to_dict(self.task_start_abs)
#             categories_dict[cat] = {
#                 "total_duration": round(total_cat_duration, 4),
#                 "count": len(entries),
#                 "entries": entries_dict,
#             }

#         # Compute accounted time
#         accounted = sum(categories_dict[cat]["total_duration"] for cat in DETAILED_CATEGORIES)

#         return {
#             "task_id": self.task_id,
#             "overall_duration": round(total_duration, 4),
#             "accounted_time": round(accounted, 4),
#             "unaccounted_time": round(total_duration - accounted, 4) if total_duration > 0 else 0.0,
#             "categories": categories_dict,
#             "overall_runtime": self._build_timeline_string(),
#         }


# class DetailedTimingTracker:
#     """Thread-safe detailed timing tracker.

#     Usage:
#         tracker.start_task("task-id")
#         key = tracker.start_entry("llm_generation", detail="LLM call", extra={...})
#         # ... do work ...
#         tracker.end_entry(key, "llm_generation", extra={...})
#         tracker.end_task()
#         tracker.save_to_file(path)
#     """

#     def __init__(self):
#         self._lock = threading.Lock()
#         self.task_timings: dict[str, TaskDetailedTimings] = {}
#         # Thread -> task_id mapping
#         self._thread_task_ids: dict[int, str] = {}
#         # Pending timers: key -> (start_time_abs, task_id, detail, extra)
#         self._pending: dict[str, tuple[float, str, str, dict]] = {}

#     @property
#     def current_task_id(self) -> Optional[str]:
#         return self._thread_task_ids.get(threading.get_ident())

#     def start_task(self, task_id: str) -> None:
#         tid = threading.get_ident()
#         with self._lock:
#             self._thread_task_ids[tid] = task_id
#             if task_id not in self.task_timings:
#                 self.task_timings[task_id] = TaskDetailedTimings(task_id=task_id)
#             self.task_timings[task_id].task_start_abs = time.perf_counter()

#     def end_task(self) -> None:
#         tid = threading.get_ident()
#         with self._lock:
#             task_id = self._thread_task_ids.get(tid)
#             if task_id and task_id in self.task_timings:
#                 self.task_timings[task_id].task_end_abs = time.perf_counter()
#                 del self._thread_task_ids[tid]

#     def start_entry(self, category: str, detail: str = "", extra: dict | None = None) -> str:
#         """Start timing an entry. Returns a key to pass to end_entry."""
#         now = time.perf_counter()
#         key = f"{category}_{now}_{threading.get_ident()}"
#         with self._lock:
#             task_id = self.current_task_id or ""
#             self._pending[key] = (now, task_id, detail, extra or {})
#         return key

#     def end_entry(self, key: str, category: str, extra: dict | None = None) -> None:
#         """End a timed entry and record it."""
#         now = time.perf_counter()
#         with self._lock:
#             if key not in self._pending:
#                 return
#             start_abs, task_id, detail, start_extra = self._pending.pop(key)
#             if not task_id or task_id not in self.task_timings:
#                 return
#             merged_extra = {**start_extra, **(extra or {})}
#             entry = TimingEntry(
#                 start_time_abs=start_abs,
#                 end_time_abs=now,
#                 detail=detail,
#                 extra=merged_extra,
#             )
#             self.task_timings[task_id].add_entry(category, entry)

#     def add_completed_entry(
#         self, category: str, start_abs: float, end_abs: float,
#         detail: str = "", extra: dict | None = None
#     ) -> None:
#         """Add an already-completed timing entry directly."""
#         with self._lock:
#             task_id = self.current_task_id
#             if not task_id or task_id not in self.task_timings:
#                 return
#             entry = TimingEntry(
#                 start_time_abs=start_abs,
#                 end_time_abs=end_abs,
#                 detail=detail,
#                 extra=extra or {},
#             )
#             self.task_timings[task_id].add_entry(category, entry)

#     # def move_last_entry(self, from_category: str, to_category: str, rename_detail: str | None = None) -> None:
#     #     """Move the last entry from one category to another.
#     #     Used for retroactively reclassifying LLM calls as retry/backoff.
#     #     """
#     #     with self._lock:
#     #         task_id = self.current_task_id
#     #         if not task_id or task_id not in self.task_timings:
#     #             return
#     #         entry = self.task_timings[task_id].remove_last_entry(from_category)
#     #         if entry is not None:
#     #             if rename_detail is not None:
#     #                 entry.detail = rename_detail
#     #             self.task_timings[task_id].add_entry(to_category, entry)

#     def move_last_entry(self, from_category: str, to_category: str, rename_detail: str | None = None, extra_update: dict | None = None) -> None:
#             """Move the last entry from one category to another.
#             Used for retroactively reclassifying LLM calls as retry/backoff.
#             """
#             with self._lock:
#                 task_id = self.current_task_id
#                 if not task_id or task_id not in self.task_timings:
#                     return
#                 entry = self.task_timings[task_id].remove_last_entry(from_category)
#                 if entry is not None:
#                     if rename_detail is not None:
#                         entry.detail = rename_detail
#                     if extra_update:
#                         entry.extra.update(extra_update)
#                     self.task_timings[task_id].add_entry(to_category, entry)

#     def get_retry_count(self) -> int:
#         """Get current count of retry entries for the current task."""
#         with self._lock:
#             task_id = self.current_task_id
#             if not task_id or task_id not in self.task_timings:
#                 return 0
#             return len(self.task_timings[task_id].categories.get("retry_backoff", []))

#     def save_to_file(self, output_path: Path) -> None:
#         """Save all task timings to a JSON file."""
#         data = {}
#         for task_id, timings in self.task_timings.items():
#             data[task_id] = timings.to_dict()
#         output_path.parent.mkdir(parents=True, exist_ok=True)
#         output_path.write_text(json.dumps(data, indent=2))


# # Global instance
# _global_detailed_tracker: Optional[DetailedTimingTracker] = None
# _global_detailed_lock = threading.Lock()


# def get_detailed_timing_tracker() -> DetailedTimingTracker:
#     global _global_detailed_tracker
#     with _global_detailed_lock:
#         if _global_detailed_tracker is None:
#             _global_detailed_tracker = DetailedTimingTracker()
#     return _global_detailed_tracker


# def reset_detailed_timing_tracker() -> None:
#     global _global_detailed_tracker
#     with _global_detailed_lock:
#         _global_detailed_tracker = DetailedTimingTracker()



"""
Detailed timing tracker for SWE-agent execution profiling.

Produces a per-task JSON with fine-grained timing entries, each recording
the exact start/end time (relative to the task start), duration, and
contextual detail (commands, prompts, responses, etc.).

This version also adds a per-task Markdown report string under:
  execution_timeline_report
which summarizes and renders a timeline strip similar to "Monitor + Proxy".
"""

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TimingEntry:
    """A single timed event."""
    start_time_abs: float  # absolute time (time.perf_counter)
    end_time_abs: float = 0.0
    detail: str = ""
    extra: dict = field(default_factory=dict)  # prompt, response, command, etc.

    def to_dict(self, task_start_abs: float) -> dict:
        rel_start = self.start_time_abs - task_start_abs
        rel_end = self.end_time_abs - task_start_abs if self.end_time_abs > 0 else 0.0
        duration = self.end_time_abs - self.start_time_abs if self.end_time_abs > 0 else 0.0
        result = {
            "start_time": round(rel_start, 4),
            "end_time": round(rel_end, 4),
            "duration": round(duration, 4),
            "detail": self.detail,
        }
        # Merge extra fields into top-level entry dict (as you already do)
        result.update(self.extra)
        return result


DETAILED_CATEGORIES = [
    "process_bootstrap",
    "environment_provisioning",
    "workspace_initialization",
    "repository_scan",
    "diff_computation",
    "prompt_construction",
    "context_compaction",
    "llm_generation",
    "apply_file_changes",
    "file_creation",
    "shell_command_execution",
    "git_operations",
    "test_validation_execution",
    "retry_backoff",
    "cleanup_and_teardown",
]

# Commands that indicate test execution
TEST_COMMAND_PATTERNS = [
    "pytest", "python -m pytest", "python -m unittest",
    "nosetests", "tox", "./test", "make test", "make check",
    "python -m nose", "unittest", "py.test",
]

# Commands that are git operations
GIT_COMMAND_PATTERNS = [
    "git ",
]


@dataclass
class TaskDetailedTimings:
    """All detailed timing data for a single task."""
    task_id: str
    task_start_abs: float = 0.0
    task_end_abs: float = 0.0
    categories: dict[str, list[TimingEntry]] = field(default_factory=dict)

    def __post_init__(self):
        for cat in DETAILED_CATEGORIES:
            if cat not in self.categories:
                self.categories[cat] = []

    def add_entry(self, category: str, entry: TimingEntry) -> None:
        if category not in self.categories:
            self.categories[category] = []
        self.categories[category].append(entry)

    def remove_last_entry(self, category: str) -> Optional[TimingEntry]:
        """Remove and return the last entry from a category."""
        if category in self.categories and self.categories[category]:
            return self.categories[category].pop()
        return None

    def _build_timeline_string(self) -> str:
        """Build the 'overall_runtime' timeline string (existing compact version)."""
        if self.task_end_abs <= 0 or self.task_start_abs <= 0:
            return ""

        total_duration = self.task_end_abs - self.task_start_abs

        # Collect all entries with their relative times and categories
        all_events: list[tuple[float, float, str]] = []
        for cat, entries in self.categories.items():
            for entry in entries:
                rel_start = entry.start_time_abs - self.task_start_abs
                rel_end = entry.end_time_abs - self.task_start_abs if entry.end_time_abs > 0 else rel_start
                all_events.append((rel_start, rel_end, cat))

        # Sort by start time
        all_events.sort(key=lambda x: x[0])

        lines = [f"0.0s ----------------------- {total_duration:.1f}s"]
        for rel_start, rel_end, cat in all_events:
            lines.append(f"{rel_start:.1f} - {rel_end:.1f}s [{cat}]")

        return "\n".join(lines)

    # ----------------------------
    # Report helpers (Monitor+Proxy style)
    # ----------------------------
    def _human_label(self, category: str) -> str:
        mapping = {
            "process_bootstrap": "Process Bootstrap",
            "environment_provisioning": "Environment Provisioning",
            "workspace_initialization": "Workspace Initialization",
            "repository_scan": "Repository Scan",
            "diff_computation": "Diff Computation",
            "prompt_construction": "Prompt Construction",
            "context_compaction": "Context Compaction",
            "llm_generation": "LLM Generation",
            "apply_file_changes": "Apply File Changes",
            "file_creation": "File Creation",
            "shell_command_execution": "Shell Command Execution",
            "git_operations": "Git Operations",
            "test_validation_execution": "Test/Validation Execution",
            "retry_backoff": "Retry/Backoff",
            "cleanup_and_teardown": "Cleanup & Teardown",
        }
        return mapping.get(category, category)

    def _iter_completed_events(self) -> list[tuple[str, TimingEntry]]:
        events: list[tuple[str, TimingEntry]] = []
        for cat in DETAILED_CATEGORIES:
            for e in self.categories.get(cat, []):
                if e.end_time_abs and e.end_time_abs > 0:
                    events.append((cat, e))
        events.sort(key=lambda x: x[1].start_time_abs)
        return events

    def _sum_cat(self, cat: str) -> float:
        return sum(
            (e.end_time_abs - e.start_time_abs)
            for e in self.categories.get(cat, [])
            if e.end_time_abs and e.end_time_abs > 0
        )

    def _guess_file_path_from_detail(self, detail: str) -> Optional[str]:
        """
        Heuristic only.
        Your TimingEntry.detail for tool exec is typically the command_for_log (possibly truncated),
        so this tries to extract a path from common SWE-agent file edit/create actions.
        """
        parts = (detail or "").split()
        if not parts:
            return None
        cmd = parts[0]

        # str_replace_editor <sub> <path> ...
        if cmd == "str_replace_editor" and len(parts) >= 3:
            sub = parts[1]
            if sub in ("create", "str_replace", "insert", "view", "undo_edit"):
                return parts[2]

        # create <path>, edit <path>
        if cmd in ("create", "edit") and len(parts) >= 2:
            return parts[1]

        return None

    def _build_execution_timeline_report(self) -> str:
        """
        Produces a Markdown report similar to the "Execution Timeline (Monitor + Proxy)" example.
        Fields not captured by this tracker remain n/a.
        """
        if self.task_start_abs <= 0 or self.task_end_abs <= 0:
            return ""

        total = self.task_end_abs - self.task_start_abs

        # Summary numbers
        llm_calls = len(self.categories.get("llm_generation", []))
        llm_total = self._sum_cat("llm_generation")
        llm_avg = (llm_total / llm_calls) if llm_calls > 0 else 0.0

        file_events = len(self.categories.get("file_creation", [])) + len(self.categories.get("apply_file_changes", []))
        shell_cmds = len(self.categories.get("shell_command_execution", []))
        test_cmds = len(self.categories.get("test_validation_execution", []))
        git_cmds = len(self.categories.get("git_operations", []))

        # Token/cost proxy totals (only if present on llm_generation entries)
        in_tok = 0
        out_tok = 0
        total_tok = 0
        any_tokens = False
        cost_usd = 0.0
        any_cost = False

        for e in self.categories.get("llm_generation", []):
            if not (e.end_time_abs and e.end_time_abs > 0):
                continue
            if isinstance(e.extra, dict):
                if "input_tokens" in e.extra:
                    try:
                        in_tok += int(e.extra["input_tokens"])
                        any_tokens = True
                    except Exception:
                        pass
                if "output_tokens" in e.extra:
                    try:
                        out_tok += int(e.extra["output_tokens"])
                        any_tokens = True
                    except Exception:
                        pass
                if "total_tokens" in e.extra:
                    try:
                        total_tok += int(e.extra["total_tokens"])
                        any_tokens = True
                    except Exception:
                        pass
                if "cost_usd" in e.extra:
                    try:
                        cost_usd += float(e.extra["cost_usd"])
                        any_cost = True
                    except Exception:
                        pass

        in_tok_str = str(in_tok) if any_tokens else "n/a"
        out_tok_str = str(out_tok) if any_tokens else "n/a"
        total_tok_str = str(total_tok) if any_tokens else "n/a"
        cost_str = f"{cost_usd:.6f}" if any_cost else "n/a (not present in captured responses)"

        # Timeline strip
        lines: list[str] = []
        lines.append(f"0.0s --------------------------------------- {total:.1f}s")

        llm_idx = 0
        for cat, entry in self._iter_completed_events():
            rel_s = entry.start_time_abs - self.task_start_abs
            rel_e = entry.end_time_abs - self.task_start_abs
            label = self._human_label(cat)

            detail = (entry.detail or "").strip()
            if cat == "llm_generation":
                llm_idx += 1
                tok_note = ""
                if isinstance(entry.extra, dict) and "output_tokens" in entry.extra:
                    tok_note = f"; output_tokens={entry.extra.get('output_tokens', 'n/a')}"
                detail = f"Call {llm_idx}: {detail}{tok_note}".strip()
            elif cat in ("prompt_construction", "context_compaction"):
                if not detail:
                    detail = "Agent internal orchestration / no external event"

            lines.append(f"{rel_s:7.3f} - {rel_e:7.3f}s [{label}] {detail}".rstrip())

        timeline_strip = "\n".join(lines)

        # Phase breakdown (coarse mapping)
        phases = [
            (
                "Startup (bootstrap/env)",
                self._sum_cat("process_bootstrap")
                + self._sum_cat("environment_provisioning")
                + self._sum_cat("workspace_initialization"),
            ),
            (
                "Coordination (scan/diff/prompt)",
                self._sum_cat("repository_scan")
                + self._sum_cat("diff_computation")
                + self._sum_cat("prompt_construction")
                + self._sum_cat("context_compaction")
                + self._sum_cat("retry_backoff"),
            ),
            ("LLM Inference", self._sum_cat("llm_generation")),
            (
                "Tool Execution (shell/files/git/tests)",
                self._sum_cat("apply_file_changes")
                + self._sum_cat("file_creation")
                + self._sum_cat("shell_command_execution")
                + self._sum_cat("test_validation_execution")
                + self._sum_cat("git_operations"),
            ),
            ("Cleanup", self._sum_cat("cleanup_and_teardown")),
        ]

        phase_rows: list[str] = []
        phase_rows.append("| Phase | Time | % |")
        phase_rows.append("| --- | ---: | ---: |")
        for name, t in phases:
            pct = (100.0 * t / total) if total > 0 else 0.0
            phase_rows.append(f"| {name} | {t:.1f}s | {pct:.0f}% |")
        phase_rows.append(f"| **Total** | **{total:.1f}s** | **100%** |")
        phase_table = "\n".join(phase_rows)

        # LLM calls table (no TTFT/first-token data in this tracker -> n/a)
        llm_rows: list[str] = []
        llm_rows.append("| Call | Dispatch | Complete | Latency | In Tok | Out Tok | Total Tok | Cost (USD) |")
        llm_rows.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        llm_idx = 0
        for e in self.categories.get("llm_generation", []):
            if not (e.end_time_abs and e.end_time_abs > 0):
                continue
            llm_idx += 1
            rel_s = e.start_time_abs - self.task_start_abs
            rel_e = e.end_time_abs - self.task_start_abs
            lat = e.end_time_abs - e.start_time_abs
            it = (e.extra.get("input_tokens") if isinstance(e.extra, dict) else None) or "n/a"
            ot = (e.extra.get("output_tokens") if isinstance(e.extra, dict) else None) or "n/a"
            tt = (e.extra.get("total_tokens") if isinstance(e.extra, dict) else None) or "n/a"
            cu = (e.extra.get("cost_usd") if isinstance(e.extra, dict) else None) or "n/a"
            llm_rows.append(f"| {llm_idx} | +{rel_s:.3f}s | +{rel_e:.3f}s | {lat:.3f}s | {it} | {ot} | {tt} | {cu} |")
        llm_table = "\n".join(llm_rows)

        # File events table (best-effort)
        file_rows: list[str] = []
        file_rows.append("| Time | Event | Path/Detail |")
        file_rows.append("| ---: | --- | --- |")
        for cat in ("file_creation", "apply_file_changes"):
            for e in self.categories.get(cat, []):
                if not (e.end_time_abs and e.end_time_abs > 0):
                    continue
                rel_s = e.start_time_abs - self.task_start_abs
                event = "create" if cat == "file_creation" else "change"
                path = self._guess_file_path_from_detail(e.detail) or (e.detail or "")
                path_cell = f"`{path}`" if path else "`(unknown)`"
                file_rows.append(f"| +{rel_s:.3f}s | {event} | {path_cell} |")
        file_table = "\n".join(file_rows)

        # Not tracked here
        peak_cpu = "n/a"
        peak_rss = "n/a"

        report = f"""# Execution Timeline (Monitor + Proxy)

## Summary

- Duration: {total:.3f}s
- LLM calls: {llm_calls}
- LLM total latency: {llm_total:.3f}s
- LLM avg latency: {llm_avg:.3f}s
- Input tokens (proxy): {in_tok_str}
- Output tokens (proxy): {out_tok_str}
- Total tokens (proxy): {total_tok_str}
- Total cost (USD, proxy): {cost_str}
- File events: {file_events}
- Shell commands: {shell_cmds}
- Test/validation commands: {test_cmds}
- Git commands: {git_cmds}
- Peak CPU%: {peak_cpu}
- Peak RSS (MB): {peak_rss}

## Timeline Strip (Relative)

```text
{timeline_strip}
```

## Phase Breakdown

{phase_table}

### LLM Calls

{llm_table}

### File Events

{file_table}

### Lifecycle

- +0.000s `run_start`
- +{total:.3f}s `run_end`
"""
        return report

    def _aggregate_token_cost_summary(self) -> dict:
        """Aggregate input/output tokens and cost across all llm_generation entries."""
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0
        any_tokens = False
        any_cost = False
        for e in self.categories.get("llm_generation", []):
            if not (e.end_time_abs and e.end_time_abs > 0):
                continue
            if isinstance(e.extra, dict):
                if "input_tokens" in e.extra:
                    try:
                        total_input_tokens += int(e.extra["input_tokens"])
                        any_tokens = True
                    except Exception:
                        pass
                if "output_tokens" in e.extra:
                    try:
                        total_output_tokens += int(e.extra["output_tokens"])
                        any_tokens = True
                    except Exception:
                        pass
                if "cost_usd" in e.extra:
                    try:
                        total_cost_usd += float(e.extra["cost_usd"])
                        any_cost = True
                    except Exception:
                        pass
        summary: dict = {}
        if any_tokens:
            summary["total_input_tokens"] = total_input_tokens
            summary["total_output_tokens"] = total_output_tokens
            summary["total_tokens"] = total_input_tokens + total_output_tokens
        if any_cost:
            summary["total_cost_usd"] = round(total_cost_usd, 6)
        return summary

    def to_dict(self) -> dict:
        total_duration = (self.task_end_abs - self.task_start_abs) if self.task_end_abs > 0 else 0.0

        categories_dict = {}
        for cat in DETAILED_CATEGORIES:
            entries = self.categories.get(cat, [])
            total_cat_duration = sum(
                (e.end_time_abs - e.start_time_abs) for e in entries if e.end_time_abs > 0
            )
            entries_dict = {}
            for idx, entry in enumerate(entries, 1):
                entries_dict[str(idx)] = entry.to_dict(self.task_start_abs)
            categories_dict[cat] = {
                "total_duration": round(total_cat_duration, 4),
                "count": len(entries),
                "entries": entries_dict,
            }

        # Compute accounted time
        accounted = sum(categories_dict[cat]["total_duration"] for cat in DETAILED_CATEGORIES)

        result = {
            "task_id": self.task_id,
            "overall_duration": round(total_duration, 4),
            "accounted_time": round(accounted, 4),
            "unaccounted_time": round(total_duration - accounted, 4) if total_duration > 0 else 0.0,
            "token_and_cost_summary": self._aggregate_token_cost_summary(),
            "categories": categories_dict,
            "overall_runtime": self._build_timeline_string(),
            # NEW: rich markdown report string
            "execution_timeline_report": self._build_execution_timeline_report(),
        }
        return result


class DetailedTimingTracker:
    """Thread-safe detailed timing tracker.

    Usage:
        tracker.start_task("task-id")
        key = tracker.start_entry("llm_generation", detail="LLM call", extra={...})
        # ... do work ...
        tracker.end_entry(key, "llm_generation", extra={...})
        tracker.end_task()
        tracker.save_to_file(path)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.task_timings: dict[str, TaskDetailedTimings] = {}
        # Thread -> task_id mapping
        self._thread_task_ids: dict[int, str] = {}
        # Pending timers: key -> (start_time_abs, task_id, detail, extra)
        self._pending: dict[str, tuple[float, str, str, dict]] = {}

    @property
    def current_task_id(self) -> Optional[str]:
        return self._thread_task_ids.get(threading.get_ident())

    def start_task(self, task_id: str) -> None:
        tid = threading.get_ident()
        with self._lock:
            self._thread_task_ids[tid] = task_id
            if task_id not in self.task_timings:
                self.task_timings[task_id] = TaskDetailedTimings(task_id=task_id)
            self.task_timings[task_id].task_start_abs = time.perf_counter()

    def end_task(self) -> None:
        tid = threading.get_ident()
        with self._lock:
            task_id = self._thread_task_ids.get(tid)
            if task_id and task_id in self.task_timings:
                self.task_timings[task_id].task_end_abs = time.perf_counter()
                del self._thread_task_ids[tid]

    def start_entry(self, category: str, detail: str = "", extra: Optional[dict] = None) -> str:
        """Start timing an entry. Returns a key to pass to end_entry."""
        now = time.perf_counter()
        key = f"{category}_{now}_{threading.get_ident()}"
        with self._lock:
            task_id = self._thread_task_ids.get(threading.get_ident(), "")
            self._pending[key] = (now, task_id, detail, extra or {})
        return key

    def end_entry(self, key: str, category: str, extra: Optional[dict] = None) -> None:
        """End a timed entry and record it."""
        now = time.perf_counter()
        with self._lock:
            if key not in self._pending:
                return
            start_abs, task_id, detail, start_extra = self._pending.pop(key)
            if not task_id or task_id not in self.task_timings:
                return
            merged_extra = {**start_extra, **(extra or {})}
            entry = TimingEntry(
                start_time_abs=start_abs,
                end_time_abs=now,
                detail=detail,
                extra=merged_extra,
            )
            self.task_timings[task_id].add_entry(category, entry)

    def add_completed_entry(
        self,
        category: str,
        start_abs: float,
        end_abs: float,
        detail: str = "",
        extra: Optional[dict] = None,
    ) -> None:
        """Add an already-completed timing entry directly."""
        with self._lock:
            task_id = self._thread_task_ids.get(threading.get_ident())
            if not task_id or task_id not in self.task_timings:
                return
            entry = TimingEntry(
                start_time_abs=start_abs,
                end_time_abs=end_abs,
                detail=detail,
                extra=extra or {},
            )
            self.task_timings[task_id].add_entry(category, entry)

    def move_last_entry(
        self,
        from_category: str,
        to_category: str,
        rename_detail: Optional[str] = None,
        extra_update: Optional[dict] = None,
    ) -> None:
        """Move the last entry from one category to another.
        Used for retroactively reclassifying LLM calls as retry/backoff.
        """
        with self._lock:
            task_id = self._thread_task_ids.get(threading.get_ident())
            if not task_id or task_id not in self.task_timings:
                return
            entry = self.task_timings[task_id].remove_last_entry(from_category)
            if entry is not None:
                if rename_detail is not None:
                    entry.detail = rename_detail
                if extra_update:
                    try:
                        entry.extra.update(extra_update)
                    except Exception:
                        pass
                self.task_timings[task_id].add_entry(to_category, entry)

    def get_retry_count(self) -> int:
        """Get current count of retry entries for the current task."""
        with self._lock:
            task_id = self._thread_task_ids.get(threading.get_ident())
            if not task_id or task_id not in self.task_timings:
                return 0
            return len(self.task_timings[task_id].categories.get("retry_backoff", []))

    def save_to_file(self, output_path: Path) -> None:
        """Save all task timings to a JSON file."""
        data = {}
        for task_id, timings in self.task_timings.items():
            data[task_id] = timings.to_dict()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2))


# Global instance
_global_detailed_tracker: Optional[DetailedTimingTracker] = None
_global_detailed_lock = threading.Lock()


def get_detailed_timing_tracker() -> DetailedTimingTracker:
    global _global_detailed_tracker
    with _global_detailed_lock:
        if _global_detailed_tracker is None:
            _global_detailed_tracker = DetailedTimingTracker()
    return _global_detailed_tracker


def reset_detailed_timing_tracker() -> None:
    global _global_detailed_tracker
    with _global_detailed_lock:
        _global_detailed_tracker = DetailedTimingTracker()
