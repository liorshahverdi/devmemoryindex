"""
LLM backend abstraction for devmemory ask (Phase 7.1).

Supported backends:
  ollama   — local Ollama server (default: http://localhost:11434)
  llamacpp — llama.cpp server   (default: http://localhost:8080)

Config via config.toml [llm] section:
  backend = "ollama"
  model   = "mistral"
  url     = "http://localhost:11434"   # optional override
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod


class LLMBackend(ABC):
    @abstractmethod
    def generate(self, prompt: str, stream: bool = True):
        """Yield text chunks (stream=True) or yield a single full string (stream=False)."""
        ...


class OllamaBackend(LLMBackend):
    def __init__(self, model: str = "mistral", url: str = "http://localhost:11434"):
        self.model = model
        self.url = url.rstrip("/")

    def generate(self, prompt: str, stream: bool = True):
        import httpx
        endpoint = f"{self.url}/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": stream}

        if stream:
            with httpx.stream("POST", endpoint, json=payload, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if chunk.get("response"):
                            yield chunk["response"]
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        else:
            r = httpx.post(endpoint, json=payload, timeout=120)
            r.raise_for_status()
            yield r.json().get("response", "")


class LlamaCppBackend(LLMBackend):
    def __init__(self, url: str = "http://localhost:8080"):
        self.url = url.rstrip("/")

    def generate(self, prompt: str, stream: bool = True):
        import httpx
        endpoint = f"{self.url}/completion"
        payload = {"prompt": prompt, "stream": stream, "n_predict": 512}

        if stream:
            with httpx.stream("POST", endpoint, json=payload, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        chunk = json.loads(line[6:])
                        if chunk.get("content"):
                            yield chunk["content"]
                        if chunk.get("stop"):
                            break
                    except json.JSONDecodeError:
                        continue
        else:
            r = httpx.post(endpoint, json=payload, timeout=120)
            r.raise_for_status()
            yield r.json().get("content", "")


def get_backend(cfg: dict | None = None) -> LLMBackend:
    """Factory — build the right backend from a config dict or config.toml [llm]."""
    if cfg is None:
        from core.config import get_llm_config
        cfg = get_llm_config()

    backend_name = cfg.get("backend", "ollama").lower()

    if backend_name == "llamacpp":
        return LlamaCppBackend(url=cfg.get("url", "http://localhost:8080"))

    # default: ollama
    return OllamaBackend(
        model=cfg.get("model", "mistral"),
        url=cfg.get("url", "http://localhost:11434"),
    )
