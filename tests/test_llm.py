import json

import httpx
import pytest

from shortstock import db
from shortstock.llm import PROVIDERS, LLMError, OpenAICompatibleLLM, get_llm, parse_json


def make_llm(handler):
    return OpenAICompatibleLLM(
        PROVIDERS["openrouter"], "key", "some/model", transport=httpx.MockTransport(handler)
    )


def reply(content, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


def test_sends_structured_output_request():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return reply('{"clips": []}')

    assert make_llm(handler).complete_json("sys", "user", {"type": "object"}, "x") == {"clips": []}
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer key"
    assert seen["body"]["model"] == "some/model"
    assert seen["body"]["response_format"]["json_schema"]["strict"] is True


def test_falls_back_when_model_rejects_response_format():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, text="response_format not supported")
        return reply('```json\n{"ok": true}\n```')

    assert make_llm(handler).complete_json("s", "u", {}, "x") == {"ok": True}
    assert calls == [True, False]


def test_errors_are_raised():
    with pytest.raises(LLMError, match="401"):
        make_llm(lambda r: httpx.Response(401, text="bad key")).complete_json("s", "u", {}, "x")


def test_parse_json_handles_prose():
    assert parse_json('Here you go: {"a": 1} thanks') == {"a": 1}
    with pytest.raises(LLMError):
        parse_json("no json here")


def test_get_llm_requires_key_and_uses_settings():
    with pytest.raises(LLMError, match="No API key"):
        get_llm()
    db.set_setting("openrouter_api_key", "sk-test")
    db.set_setting("llm_model", "x/y")
    assert get_llm().model == "x/y"
    assert get_llm("override/model").model == "override/model"
