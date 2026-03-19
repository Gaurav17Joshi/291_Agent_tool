from datetime import datetime

import ast
import time
import psutil
from pathlib import Path

def extract_time(line):
    time = line.split(maxsplit=2)
    if len(time) >= 2:
        return time[0] + " " + time[1] 

def find_time_diff(start, end):
    time1 = datetime.strptime(start, "%Y-%m-%d %H:%M:%S.%f")
    time2 = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f")
    
    total_time = time2 - time1
    return round(total_time.total_seconds(), 3)

def extract_tool_name(line):
    tool = line.split('"toolName":"')
    if len(tool) > 1:
        res_tool = tool[1].split('"')[0]
        return res_tool

def extract_key_events(lines):
    events = []
    llm_call_num = 0

    for line in lines:
        time = extract_time(line)

        if "All services initialization complete" in line:
            events.append(("startup_end", time, None))
        elif "Creating chat completion stream" in line:
            llm_call_num += 1
            events.append(("llm_call_start", time, llm_call_num))
        elif "Received chunk" in line and '"chunkCount":1' in line:
            events.append(("ttft", time, llm_call_num))
        elif "Stream complete" in line:
            events.append(("llm_gen_end", time, llm_call_num))
        elif "Executing tool" in line:
            tool_name = extract_tool_name(line)
            events.append(("tool_exec_start", time, tool_name))
        elif "Tool execution completed" in line:
            events.append(("tool_exec_end", time, None))
        
    return events

def map_events(events, first_time):
    result = []
    
    for i in range(len(events) - 1):
        event = events[i]
        next_event = events[i + 1]
        
        event_type = event[0]
        event_time = event[1]
        event_data = event[2]
        next_time = next_event[1]
        
        start = find_time_diff(first_time, event_time)
        end = find_time_diff(first_time, next_time)
        
        name = ""
        if event_type == "startup_end":
            name = "Startup"
        elif event_type == "llm_call_start":
            name = "LLM Wait"
        elif event_type == "ttft":
            name = "LLM Generation"
        elif event_type == "tool_exec_start":
            name = "Tool Execution"
        
        if name != "":
            last = result[-1] if len(result) > 0 else None
            
            if last is not None and last["name"] == name:
                last["end"] = end
            else:
                item = {"name": name, "start": start, "end": end, "data": event_data}
                result.append(item)
    
    return result

def capture_cpu_usage(pid, interval=0.2):
    try:
        p = psutil.Process(pid)
        p.cpu_percent(None)
    except Exception:
        return 0.0, 0.0

    peak_cpu = 0.0
    peak_rss_mb = 0.0
    
    while True:
        try:
            if not p.is_running():
                break
            cpu = p.cpu_percent(None)
            rss_mb = p.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            break
        except psutil.Error:
            break

        if cpu > peak_cpu:
            peak_cpu = cpu
        if rss_mb > peak_rss_mb:
            peak_rss_mb = rss_mb

        time.sleep(interval)

    return round(peak_cpu, 2), round(peak_rss_mb, 2)


def extract_tokens(line):
    if "Stream complete" in line:
        payload_start = line.find("{")
        if payload_start != -1:
            d = ast.literal_eval(line[payload_start:])
            return d.get("inputTokens"), d.get("outputTokens")
           
    if '"usage"' in line and '"prompt_tokens"' in line:
        last_part = line.split()[-1]
        if last_part.endswith('}'):
            d = ast.literal_eval(last_part)
            if 'usage' in d:
                inp = d['usage']['prompt_tokens']
                out = d['usage']['completion_tokens']
                return inp, out

    return None, None
    
def process_cn():
    project_root = Path(__file__).resolve().parent
    path = project_root / "continue" / ".continue" / "logs" / "cn.log"
    
    with open(path, "r") as f:
        lines = f.readlines()

    if len(lines) < 2:
        print("Log file too short, run likely failed")
        return

    first_time = extract_time(lines[0])
    last_time = extract_time(lines[-1])

    if first_time is None or last_time is None:
        print("Could not parse timestamps from log")
        return

    token_list = []
    for line in lines:
        inp, out = extract_tokens(line)
        if inp is not None and out is not None:
            token_list.append({"input": inp, "output": out})

    mapped_events = map_events(extract_key_events(lines), first_time)
    total = find_time_diff(first_time, last_time)
    print("Total: " + str(total) + "s\n")
    
    token_idx = 0
    for mapped_event in mapped_events:
        data = mapped_event["data"]
        
        line = str(mapped_event["start"]) + " - " + str(mapped_event["end"]) + "s [" \
                + mapped_event["name"] + "]"
        
        if data is not None:
            line = line + " " + str(data)
        
        if mapped_event["name"] == "LLM Generation":
            if token_idx < len(token_list):
                tokens = token_list[token_idx]
                line = line + "; " + str(tokens["input"]) + " input, " + str(tokens["output"]) + " output"
                token_idx = token_idx + 1
            else:
                line = line + " (no tokens)"

        print(line)


def print_patched_stats(added_files, deleted_files, added_lines, deleted_lines, updated_files):
    all_files = added_files + deleted_files + updated_files

    print("File Edits")
    print("Files changed:", len(all_files))
    print()

    for file in added_files:
        print("  +", file, "(new file)")

    for file in deleted_files:
        print("  -", file, "(deleted)")

    for file in updated_files:
        print("  ~", file)

    print()
    print("Lines added:  ", added_lines)
    print("Lines removed:", deleted_lines)
    print("Total edits:  ", added_lines + deleted_lines)


def patched_stats(patch_output):
    added_files = []
    added_lines = 0
    deleted_files = []
    deleted_lines = 0
    updated_files = []

    current_file = None

    for line in patch_output.splitlines():
        if line.startswith("diff --git"):
            current_file = line.split(" b/")[1]
        elif line.startswith("new file mode"):
            added_files.append(current_file)
        elif line.startswith("deleted file mode"):
            deleted_files.append(current_file)
        elif line.startswith("*** Update File:"):
            updated_files.append(line.replace("*** Update File: ", ""))
        elif line.startswith("*** Add File:"):
            added_files.append(line.replace("*** Add File: ", ""))
        elif line.startswith("*** Delete File:"):
            deleted_files.append(line.replace("*** Delete File: ", ""))
        elif line.startswith("+") and not line.startswith("+++"):
            added_lines += 1
        elif line.startswith("-") and not line.startswith("---"):
            deleted_lines += 1

    if "diff --git" in patch_output:
        for line in patch_output.splitlines():
            if line.startswith("diff --git"):
                file_name = line.split(" b/")[1]
                if file_name not in added_files and file_name not in deleted_files:
                    updated_files.append(file_name)

    print_patched_stats(added_files, deleted_files, added_lines, deleted_lines, updated_files)
