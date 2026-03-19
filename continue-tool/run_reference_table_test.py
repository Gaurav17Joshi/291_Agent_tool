import random
import sys
from datasets import load_dataset
from model_alteration_experiments import run_model_alteration_method


def pick_task(test_data, user_idx):
    if user_idx is not None:
        return user_idx
    return random.randint(0, len(test_data) - 1)


def fmt_int(n):
    return f"{int(n):,}"


def print_table(rows):
    print("| Method | Time (s) | GPT-5 tokens | GPT-5-mini tokens | GPT-5 cost (USD) | GPT-5-mini cost (USD) | Total cost (USD) | Total LLM calls |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        print(
            f"| {r['label']} | "
            f"{int(r['total_time_s'])} | "
            f"{fmt_int(r['gpt5_tokens'])} | "
            f"{fmt_int(r['gpt5mini_tokens'])} | "
            f"{r['gpt5_cost']:.3f} | "
            f"{r['gpt5mini_cost']:.3f} | "
            f"{r['total_cost']:.3f} | "
            f"{int(r['total_llm_calls'])} |"
        )


def main():
    dataset = load_dataset("princeton-nlp/SWE-bench_Lite")
    test_data = dataset["test"]

    idx = None
    if len(sys.argv) > 1:
        idx = int(sys.argv[1])
    idx = pick_task(test_data, idx)

    test_case = test_data[idx]
    print("task_index:", idx)
    print("instance_id:", test_case["instance_id"])
    print("repo:", test_case["repo"])
    print()

    methods = ["baseline", "alternating", "router", "confidence", "phase", "tool_complexity"]
    labels = {
        "baseline": "0 (Baseline)",
        "alternating": "1 (Alternating)",
        "router": "2 (GPT-5 Router)",
        "confidence": "3 (Confidence-Based)",
        "phase": "4 (Phase-Based)",
        "tool_complexity": "5 (Tool-Complexity)"
    }

    out_rows = []
    for m in methods:
        print("running:", m)
        res = run_model_alteration_method(m, test_case)
        out_rows.append(
            {
                "label": labels[m],
                "total_time_s": res["total_time_s"],
                "gpt5_tokens": res["gpt5_tokens"],
                "gpt5mini_tokens": res["gpt5mini_tokens"],
                "gpt5_cost": res["gpt5_cost"],
                "gpt5mini_cost": res["gpt5mini_cost"],
                "total_cost": res["total_cost"],
                "total_llm_calls": res["total_llm_calls"]
            }
        )

    print()
    print_table(out_rows)


if __name__ == "__main__":
    main()
