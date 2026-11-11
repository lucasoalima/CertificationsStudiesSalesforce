"""LLM providers behind one interface, with usage tracking and robust JSON parsing."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    failures: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    name: str
    usage: Usage

    def complete(self, prompt: str, system: str = "", max_tokens: int = 4000) -> str: ...


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in a model reply (tolerates ```json fences and chatter)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    pairs = sorted((("[", "]"), ("{", "}")), key=lambda p: (text.find(p[0]) == -1, text.find(p[0])))
    for open_, close in pairs:
        start = text.find(open_)
        end = text.rfind(close)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"model did not return valid JSON: {text[:200]!r}")


def complete_json(llm: LLM, prompt: str, system: str = "", retries: int = 2, max_tokens: int = 4000) -> Any:
    last: Exception | None = None
    for attempt in range(retries + 1):
        suffix = "" if attempt == 0 else "\n\nYour previous reply was not valid JSON. Reply with ONLY the JSON value."
        try:
            return extract_json(llm.complete(prompt + suffix, system=system, max_tokens=max_tokens))
        except LLMError as e:
            llm.usage.failures += 1
            last = e
    raise LLMError(str(last))


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, temperature: float = 0.4, timeout: float = 180):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self.api_key, self.model, self.temperature, self.timeout = api_key, model, temperature, timeout
        self.name = f"anthropic:{model}"
        self.usage = Usage()

    def complete(self, prompt: str, system: str = "", max_tokens: int = 4000) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        t0 = time.perf_counter()
        for attempt in range(4):
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json=body,
                timeout=self.timeout,
            )
            if r.status_code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            break
        if r.status_code >= 400:
            raise LLMError(f"Anthropic API {r.status_code}: {r.text[:300]}")
        j = r.json()
        self.usage.calls += 1
        self.usage.input_tokens += j.get("usage", {}).get("input_tokens", 0)
        self.usage.output_tokens += j.get("usage", {}).get("output_tokens", 0)
        self.usage.seconds += time.perf_counter() - t0
        return "".join(b.get("text", "") for b in j.get("content", []))


class OllamaLLM:
    def __init__(self, url: str, model: str, temperature: float = 0.4, timeout: float = 600):
        self.url, self.model, self.temperature, self.timeout = url.rstrip("/"), model, temperature, timeout
        self.name = f"ollama:{model}"
        self.usage = Usage()

    def complete(self, prompt: str, system: str = "", max_tokens: int = 4000) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        t0 = time.perf_counter()
        try:
            r = httpx.post(
                f"{self.url}/api/chat",
                json={"model": self.model, "messages": msgs, "stream": False, "options": {"temperature": self.temperature, "num_predict": max_tokens}},
                timeout=self.timeout,
            )
        except httpx.ConnectError as e:
            raise LLMError(f"cannot reach Ollama at {self.url} (is `ollama serve` running?)") from e
        if r.status_code >= 400:
            raise LLMError(f"Ollama {r.status_code}: {r.text[:300]}")
        j = r.json()
        self.usage.calls += 1
        self.usage.input_tokens += j.get("prompt_eval_count", 0)
        self.usage.output_tokens += j.get("eval_count", 0)
        self.usage.seconds += time.perf_counter() - t0
        return j.get("message", {}).get("content", "")


@dataclass
class FakeLLM:
    """Deterministic stand-in for tests and offline demos: `responder(prompt) -> str`."""

    responder: Callable[[str], str]
    name: str = "fake"
    usage: Usage = field(default_factory=Usage)
    prompts: list[str] = field(default_factory=list)

    def complete(self, prompt: str, system: str = "", max_tokens: int = 4000) -> str:
        self.prompts.append(prompt)
        self.usage.calls += 1
        return self.responder(prompt)


def make_llm(spec: str | None, settings) -> LLM:
    """`spec` like 'anthropic', 'anthropic:claude-...', 'ollama', 'ollama:qwen2.5:7b'."""
    spec = spec or settings.provider
    provider, _, model = spec.partition(":")
    if provider == "anthropic":
        return AnthropicLLM(settings.anthropic_api_key, model or settings.anthropic_model, settings.temperature)
    if provider == "ollama":
        return OllamaLLM(settings.ollama_url, model or settings.ollama_model, settings.temperature)
    raise ValueError(f"unknown provider '{provider}' (use anthropic | ollama)")
