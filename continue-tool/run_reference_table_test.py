import argparse
import random
import subprocess
import time
from pathlib import Path
from datasets import load_dataset
from model_alteration_experiments import run_model_alteration_method

PROJECT_ROOT = Path(__file__).resolve().parent


def run_git(repo_path: Path, args, check=True):
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        cmd = "git " + " ".join(args)
        err = proc.stderr.strip() or proc.stdout.strip() or "unknown git error"
        raise RuntimeError(f"{cmd} failed in {repo_path}: {err}")
    return proc


def is_git_workspace(repo_path: Path):
    probe = run_git(repo_path, ["rev-parse", "--is-inside-work-tree"], check=False)
    return probe.returncode == 0


def find_stash_ref_by_marker(repo_path: Path, marker: str):
    out = run_git(repo_path, ["stash", "list"], check=True).stdout.splitlines()
    for line in out:
        if marker in line:
            return line.split(":", 1)[0]
    return None


def prepare_baseline_stash(repo_path: Path):
    if not is_git_workspace(repo_path):
        print(f"[warn] {repo_path} is not a git workspace; skip reset-between-methods.")
        return None

    status = run_git(repo_path, ["status", "--porcelain"], check=True).stdout.strip()
    if not status:
        return None

    marker = f"reference-table-baseline-{int(time.time())}"
    run_git(repo_path, ["stash", "push", "--include-untracked", "-m", marker], check=True)
    stash_ref = find_stash_ref_by_marker(repo_path, marker)
    if not stash_ref:
        raise RuntimeError("Could not find baseline stash after creation.")

    run_git(repo_path, ["stash", "apply", "--index", stash_ref], check=True)
    return stash_ref


def restore_workspace(repo_path: Path, baseline_stash_ref):
    run_git(repo_path, ["reset", "--hard", "HEAD"], check=True)
    run_git(repo_path, ["clean", "-fd"], check=True)
    if baseline_stash_ref:
        run_git(repo_path, ["stash", "apply", "--index", baseline_stash_ref], check=True)


def drop_stash_if_any(repo_path: Path, stash_ref):
    if not stash_ref:
        return
    run_git(repo_path, ["stash", "drop", stash_ref], check=False)


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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run all reference-table methods on one SWE-bench Lite task."
    )
    parser.add_argument(
        "task_index",
        nargs="?",
        type=int,
        help="Index in SWE-bench Lite test split. Random if omitted.",
    )
    parser.add_argument(
        "--workspace",
        default=str(PROJECT_ROOT),
        help="Git workspace to reset between methods (default: this repo root).",
    )
    parser.add_argument(
        "--no-reset-between-methods",
        action="store_true",
        help="Disable workspace reset between methods.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dataset = load_dataset("princeton-nlp/SWE-bench_Lite")
    test_data = dataset["test"]

    idx = pick_task(test_data, args.task_index)
    workspace = Path(args.workspace).resolve()
    reset_between_methods = not args.no_reset_between_methods

    test_case = test_data[idx]
    print("task_index:", idx)
    print("instance_id:", test_case["instance_id"])
    print("repo:", test_case["repo"])
    print("workspace:", workspace)
    print("reset_between_methods:", reset_between_methods)
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

    baseline_stash_ref = None
    if reset_between_methods:
        baseline_stash_ref = prepare_baseline_stash(workspace)

    out_rows = []
    try:
        for m in methods:
            print("running:", m)
            try:
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
            finally:
                if reset_between_methods and is_git_workspace(workspace):
                    restore_workspace(workspace, baseline_stash_ref)
    finally:
        if reset_between_methods and is_git_workspace(workspace):
            drop_stash_if_any(workspace, baseline_stash_ref)

    print()
    print_table(out_rows)


if __name__ == "__main__":
    main()
