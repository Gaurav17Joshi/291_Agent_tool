import sys
from datasets import load_dataset
from timeline_processor import *
from methods import run_alternating_method, run_complexity_method
from run import run_continue


mode = sys.argv[1].lower() if len(sys.argv) > 1 else "alternating"
task_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0

dataset = load_dataset("princeton-nlp/SWE-bench_Lite")
test_data = dataset["test"]
test_case = test_data[task_index]

prompt = f"Fix a bug in the repository: {test_case['repo']} Here is the issue: {test_case['problem_statement']} Please provide a git patch that fixes this issue by making your own test cases and making sure it passes for the appropriate task."

print("Running strategy:", mode)
print("Task index:", task_index)

if mode == "alternating":
    total_time, output, return_code, peak_cpu, peak_rss = run_alternating_method(test_case)

elif mode == "complexity":
    total_time, output, return_code, peak_cpu, peak_rss = run_complexity_method(test_case, prompt)

elif mode == "normal":
    total_time, output, return_code, peak_cpu, peak_rss = run_continue(prompt, model="gpt-5.2", timeout_sec=1800, max_retries=0)

else:
    print("Unknown mode:", mode)
    print("Usage: python orchestrator.py [alternating|complexity|normal] [task_index]")
    sys.exit(1)

print((total_time, output, return_code))
print("Peak CPU: ", peak_cpu, "%")
print("Peak RSS: ", peak_rss, " MB")
patched_stats(output)
process_cn()
