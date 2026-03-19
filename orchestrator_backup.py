from datasets import load_dataset
from timeline_processor import *
from methods import run_alternating_method, run_complexity_method



method = "alternating"  

dataset = load_dataset("princeton-nlp/SWE-bench_Lite")
test_data = dataset["test"]
test_case = test_data[0]

prompt = f"Fix a bug in the repository: {test_case['repo']} Here is the issue: {test_case['problem_statement']} Please provide a git patch that fixes this issue by making your own test cases and making sure it passes for the appropriate task."

print("Running strategy:", method)

if method == "alternating":
    total_time, output, return_code, peak_cpu, peak_rss = run_alternating_method(test_case)

elif method == "complexity":
    total_time, output, return_code, peak_cpu, peak_rss = run_complexity_method(test_case, prompt)

print((total_time, output, return_code))
print("Peak CPU: ", peak_cpu, "%")
print("Peak RSS: ", peak_rss, " MB")
patched_stats(output)
process_cn()
