"""Model-agnostic LLM access.

Every provider speaks the OpenAI chat-completions protocol, so adding one is a new entry in
``PROVIDERS``. OpenRouter is the default and gives access to most hosted models with one key.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from shortstock.config import get_setting


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str) -> dict: ...


@dataclass(frozen=True, slots=True)
class Provider:
    name: str
    base_url: str
    key_setting: str
    headers: dict[str, str] = field(default_factory=dict)


PROVIDERS: dict[str, Provider] = {
    "openrouter": Provider(
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        key_setting="openrouter_api_key",
        headers={
            "HTTP-Referer": "https://github.com/T3-Venture-Labs-Limited/short-stock",
            "X-Title": "shortstock",
        },
    ),
}


class OpenAICompatibleLLM:
    def __init__(
        self,
        provider: Provider,
        api_key: str,
        model: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 300.0,
    ) -> None:
        if not api_key:
            raise LLMError(
                f"No API key for {provider.name}. Add it in Settings or run "
                f"`shortstock config set {provider.key_setting} <key>`."
            )
        self.provider = provider
        self.model = model
        self._client = httpx.Client(
            base_url=provider.base_url,
            headers={"Authorization": f"Bearer {api_key}", **provider.headers},
            timeout=timeout,
            transport=transport,
        )

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            },
        }
        response = self._post(body)
        if response.status_code == 400 and "response_format" in response.text:
            # Some models reject structured outputs; the prompt still asks for JSON.
            body.pop("response_format")
            response = self._post(body)
        if response.status_code >= 400:
            raise LLMError(f"{self.provider.name} error {response.status_code}: {response.text[:500]}")

        payload = response.json()
        if "error" in payload:
            raise LLMError(f"{self.provider.name} error: {payload['error']}")
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected response from {self.provider.name}: {payload}") from exc
        return parse_json(content)

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        delay = 2.0
        for attempt in range(4):
            try:
                response = self._client.post("/chat/completions", json=body)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 3:
                    raise
            else:
                if response.status_code not in {429, 500, 502, 503, 504} or attempt == 3:
                    return response
            time.sleep(delay)
            delay *= 2
        raise AssertionError("unreachable")


def parse_json(content: Any) -> dict:
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"Model did not return JSON: {text[:200]}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {exc}: {text[:200]}") from exc


def get_llm(model: str | None = None) -> LLM:
    provider_key = get_setting("llm_provider") or "openrouter"
    provider = PROVIDERS.get(provider_key)
    if provider is None:
        raise LLMError(f"Unknown LLM provider '{provider_key}'. Available: {', '.join(PROVIDERS)}")
    return OpenAICompatibleLLM(provider, get_setting(provider.key_setting), model or get_setting("llm_model"))


def list_models() -> list[dict[str, Any]]:
    """Models the current provider offers that support structured JSON output."""
    provider = PROVIDERS[get_setting("llm_provider") or "openrouter"]
    response = httpx.get(f"{provider.base_url}/models", timeout=30)
    response.raise_for_status()
    models = []
    for item in response.json().get("data", []):
        params = item.get("supported_parameters") or []
        if item["id"].endswith(":batch"):
            continue
        if params and "structured_outputs" not in params and "response_format" not in params:
            continue
        pricing = item.get("pricing") or {}
        models.append(
            {
                "id": item["id"],
                "name": item.get("name", item["id"]),
                "context_length": item.get("context_length"),
                "prompt_price_per_million": _per_million(pricing.get("prompt")),
                "completion_price_per_million": _per_million(pricing.get("completion")),
            }
        )
    return sorted(models, key=lambda m: m["id"])


def _per_million(value: Any) -> float | None:
    try:
        return round(float(value) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None
