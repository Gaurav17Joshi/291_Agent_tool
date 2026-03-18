# # """Timing tracker for profiling SWE-agent execution"""
# # import time
# # from typing import Dict, List, Optional
# # from pathlib import Path
# # import json
# # from dataclasses import dataclass, field, asdict


# # @dataclass
# # class TimingStats:
# #     """Statistics for a single timing category"""
# #     total_time: float = 0.0
# #     count: int = 0
    
# #     def add(self, duration: float):
# #         self.total_time += duration
# #         self.count += 1
    
# #     def to_dict(self) -> dict:
# #         return {
# #             "total_time": self.total_time,
# #             "count": self.count,
# #             "average_time": self.total_time / self.count if self.count > 0 else 0.0
# #         }


# # @dataclass
# # class TaskTimings:
# #     """Timing data for a single task"""
# #     task_id: str
# #     llm_inference: TimingStats = field(default_factory=TimingStats)
# #     shell_commands: TimingStats = field(default_factory=TimingStats)
# #     edit_commands: TimingStats = field(default_factory=TimingStats)
# #     file_views: TimingStats = field(default_factory=TimingStats)
# #     file_searches: TimingStats = field(default_factory=TimingStats)
# #     context_management: TimingStats = field(default_factory=TimingStats)
# #     other_tools: TimingStats = field(default_factory=TimingStats)
# #     total_time: float = 0.0
    
# #     def to_dict(self) -> dict:
# #         return {
# #             "task_id": self.task_id,
# #             "llm_inference": self.llm_inference.to_dict(),
# #             "shell_commands": self.shell_commands.to_dict(),
# #             "edit_commands": self.edit_commands.to_dict(),
# #             "file_views": self.file_views.to_dict(),
# #             "file_searches": self.file_searches.to_dict(),
# #             "context_management": self.context_management.to_dict(),
# #             "other_tools": self.other_tools.to_dict(),
# #             "total_time": self.total_time
# #         }


# # class TimingTracker:
# #     """Tracks timing information across task execution"""
    
# #     def __init__(self):
# #         self.task_timings: Dict[str, TaskTimings] = {}
# #         self.current_task_id: Optional[str] = None
# #         self._start_times: Dict[str, float] = {}
        
# #     def start_task(self, task_id: str):
# #         """Start tracking a new task"""
# #         self.current_task_id = task_id
# #         if task_id not in self.task_timings:
# #             self.task_timings[task_id] = TaskTimings(task_id=task_id)
# #         self._start_times[f"task_{task_id}"] = time.perf_counter()
    
# #     def end_task(self):
# #         """End tracking current task"""
# #         if self.current_task_id:
# #             key = f"task_{self.current_task_id}"
# #             if key in self._start_times:
# #                 duration = time.perf_counter() - self._start_times[key]
# #                 self.task_timings[self.current_task_id].total_time = duration
# #                 del self._start_times[key]
# #             self.current_task_id = None
    
# #     def start_timer(self, category: str) -> str:
# #         """Start a timer for a category, returns timer key"""
# #         key = f"{category}_{time.perf_counter()}_{id(self)}"
# #         self._start_times[key] = time.perf_counter()
# #         return key
    
# #     def end_timer(self, key: str, category: str):
# #         """End a timer and record the duration"""
# #         if key not in self._start_times or not self.current_task_id:
# #             return
        
# #         duration = time.perf_counter() - self._start_times[key]
# #         del self._start_times[key]
        
# #         timings = self.task_timings[self.current_task_id]
        
# #         if category == "llm_inference":
# #             timings.llm_inference.add(duration)
# #         elif category == "shell_commands":
# #             timings.shell_commands.add(duration)
# #         elif category == "edit_commands":
# #             timings.edit_commands.add(duration)
# #         elif category == "file_views":
# #             timings.file_views.add(duration)
# #         elif category == "file_searches":
# #             timings.file_searches.add(duration)
# #         elif category == "context_management":
# #             timings.context_management.add(duration)
# #         else:
# #             timings.other_tools.add(duration)
    
# #     def get_aggregated_stats(self) -> dict:
# #         """Get aggregated statistics across all tasks"""
# #         if not self.task_timings:
# #             return {}
        
# #         agg = TaskTimings(task_id="AGGREGATE")
        
# #         for task_timing in self.task_timings.values():
# #             agg.llm_inference.total_time += task_timing.llm_inference.total_time
# #             agg.llm_inference.count += task_timing.llm_inference.count
            
# #             agg.shell_commands.total_time += task_timing.shell_commands.total_time
# #             agg.shell_commands.count += task_timing.shell_commands.count
            
# #             agg.edit_commands.total_time += task_timing.edit_commands.total_time
# #             agg.edit_commands.count += task_timing.edit_commands.count
            
# #             agg.file_views.total_time += task_timing.file_views.total_time
# #             agg.file_views.count += task_timing.file_views.count
            
# #             agg.file_searches.total_time += task_timing.file_searches.total_time
# #             agg.file_searches.count += task_timing.file_searches.count
            
# #             agg.context_management.total_time += task_timing.context_management.total_time
# #             agg.context_management.count += task_timing.context_management.count
            
# #             agg.other_tools.total_time += task_timing.other_tools.total_time
# #             agg.other_tools.count += task_timing.other_tools.count
            
# #             agg.total_time += task_timing.total_time
        
# #         return agg.to_dict()
    
# #     def save_to_file(self, output_path: Path):
# #         """Save timing data to JSON file"""
# #         data = {
# #             "per_task": {task_id: timing.to_dict() for task_id, timing in self.task_timings.items()},
# #             "aggregated": self.get_aggregated_stats()
# #         }
        
# #         output_path.write_text(json.dumps(data, indent=2))


# # # Global timing tracker instance
# # _global_tracker: Optional[TimingTracker] = None


# # def get_timing_tracker() -> TimingTracker:
# #     """Get or create the global timing tracker"""
# #     global _global_tracker
# #     if _global_tracker is None:
# #         _global_tracker = TimingTracker()
# #     return _global_tracker


# # def reset_timing_tracker():
# #     """Reset the global timing tracker"""
# #     global _global_tracker
# #     _global_tracker = TimingTracker()


# """Timing tracker for profiling SWE-agent execution"""
# import time
# from typing import Dict, List, Optional, Any
# from pathlib import Path
# import json
# from dataclasses import dataclass, field


# @dataclass
# class CommandEntry:
#     """A single command execution record"""
#     command: str
#     duration: float
#     timestamp: float = 0.0
    
#     def to_dict(self) -> dict:
#         return {
#             "command": self.command,
#             "duration": self.duration,
#             "timestamp": self.timestamp
#         }


# @dataclass
# class TimingStats:
#     """Statistics for a single timing category"""
#     total_time: float = 0.0
#     count: int = 0
#     commands: List[CommandEntry] = field(default_factory=list)
    
#     def add(self, duration: float, command: str = ""):
#         self.total_time += duration
#         self.count += 1
#         self.commands.append(CommandEntry(
#             command=command,
#             duration=duration,
#             timestamp=time.time()
#         ))
    
#     def to_dict(self, include_commands: bool = True) -> dict:
#         result = {
#             "total_time": self.total_time,
#             "count": self.count,
#             "average_time": self.total_time / self.count if self.count > 0 else 0.0
#         }
#         if include_commands:
#             result["commands"] = [cmd.to_dict() for cmd in self.commands]
#         return result


# @dataclass
# class TaskTimings:
#     """Timing data for a single task"""
#     task_id: str
#     llm_inference: TimingStats = field(default_factory=TimingStats)
#     shell_commands: TimingStats = field(default_factory=TimingStats)
#     edit_commands: TimingStats = field(default_factory=TimingStats)
#     file_views: TimingStats = field(default_factory=TimingStats)
#     file_searches: TimingStats = field(default_factory=TimingStats)
#     context_management: TimingStats = field(default_factory=TimingStats)
#     other_tools: TimingStats = field(default_factory=TimingStats)
#     total_time: float = 0.0
    
#     def to_dict(self, include_commands: bool = True) -> dict:
#         return {
#             "task_id": self.task_id,
#             "llm_inference": self.llm_inference.to_dict(include_commands),
#             "shell_commands": self.shell_commands.to_dict(include_commands),
#             "edit_commands": self.edit_commands.to_dict(include_commands),
#             "file_views": self.file_views.to_dict(include_commands),
#             "file_searches": self.file_searches.to_dict(include_commands),
#             "context_management": self.context_management.to_dict(include_commands),
#             "other_tools": self.other_tools.to_dict(include_commands),
#             "total_time": self.total_time
#         }


# class TimingTracker:
#     """Tracks timing information across task execution"""
    
#     def __init__(self):
#         self.task_timings: Dict[str, TaskTimings] = {}
#         self.current_task_id: Optional[str] = None
#         self._start_times: Dict[str, float] = {}
#         self._pending_commands: Dict[str, str] = {}  # Maps timer_key to command string
        
#     def start_task(self, task_id: str):
#         """Start tracking a new task"""
#         self.current_task_id = task_id
#         if task_id not in self.task_timings:
#             self.task_timings[task_id] = TaskTimings(task_id=task_id)
#         self._start_times[f"task_{task_id}"] = time.perf_counter()
    
#     def end_task(self):
#         """End tracking current task"""
#         if self.current_task_id:
#             key = f"task_{self.current_task_id}"
#             if key in self._start_times:
#                 duration = time.perf_counter() - self._start_times[key]
#                 self.task_timings[self.current_task_id].total_time = duration
#                 del self._start_times[key]
#             self.current_task_id = None
    
#     def start_timer(self, category: str, command: str = "") -> str:
#         """Start a timer for a category, returns timer key"""
#         key = f"{category}_{time.perf_counter()}_{id(self)}"
#         self._start_times[key] = time.perf_counter()
#         self._pending_commands[key] = command  # Store the command
#         return key
    
#     def end_timer(self, key: str, category: str):
#         """End a timer and record the duration"""
#         if key not in self._start_times or not self.current_task_id:
#             return
        
#         duration = time.perf_counter() - self._start_times[key]
#         command = self._pending_commands.get(key, "")
        
#         del self._start_times[key]
#         if key in self._pending_commands:
#             del self._pending_commands[key]
        
#         timings = self.task_timings[self.current_task_id]
        
#         if category == "llm_inference":
#             timings.llm_inference.add(duration, command)
#         elif category == "shell_commands":
#             timings.shell_commands.add(duration, command)
#         elif category == "edit_commands":
#             timings.edit_commands.add(duration, command)
#         elif category == "file_views":
#             timings.file_views.add(duration, command)
#         elif category == "file_searches":
#             timings.file_searches.add(duration, command)
#         elif category == "context_management":
#             timings.context_management.add(duration, command)
#         else:
#             timings.other_tools.add(duration, command)
    
#     def get_aggregated_stats(self, include_commands: bool = False) -> dict:
#         """Get aggregated statistics across all tasks"""
#         if not self.task_timings:
#             return {}
        
#         agg = TaskTimings(task_id="AGGREGATE")
        
#         for task_timing in self.task_timings.values():
#             # Aggregate llm_inference
#             agg.llm_inference.total_time += task_timing.llm_inference.total_time
#             agg.llm_inference.count += task_timing.llm_inference.count
#             if include_commands:
#                 agg.llm_inference.commands.extend(task_timing.llm_inference.commands)
            
#             # Aggregate shell_commands
#             agg.shell_commands.total_time += task_timing.shell_commands.total_time
#             agg.shell_commands.count += task_timing.shell_commands.count
#             if include_commands:
#                 agg.shell_commands.commands.extend(task_timing.shell_commands.commands)
            
#             # Aggregate edit_commands
#             agg.edit_commands.total_time += task_timing.edit_commands.total_time
#             agg.edit_commands.count += task_timing.edit_commands.count
#             if include_commands:
#                 agg.edit_commands.commands.extend(task_timing.edit_commands.commands)
            
#             # Aggregate file_views
#             agg.file_views.total_time += task_timing.file_views.total_time
#             agg.file_views.count += task_timing.file_views.count
#             if include_commands:
#                 agg.file_views.commands.extend(task_timing.file_views.commands)
            
#             # Aggregate file_searches
#             agg.file_searches.total_time += task_timing.file_searches.total_time
#             agg.file_searches.count += task_timing.file_searches.count
#             if include_commands:
#                 agg.file_searches.commands.extend(task_timing.file_searches.commands)
            
#             # Aggregate context_management
#             agg.context_management.total_time += task_timing.context_management.total_time
#             agg.context_management.count += task_timing.context_management.count
#             if include_commands:
#                 agg.context_management.commands.extend(task_timing.context_management.commands)
            
#             # Aggregate other_tools
#             agg.other_tools.total_time += task_timing.other_tools.total_time
#             agg.other_tools.count += task_timing.other_tools.count
#             if include_commands:
#                 agg.other_tools.commands.extend(task_timing.other_tools.commands)
            
#             agg.total_time += task_timing.total_time
        
#         return agg.to_dict(include_commands)
    
#     def save_to_file(self, output_path: Path, include_commands: bool = True):
#         """Save timing data to JSON file"""
#         data = {
#             "per_task": {
#                 task_id: timing.to_dict(include_commands) 
#                 for task_id, timing in self.task_timings.items()
#             },
#             "aggregated": self.get_aggregated_stats(include_commands=False)  # Keep aggregate compact
#         }
        
#         output_path.write_text(json.dumps(data, indent=2))
    
#     def get_command_summary(self) -> dict:
#         """Get a summary of all commands by category across all tasks"""
#         summary = {
#             "llm_inference": [],
#             "shell_commands": [],
#             "edit_commands": [],
#             "file_views": [],
#             "file_searches": [],
#             "context_management": [],
#             "other_tools": []
#         }
        
#         for task_timing in self.task_timings.values():
#             summary["llm_inference"].extend([
#                 {"task": task_timing.task_id, **cmd.to_dict()} 
#                 for cmd in task_timing.llm_inference.commands
#             ])
#             summary["shell_commands"].extend([
#                 {"task": task_timing.task_id, **cmd.to_dict()} 
#                 for cmd in task_timing.shell_commands.commands
#             ])
#             summary["edit_commands"].extend([
#                 {"task": task_timing.task_id, **cmd.to_dict()} 
#                 for cmd in task_timing.edit_commands.commands
#             ])
#             summary["file_views"].extend([
#                 {"task": task_timing.task_id, **cmd.to_dict()} 
#                 for cmd in task_timing.file_views.commands
#             ])
#             summary["file_searches"].extend([
#                 {"task": task_timing.task_id, **cmd.to_dict()} 
#                 for cmd in task_timing.file_searches.commands
#             ])
#             summary["context_management"].extend([
#                 {"task": task_timing.task_id, **cmd.to_dict()} 
#                 for cmd in task_timing.context_management.commands
#             ])
#             summary["other_tools"].extend([
#                 {"task": task_timing.task_id, **cmd.to_dict()} 
#                 for cmd in task_timing.other_tools.commands
#             ])
        
#         return summary


# # Global timing tracker instance
# _global_tracker: Optional[TimingTracker] = None


# def get_timing_tracker() -> TimingTracker:
#     """Get or create the global timing tracker"""
#     global _global_tracker
#     if _global_tracker is None:
#         _global_tracker = TimingTracker()
#     return _global_tracker


# def reset_timing_tracker():
#     """Reset the global timing tracker"""
#     global _global_tracker
#     _global_tracker = TimingTracker()

"""Timing tracker for profiling SWE-agent execution"""
import time
import threading
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from dataclasses import dataclass, field


@dataclass
class CommandEntry:
    """A single command execution record"""
    command: str
    duration: float
    timestamp: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "duration": self.duration,
            "timestamp": self.timestamp
        }


@dataclass
class TimingStats:
    """Statistics for a single timing category"""
    total_time: float = 0.0
    count: int = 0
    commands: List[CommandEntry] = field(default_factory=list)
    
    def add(self, duration: float, command: str = ""):
        self.total_time += duration
        self.count += 1
        self.commands.append(CommandEntry(
            command=command,
            duration=duration,
            timestamp=time.time()
        ))
    
    def to_dict(self, include_commands: bool = True) -> dict:
        result = {
            "total_time": self.total_time,
            "count": self.count,
            "average_time": self.total_time / self.count if self.count > 0 else 0.0
        }
        if include_commands:
            result["commands"] = [cmd.to_dict() for cmd in self.commands]
        return result


# All recognized timing categories. When adding a new one, add it here AND
# as a field on TaskTimings.
TIMING_CATEGORIES = [
    "llm_inference",
    "shell_commands",
    "edit_commands",
    "file_views",
    "file_searches",
    "context_management",
    "other_tools",
    "environment_setup",
    "environment_teardown",
    "agent_setup",
    "state_retrieval",
]


@dataclass
class TaskTimings:
    """Timing data for a single task"""
    task_id: str
    llm_inference: TimingStats = field(default_factory=TimingStats)
    shell_commands: TimingStats = field(default_factory=TimingStats)
    edit_commands: TimingStats = field(default_factory=TimingStats)
    file_views: TimingStats = field(default_factory=TimingStats)
    file_searches: TimingStats = field(default_factory=TimingStats)
    context_management: TimingStats = field(default_factory=TimingStats)
    other_tools: TimingStats = field(default_factory=TimingStats)
    environment_setup: TimingStats = field(default_factory=TimingStats)
    environment_teardown: TimingStats = field(default_factory=TimingStats)
    agent_setup: TimingStats = field(default_factory=TimingStats)
    state_retrieval: TimingStats = field(default_factory=TimingStats)
    total_time: float = 0.0
    
    def _get_stats(self, category: str) -> TimingStats:
        """Get the TimingStats object for a given category name."""
        return getattr(self, category)
    
    def to_dict(self, include_commands: bool = True) -> dict:
        result: dict[str, Any] = {"task_id": self.task_id}
        for cat in TIMING_CATEGORIES:
            result[cat] = self._get_stats(cat).to_dict(include_commands)
        result["total_time"] = self.total_time
        # Compute accounted vs unaccounted time
        accounted = sum(self._get_stats(cat).total_time for cat in TIMING_CATEGORIES)
        result["accounted_time"] = accounted
        result["unaccounted_time"] = self.total_time - accounted if self.total_time > 0 else 0.0
        return result


class TimingTracker:
    """Tracks timing information across task execution.
    
    Thread-safe: each timer key is associated with a specific task_id at
    creation time, so multi-worker runs record to the correct task.
    """
    
    def __init__(self):
        self.task_timings: Dict[str, TaskTimings] = {}
        self._lock = threading.Lock()
        # Maps thread id -> current task id (thread-safe)
        self._thread_task_ids: Dict[int, str] = {}
        self._start_times: Dict[str, float] = {}
        self._pending_commands: Dict[str, str] = {}
        # Maps timer_key -> task_id so end_timer records to the right task
        self._timer_task_ids: Dict[str, str] = {}
    
    @property
    def current_task_id(self) -> Optional[str]:
        """Get the current task id for this thread."""
        return self._thread_task_ids.get(threading.get_ident())
    
    def start_task(self, task_id: str):
        """Start tracking a new task"""
        tid = threading.get_ident()
        with self._lock:
            self._thread_task_ids[tid] = task_id
            if task_id not in self.task_timings:
                self.task_timings[task_id] = TaskTimings(task_id=task_id)
            self._start_times[f"task_{task_id}"] = time.perf_counter()
    
    def end_task(self):
        """End tracking current task"""
        tid = threading.get_ident()
        with self._lock:
            task_id = self._thread_task_ids.get(tid)
            if task_id:
                key = f"task_{task_id}"
                if key in self._start_times:
                    duration = time.perf_counter() - self._start_times[key]
                    self.task_timings[task_id].total_time = duration
                    del self._start_times[key]
                del self._thread_task_ids[tid]
    
    def start_timer(self, category: str, command: str = "") -> str:
        """Start a timer for a category, returns timer key"""
        key = f"{category}_{time.perf_counter()}_{threading.get_ident()}"
        with self._lock:
            self._start_times[key] = time.perf_counter()
            self._pending_commands[key] = command
            # Remember which task this timer belongs to
            task_id = self.current_task_id
            if task_id:
                self._timer_task_ids[key] = task_id
        return key
    
    def end_timer(self, key: str, category: str):
        """End a timer and record the duration"""
        with self._lock:
            if key not in self._start_times:
                return
            
            # Use the task_id that was active when the timer STARTED
            task_id = self._timer_task_ids.get(key) or self.current_task_id
            if not task_id or task_id not in self.task_timings:
                # Clean up and bail
                self._start_times.pop(key, None)
                self._pending_commands.pop(key, None)
                self._timer_task_ids.pop(key, None)
                return
            
            duration = time.perf_counter() - self._start_times[key]
            command = self._pending_commands.get(key, "")
            
            del self._start_times[key]
            self._pending_commands.pop(key, None)
            self._timer_task_ids.pop(key, None)
            
            timings = self.task_timings[task_id]
            
            # Record to the appropriate category
            if hasattr(timings, category) and isinstance(getattr(timings, category), TimingStats):
                getattr(timings, category).add(duration, command)
            else:
                timings.other_tools.add(duration, command)
    
    def get_aggregated_stats(self, include_commands: bool = False) -> dict:
        """Get aggregated statistics across all tasks"""
        if not self.task_timings:
            return {}
        
        agg = TaskTimings(task_id="AGGREGATE")
        
        for task_timing in self.task_timings.values():
            for cat in TIMING_CATEGORIES:
                src = task_timing._get_stats(cat)
                dst = agg._get_stats(cat)
                dst.total_time += src.total_time
                dst.count += src.count
                if include_commands:
                    dst.commands.extend(src.commands)
            agg.total_time += task_timing.total_time
        
        return agg.to_dict(include_commands)
    
    def save_to_file(self, output_path: Path, include_commands: bool = True):
        """Save timing data to JSON file"""
        data = {
            "per_task": {
                task_id: timing.to_dict(include_commands) 
                for task_id, timing in self.task_timings.items()
            },
            "aggregated": self.get_aggregated_stats(include_commands=False)
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2))
    
    def get_command_summary(self) -> dict:
        """Get a summary of all commands by category across all tasks"""
        summary = {cat: [] for cat in TIMING_CATEGORIES}
        
        for task_timing in self.task_timings.values():
            for cat in TIMING_CATEGORIES:
                stats = task_timing._get_stats(cat)
                summary[cat].extend([
                    {"task": task_timing.task_id, **cmd.to_dict()} 
                    for cmd in stats.commands
                ])
        
        return summary


# Global timing tracker instance
_global_tracker: Optional[TimingTracker] = None
_global_lock = threading.Lock()


def get_timing_tracker() -> TimingTracker:
    """Get or create the global timing tracker"""
    global _global_tracker
    with _global_lock:
        if _global_tracker is None:
            _global_tracker = TimingTracker()
    return _global_tracker


def reset_timing_tracker():
    """Reset the global timing tracker"""
    global _global_tracker
    with _global_lock:
        _global_tracker = TimingTracker()