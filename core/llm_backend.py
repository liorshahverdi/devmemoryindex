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

    def chat(self, messages: list[dict], stream: bool = True):
        """Send a structured chat request (system + user roles).

        Default implementation flattens messages into a single prompt and
        delegates to generate(). Subclasses should override this to use
        the backend's native chat endpoint so instruction-tuned models
        receive properly formatted role tokens.

        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        prompt = "\n\n".join(m["content"] for m in messages)
        yield from self.generate(prompt, stream=stream)


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

    def chat(self, messages: list[dict], stream: bool = True):
        """Use Ollama /api/chat so instruction-tuned models receive proper role tokens."""
        import httpx
        endpoint = f"{self.url}/api/chat"
        payload = {"model": self.model, "messages": messages, "stream": stream}

        if stream:
            with httpx.stream("POST", endpoint, json=payload, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        else:
            r = httpx.post(endpoint, json=payload, timeout=120)
            r.raise_for_status()
            yield r.json().get("message", {}).get("content", "")


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


def llm_summarize(raw_text: str, max_chars: int = 200, cfg: dict | None = None) -> str | None:
    """Generate a 1-sentence LLM summary of raw_text for ingest (T1-G).

    Uses the configured local LLM (Ollama by default). Returns None if the
    LLM is unavailable, allowing callers to fall back to heuristic truncation.

    Args:
        raw_text:  The full text to summarize.
        max_chars: Maximum length of the returned summary (default 200).
        cfg:       Optional LLM config dict; reads from config.toml if None.

    Returns:
        A one-sentence summary string, or None if the LLM call failed.
    """
    if not raw_text or not raw_text.strip():
        return None
    excerpt = raw_text[:1000]
    prompt = (
        "Summarize the following developer note in one concise sentence (max 200 characters). "
        "Output only the sentence, nothing else.\n\n"
        f"{excerpt}"
    )
    try:
        backend = get_backend(cfg)
        chunks = list(backend.generate(prompt, stream=False))
        result = "".join(chunks).strip()
        # Strip any wrapping quotes the model may add
        result = result.strip('"\'')
        return result[:max_chars] if result else None
    except Exception:
        return None


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
