import subprocess
import time
import os
from pathlib import Path
import threading
import tempfile
from typing import Optional
from timeline_processor import capture_cpu_usage


PROJECT_ROOT = Path(__file__).resolve().parent
CONTINUE_DIR = PROJECT_ROOT / "continue"
BASE_CONFIG_PATH = CONTINUE_DIR / ".continue-debug" / "config.yaml"
CN_LOG_PATH = CONTINUE_DIR / ".continue" / "logs" / "cn.log"
CONTINUE_GLOBAL_DIR = CONTINUE_DIR / ".continue"
DEFAULT_TIMEOUT_SEC = int(os.getenv("CONTINUE_TIMEOUT_SEC", "900"))
DEFAULT_MAX_RETRIES = int(os.getenv("CONTINUE_MAX_RETRIES", "2"))
DEFAULT_RETRY_BACKOFF_SEC = float(os.getenv("CONTINUE_RETRY_BACKOFF_SEC", "2"))
DEFAULT_PROXY_API_BASE = os.getenv("CONTINUE_OPENAI_API_BASE")
DEFAULT_PROXY_API_KEY = os.getenv("CONTINUE_OPENAI_API_KEY")


def normalize_model(model: str):
    alias_map = {"gpt": ("openai", "gpt-4o-mini")}
    if model in alias_map:
        return alias_map[model]

    if "/" in model:
        provider, model_name = model.split("/", 1)
        return provider, model_name

    return "openai", model


def build_config_for_model(model: Optional[str]):
    base_text = BASE_CONFIG_PATH.read_text(encoding="utf-8")
    if not model:
        return str(BASE_CONFIG_PATH), None

    provider, model_name = normalize_model(model)
    proxy_api_base = DEFAULT_PROXY_API_BASE
    proxy_api_key = DEFAULT_PROXY_API_KEY
    lines = base_text.splitlines()
    provider_set = False
    model_set = False
    api_base_set = False
    api_key_set = False
    inserted_api_base = False
    rewritten = []

    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]

        if not provider_set and stripped.startswith("provider:"):
            rewritten.append(f"{indent}provider: {provider}")
            provider_set = True
            continue
        if not model_set and stripped.startswith("model:"):
            rewritten.append(f"{indent}model: {model_name}")
            model_set = True
            if proxy_api_base:
                rewritten.append(f"{indent}apiBase: {proxy_api_base}")
                inserted_api_base = True
            continue

        if proxy_api_base and not api_base_set and stripped.startswith("apiBase:"):
            rewritten.append(f"{indent}apiBase: {proxy_api_base}")
            api_base_set = True
            continue

        if proxy_api_key and not api_key_set and stripped.startswith("apiKey:"):
            rewritten.append(f"{indent}apiKey: {proxy_api_key}")
            api_key_set = True
            continue

        rewritten.append(line)

    if proxy_api_base and not api_base_set and not inserted_api_base:
        for i, line in enumerate(rewritten):
            if line.lstrip().startswith("model:"):
                indent = line[: len(line) - len(line.lstrip())]
                rewritten.insert(i + 1, f"{indent}apiBase: {proxy_api_base}")
                break

    cfg = "\n".join(rewritten) + ("\n" if base_text.endswith("\n") else "")

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(cfg)
    tmp.close()
    return tmp.name, model_name


def run_continue(prompt, model=None, timeout_sec=None, max_retries=None):
    timeout_sec = DEFAULT_TIMEOUT_SEC if timeout_sec is None else timeout_sec
    max_retries = DEFAULT_MAX_RETRIES if max_retries is None else max_retries
    log_file = CN_LOG_PATH

    config_path, resolved_model = build_config_for_model(model)
    last_error_output = ""
    try:
        for attempt in range(max_retries + 1):
            if log_file.exists():
                log_file.unlink()

            start = time.time()
            cmd = ["node", "continue/extensions/cli/dist/cn.js", "--config", config_path, "--print", "--silent", "--verbose", prompt]

            proc = subprocess.Popen(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "CONTINUE_GLOBAL_DIR": str(CONTINUE_GLOBAL_DIR)},
            )

            stats = {"peak_cpu": 0.0, "peak_rss": 0.0}

            def monitor():
                peak_cpu, peak_rss = capture_cpu_usage(proc.pid)
                stats["peak_cpu"] = peak_cpu
                stats["peak_rss"] = peak_rss

            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()

            timed_out = False
            try:
                stdout, stderr = proc.communicate(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                stdout, stderr = proc.communicate()

            monitor_thread.join()

            end = time.time()
            total_time = end - start
            output = stdout.strip() if stdout else stderr.strip()
            if resolved_model:
                output = f"[model={resolved_model}] {output}"

            if timed_out:
                timeout_output = f"{output}\n[error] Continue timed out after {timeout_sec}s".strip()
                return total_time, timeout_output, 124, stats["peak_cpu"], stats["peak_rss"]

            last_error_output = output
            transient_connection_error = "Connection error." in output
            if proc.returncode == 0 or not transient_connection_error or attempt == max_retries:
                return total_time, output, proc.returncode, stats["peak_cpu"], stats["peak_rss"]

            time.sleep(DEFAULT_RETRY_BACKOFF_SEC)
    finally:
        if config_path != str(BASE_CONFIG_PATH):
            Path(config_path).unlink(missing_ok=True)

    return 0.0, last_error_output, 1, 0.0, 0.0
