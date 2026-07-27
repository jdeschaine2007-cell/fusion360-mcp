"""
Ollama auto-wiring for FusionMCP's plan_design.

Self-contained (stdlib urllib only — no extra dependency to install into the
CAD app's Python). On first plan_design call it:

  1. reads the Ollama base URL from OLLAMA_HOST (default http://localhost:11434),
  2. lists models and prefers QWEN3:8B (per Justin's local stack),
     falling back to the first available model,
  3. registers a callable that POSTs chat/completions and returns the
     model's raw text (the JSON plan).

If Ollama isn't running or has no models, auto-wiring silently no-ops and
plan_design keeps returning its "no LLM configured" error until you call
set_llm_callable() yourself. So this is strictly additive — it never breaks
a headless / CI run.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Callable, Optional, Tuple

_DEFAULT_HOST = "http://localhost:11434"
_PREFERRED = ("qwen3:8b", "qwen3", "qwen2.5:7b", "llama3:8b")


def _host() -> str:
    return (os.getenv("OLLAMA_HOST") or _DEFAULT_HOST).rstrip("/")


def _list_models(host: str) -> list:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
    except (urllib.error.URLError, OSError, ValueError):
        return []


def _pick_model(models: list) -> Optional[str]:
    if not models:
        return None
    low = [m.lower() for m in models]
    for pref in _PREFERRED:
        for m, ml in zip(models, low):
            if ml.startswith(pref) or pref in ml:
                return m
    return models[0]


def _chat(host: str, model: str, system: str, prompt: str) -> str:
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "format": "json",  # nudge the model toward raw JSON
    }
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("response", "")


def get_callable() -> Tuple[Optional[Callable[[str, str], str]], Optional[str]]:
    """Return (callable, model_name) or (None, None) if Ollama unavailable."""
    host = _host()
    models = _list_models(host)
    model = _pick_model(models)
    if not model:
        return None, None

    def _call(prompt: str, system: str) -> str:
        return _chat(host, model, system, prompt)

    return _call, model
