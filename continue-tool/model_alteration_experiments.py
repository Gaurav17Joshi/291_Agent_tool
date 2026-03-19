from pathlib import Path
import ast
import time
from run import run_continue

PROJECT_ROOT = Path(__file__).resolve().parent
CN_LOG_PATH = PROJECT_ROOT / "continue" / ".continue" / "logs" / "cn.log"

REFERENCE_ROWS = {
"baseline": {"method": "0 (Baseline)", "time_s": 132, "gpt5_tokens": 82000, "gpt5mini_tokens": 0, "gpt5_cost": 0.492, "gpt5mini_cost": 0.000, "total_cost": 0.492, "total_llm_calls": 21},
"alternating": {"method": "1 (Alternating)", "time_s": 174, "gpt5_tokens": 90000, "gpt5mini_tokens": 59000, "gpt5_cost": 0.540, "gpt5mini_cost": 0.071, "total_cost": 0.611, "total_llm_calls": 29},
"router": {"method": "2 (GPT-5 Router)", "time_s": 118, "gpt5_tokens": 52000, "gpt5mini_tokens": 41000, "gpt5_cost": 0.312, "gpt5mini_cost": 0.049, "total_cost": 0.361, "total_llm_calls": 25},
"confidence": {"method": "3 (Confidence-Based)", "time_s": 146, "gpt5_tokens": 78000, "gpt5mini_tokens": 27000, "gpt5_cost": 0.468, "gpt5mini_cost": 0.032, "total_cost": 0.500, "total_llm_calls": 24},
"phase": {"method": "4 (Phase-Based)", "time_s": 153, "gpt5_tokens": 83000, "gpt5mini_tokens": 31000, "gpt5_cost": 0.498, "gpt5mini_cost": 0.037, "total_cost": 0.535, "total_llm_calls": 25},
"tool_complexity": {"method": "5 (Tool-Complexity)", "time_s": 141, "gpt5_tokens": 76000, "gpt5mini_tokens": 35000, "gpt5_cost": 0.456, "gpt5mini_cost": 0.042, "total_cost": 0.498, "total_llm_calls": 23}
}


def parse_stream_complete_metrics(log_path: Path = CN_LOG_PATH):
    llm_calls = 0
    input_tokens = 0
    output_tokens = 0
    total_cost = 0.0
    if not log_path.exists():
        return llm_calls, input_tokens, output_tokens, total_cost
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "Stream complete" not in line:
            continue
        payload_start = line.find("{")
        if payload_start == -1:
            continue
        payload = line[payload_start:]
        try:
            data = ast.literal_eval(payload)
        except Exception:
            continue
        llm_calls += 1
        input_tokens += int(data.get("inputTokens") or 0)
        output_tokens += int(data.get("outputTokens") or 0)
        total_cost += float(data.get("cost") or 0.0)
    return llm_calls, input_tokens, output_tokens, total_cost


def parse_usage_chunk_metrics(log_path: Path = CN_LOG_PATH):
    llm_calls = 0
    input_tokens = 0
    output_tokens = 0
    if not log_path.exists():
        return llm_calls, input_tokens, output_tokens
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if '"usage"' not in line or '"prompt_tokens"' not in line or '"completion_tokens"' not in line:
            continue
        payload_start = line.find("{")
        if payload_start == -1:
            continue
        payload = line[payload_start:]
        try:
            data = ast.literal_eval(payload)
        except Exception:
            continue
        chunk = data.get("chunk") or {}
        usage = chunk.get("usage") or {}
        inp = int(usage.get("prompt_tokens") or 0)
        out = int(usage.get("completion_tokens") or 0)
        if inp == 0 and out == 0:
            continue
        llm_calls += 1
        input_tokens += inp
        output_tokens += out
    return llm_calls, input_tokens, output_tokens


def bucket_for_model(model: str):
    return "gpt5mini" if "mini" in model.lower() else "gpt5"


def uncertainty_signal(text: str):
    low = text.lower()
    keys = ["uncertain", "not sure", "might be", "possibly", "can't determine", "cannot determine", "need more context"]
    return any(k in low for k in keys)


def extract_router_decision(text: str):
    low = text.lower()
    for line in low.splitlines():
        if "next_model" in line and "gpt-5-mini" in line:
            return "gpt-5-mini"
        if "next_model" in line and "gpt-5" in line:
            return "gpt-5"
    if "gpt-5-mini" in low:
        return "gpt-5-mini"
    if "gpt-5" in low:
        return "gpt-5"
    return None


def run_step(prompt: str, model: str, timeout_sec=None):
    t, out, code, cpu, rss = run_continue(prompt, model=model, timeout_sec=timeout_sec)
    llm_calls, inp, out_tok, cost = 0, 0, 0, 0.0

    for _ in range(4):
        llm_calls, inp, out_tok, cost = parse_stream_complete_metrics()
        if llm_calls > 0:
            break
        time.sleep(0.25)

    if llm_calls == 0:
        llm_calls, inp, out_tok = parse_usage_chunk_metrics()
        cost = 0.0

    return {"time": t, "output": out, "code": code, "cpu": cpu, "rss": rss, "model": model, "llm_calls": llm_calls, "input_tokens": inp, "output_tokens": out_tok, "cost": cost}


def build_prompts(test_case):
    issue = test_case["problem_statement"]
    repo = test_case["repo"]
    p1 = f"Repository: {repo}. Analyze this issue and identify likely root cause and target files. Issue: {issue}"
    p2 = f"Repository: {repo}. Based on analysis, create a precise fix plan. Issue: {issue}"
    p3 = f"Repository: {repo}. Implement the fix and return only a valid git patch. Issue: {issue}"
    p_router = f"Repository: {repo}. Analyze issue and decide next model. Respond with exactly one line: NEXT_MODEL: gpt-5 or NEXT_MODEL: gpt-5-mini, then a short rationale. Issue: {issue}"
    p_light_summary = f"Repository: {repo}. Based only on this issue text, provide 5 concise bullets for likely root cause and files to inspect. Do not call tools. Issue: {issue}"
    p_light_tests = f"Repository: {repo}. Based only on this issue text, provide 5 concise bullets for tests to run and expected behavior. Do not call tools. Issue: {issue}"
    return p1, p2, p3, p_router, p_light_summary, p_light_tests


def run_model_alteration_method(method: str, test_case):
    method = method.strip().lower()
    if method not in REFERENCE_ROWS:
        raise ValueError(f"Unknown method '{method}'. Expected one of {list(REFERENCE_ROWS.keys())}")

    p1, p2, p3, p_router, p_light_summary, p_light_tests = build_prompts(test_case)
    steps = []

    if method == "baseline":
        steps.append((p3, "gpt-5"))

    elif method == "alternating":
        steps.extend([(p1, "gpt-5"), (p2, "gpt-5-mini"), (p3, "gpt-5"), ("Review and refine the patch quality briefly.", "gpt-5-mini")])

    elif method == "router":
        s1 = run_step(p_router, "gpt-5")
        if s1["code"] != 0:
            return pack_result(method, [s1])
        chosen = extract_router_decision(s1["output"]) or "gpt-5-mini"
        s2 = run_step(p3, chosen)
        return pack_result(method, [s1, s2])

    elif method == "confidence":
        s1 = run_step(p1, "gpt-5-mini")
        if s1["code"] != 0:
            return pack_result(method, [s1])
        next_model = "gpt-5" if uncertainty_signal(s1["output"]) else "gpt-5-mini"
        s2 = run_step(p3, next_model)
        return pack_result(method, [s1, s2])

    elif method == "phase":
        steps.extend([(p_light_summary, "gpt-5", 120), (p2, "gpt-5-mini", 180), (p_light_tests, "gpt-5", 120), (p3, "gpt-5-mini", 300)])

    elif method == "tool_complexity":
        fail_count = len(test_case.get("FAIL_TO_PASS", []))
        planning_model = "gpt-5" if fail_count >= 3 else "gpt-5-mini"
        patch_model = "gpt-5" if fail_count >= 5 else "gpt-5-mini"
        steps.extend([(p_light_summary, planning_model, 120), (p2, "gpt-5-mini", 180), (p3, patch_model, 300)])

    results = []
    for step in steps:
        if len(step) == 3:
            prompt, model, timeout = step
        else:
            prompt, model = step
            timeout = None
        s = run_step(prompt, model, timeout_sec=timeout)
        results.append(s)
        if s["code"] != 0 and method not in {"phase", "tool_complexity"}:
            break
    return pack_result(method, results)


def pack_result(method: str, step_results):
    total_time = sum(s["time"] for s in step_results)
    peak_cpu = max((s["cpu"] for s in step_results), default=0.0)
    peak_rss = max((s["rss"] for s in step_results), default=0.0)
    return_code = step_results[-1]["code"] if step_results else 1
    output = step_results[-1]["output"] if step_results else ""

    gpt5_tokens = 0
    gpt5mini_tokens = 0
    gpt5_cost = 0.0
    gpt5mini_cost = 0.0
    total_llm_calls = 0

    for s in step_results:
        bucket = bucket_for_model(s["model"])
        total_llm_calls += s["llm_calls"]
        step_tokens = s["input_tokens"] + s["output_tokens"]
        if bucket == "gpt5mini":
            gpt5mini_tokens += step_tokens
            gpt5mini_cost += s["cost"]
        else:
            gpt5_tokens += step_tokens
            gpt5_cost += s["cost"]

    total_cost = gpt5_cost + gpt5mini_cost

    return {"method": method, "total_time_s": total_time, "output": output, "return_code": return_code, "peak_cpu": peak_cpu, "peak_rss": peak_rss, "gpt5_tokens": gpt5_tokens, "gpt5mini_tokens": gpt5mini_tokens, "gpt5_cost": round(gpt5_cost, 6), "gpt5mini_cost": round(gpt5mini_cost, 6), "total_cost": round(total_cost, 6), "total_llm_calls": total_llm_calls}


def print_reference_table():
    print("Reference (Model Alteration Results)")
    print("-" * 84)
    print("Method            Time   GPT-5 tok  GPT-5-mini tok  GPT-5$   mini$   Total$  Calls")
    for key in ["baseline", "alternating", "router", "confidence", "phase", "tool_complexity"]:
        r = REFERENCE_ROWS[key]
        print(f"{r['method']:18} {r['time_s']:>4}   {r['gpt5_tokens']:>8}   {r['gpt5mini_tokens']:>13}   {r['gpt5_cost']:>6.3f}  {r['gpt5mini_cost']:>6.3f}  {r['total_cost']:>6.3f}   {r['total_llm_calls']:>3}")
    print("-" * 84)


def print_observed_vs_ref(method: str, observed):
    ref = REFERENCE_ROWS[method]
    print(f"Observed ({ref['method']})")
    print(f"Time (s): {observed['total_time_s']:.2f}   | Reference: {ref['time_s']}")
    print(f"GPT-5 tokens: {observed['gpt5_tokens']}   | Reference: {ref['gpt5_tokens']}")
    print(f"GPT-5-mini tokens: {observed['gpt5mini_tokens']}   | Reference: {ref['gpt5mini_tokens']}")
    print(f"GPT-5 cost: {observed['gpt5_cost']:.6f}   | Reference: {ref['gpt5_cost']:.3f}")
    print(f"GPT-5-mini cost: {observed['gpt5mini_cost']:.6f}   | Reference: {ref['gpt5mini_cost']:.3f}")
    print(f"Total cost: {observed['total_cost']:.6f}   | Reference: {ref['total_cost']:.3f}")
    print(f"Total LLM calls: {observed['total_llm_calls']}   | Reference: {ref['total_llm_calls']}")
