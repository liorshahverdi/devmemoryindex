import json

import httpx

from core.llm_backend import OllamaBackend


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_ollama_chat_sends_latency_focused_options_and_short_timeout(monkeypatch):
    captured = {}

    def fake_post(endpoint, json, timeout):
        captured["endpoint"] = endpoint
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse({"message": {"content": "ok"}})

    monkeypatch.setattr(httpx, "post", fake_post)
    backend = OllamaBackend(model="qwen2.5-coder:3b", timeout=4, num_predict=64, keep_alive="10m")

    result = list(backend.chat([{"role": "user", "content": "Say ok"}], stream=False))

    assert result == ["ok"]
    assert captured["endpoint"].endswith("/api/chat")
    assert captured["timeout"] == 4
    assert captured["json"]["keep_alive"] == "10m"
    assert captured["json"]["options"]["num_predict"] == 64
    assert captured["json"]["options"]["temperature"] <= 0.2
