from run import run_continue


run_number = 0

def pick_model_alternating():
    global run_number
    models = ["gpt-4o", "gpt-4o-mini", "gpt-5.2"]
    model = models[run_number % len(models)]
    run_number += 1
    return model

def run_alternating_method(test_case):
    issue = test_case["problem_statement"]
    repo = test_case["repo"]

    analyze_prompt = ( "You are working on repository " + repo + ". " "Analyze this bug and list likely root cause and files to edit. "
                        "Do not provide a patch yet. "
                        "Issue: " + issue)
    model = pick_model_alternating()
    print("Alternating step 1 model:", model)
    t1, out1, code1, cpu1, rss1 = run_continue(analyze_prompt, model=model)
    if code1 != 0:
        return t1, out1, code1, cpu1, rss1

    plan_prompt = ("Repository: " + repo + ". " "Using this analysis, produce a precise fix plan only. "
                    "Analysis: " + out1 + " "
                    "Issue: " + issue
    )
    model = pick_model_alternating()
    print("Alternating step 2 model:", model)
    t2, out2, code2, cpu2, rss2 = run_continue(plan_prompt, model=model)
    if code2 != 0:
        return t1 + t2, out2, code2, max(cpu1, cpu2), max(rss1, rss2)

    patch_prompt = ("Fix this bug in repository " + repo + ". "
                    "Issue: " + issue + " "
                    "Plan: " + out2 + " "
                    "Return ONLY a valid git patch.")
    model = pick_model_alternating()
    print("Alternating step 3 model:", model)
    t3, out3, code3, cpu3, rss3 = run_continue(patch_prompt, model=model)

    total_time = t1 + t2 + t3
    peak_cpu = max(cpu1, cpu2, cpu3)
    peak_rss = max(rss1, rss2, rss3)
    return total_time, out3, code3, peak_cpu, peak_rss


def score_task_complexity(test_case):
    score = 0
    if len(test_case["problem_statement"]) > 1000:
        score += 1
    if len(test_case["FAIL_TO_PASS"]) > 3:
        score += 1
    return score


def pick_model_complexity(test_case):
    score = score_task_complexity(test_case)
    model = "gpt-5.2" if score >= 2 else "gpt-4o-mini"
    print("Complexity score:", score, "-> using", model)
    return model


def run_complexity_method(test_case, prompt):
    model = pick_model_complexity(test_case)
    return run_continue(prompt, model=model)

