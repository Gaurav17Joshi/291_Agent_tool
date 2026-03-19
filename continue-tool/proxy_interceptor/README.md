# Simple Proxy Setup

This sends Continue API calls to LiteLLM first, then LiteLLM sends them to OpenAI.

## Step 1: install LiteLLM proxy

```bash
pip install "litellm[proxy]"
```

## Step 2: set keys

```bash
export OPENAI_API_KEY="sk-..."
export LITELLM_MASTER_KEY="my-proxy-key"
```

## Step 3: start proxy (terminal 1)

```bash
bash proxy_interceptor/start_proxy.sh
```

## Step 4: run orchestrator with proxy (terminal 2)

```bash
export LITELLM_MASTER_KEY="my-proxy-key"
bash proxy_interceptor/run_proxy.sh
```

With args:

```bash
bash proxy_interceptor/run_proxy.sh --method baseline --case-index 0
```

## Notes

- default proxy URL is `http://127.0.0.1:4000/v1`
- `run.py` reads:
  - `CONTINUE_OPENAI_API_BASE`
  - `CONTINUE_OPENAI_API_KEY`
- if those are set, Continue calls go through the proxy
