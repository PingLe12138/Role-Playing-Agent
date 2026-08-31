from types import SimpleNamespace

import anthropic
import httpx
import pytest

from AnthropicLLMClient import AnthropicLLMClient


def _api_error(message="boom") -> anthropic.APIError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIError(message, request=request, body=None)


def _response(texts=("hi",), *, stop_reason="end_turn", with_content=True):
    content = []
    if with_content:
        content = [SimpleNamespace(type="text", text=t) for t in texts]
    return SimpleNamespace(content=content, stop_reason=stop_reason)


class _FakeMessages:
    """按顺序弹出预设结果（异常对象则抛出）并记录调用参数。"""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _make_client(monkeypatch, *results) -> AnthropicLLMClient:
    # 免除真实退避等待
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    client = AnthropicLLMClient(api_key="sk-test")
    messages = _FakeMessages(*results)
    client.client = SimpleNamespace(messages=SimpleNamespace(create=messages.create))
    client._messages = messages  # 供断言调用次数与参数
    return client


class TestAnthropicChat:
    def test_normal_response_returns_text(self, monkeypatch):
        client = _make_client(monkeypatch, _response(texts=("你好",)))
        assert client.chat([{"role": "user", "content": "hi"}]) == "你好"

    def test_multiple_text_blocks_joined(self, monkeypatch):
        client = _make_client(monkeypatch, _response(texts=("第一段", "第二段")))
        assert client.chat([{"role": "user", "content": "hi"}]) == "第一段\n第二段"

    def test_system_messages_extracted_to_top_level(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.chat(
            [
                {"role": "system", "content": "规则一"},
                {"role": "system", "content": "规则二"},
                {"role": "user", "content": "hi"},
            ]
        )
        params = client._messages.calls[0]
        assert params["system"] == "规则一\n\n规则二"
        # system 消息不应残留在 messages 数组中
        assert all(m["role"] != "system" for m in params["messages"])
        assert params["messages"][0]["content"] == "hi"

    def test_no_system_message_omits_system_key(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.chat([{"role": "user", "content": "hi"}])
        assert "system" not in client._messages.calls[0]

    def test_thinking_enabled_omits_temperature(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="enabled")
        params = client._messages.calls[0]
        assert "temperature" not in params
        assert params["thinking"]["type"] == "enabled"
        assert 1024 <= params["thinking"]["budget_tokens"] <= 32000

    def test_thinking_enabled_via_constructor_default(self, monkeypatch):
        client = AnthropicLLMClient(api_key="sk-test", isEnableThinking="enabled")
        messages = _FakeMessages(_response())
        client.client = SimpleNamespace(messages=SimpleNamespace(create=messages.create))
        client._messages = messages
        client.chat([{"role": "user", "content": "hi"}])
        assert "temperature" not in messages.calls[0]
        assert messages.calls[0]["thinking"]["type"] == "enabled"

    def test_thinking_disabled_passes_temperature(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="disabled", temperature=0.5)
        params = client._messages.calls[0]
        assert "thinking" not in params
        assert params["temperature"] == 0.5

    def test_response_format_ignored(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.chat([{"role": "user", "content": "hi"}], response_format={"type": "json_object"})
        assert "response_format" not in client._messages.calls[0]

    def test_max_tokens_defaulted_and_required(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.chat([{"role": "user", "content": "hi"}])
        assert client._messages.calls[0]["max_tokens"] == 2048


class TestAnthropicEmptyAndErrors:
    def test_empty_content_retries_then_raises(self, monkeypatch):
        results = [_response(with_content=False)] * (AnthropicLLMClient.EMPTY_RESPONSE_RETRIES + 1)
        client = _make_client(monkeypatch, *results)
        with pytest.raises(RuntimeError, match="空内容"):
            client.chat([{"role": "user", "content": "hi"}])
        assert len(client._messages.calls) == AnthropicLLMClient.EMPTY_RESPONSE_RETRIES + 1

    def test_empty_content_retries_then_succeeds(self, monkeypatch):
        client = _make_client(monkeypatch, _response(with_content=False), _response(texts=("恢复",)))
        assert client.chat([{"role": "user", "content": "hi"}]) == "恢复"
        assert len(client._messages.calls) == 2

    def test_non_text_blocks_are_ignored(self, monkeypatch):
        # thinking 块（type="thinking"）不应作为可见内容返回
        content = [SimpleNamespace(type="thinking", thinking="内部推理"), SimpleNamespace(type="text", text="可见文本")]
        client = _make_client(monkeypatch, SimpleNamespace(content=content, stop_reason="end_turn"))
        assert client.chat([{"role": "user", "content": "hi"}]) == "可见文本"

    def test_api_error_wrapped_as_runtime_error(self, monkeypatch):
        client = _make_client(monkeypatch, _api_error("boom"))
        with pytest.raises(RuntimeError, match="LLM API 请求失败"):
            client.chat([{"role": "user", "content": "hi"}])

    def test_exhausted_retries_raise_runtime_error(self, monkeypatch):
        results = [_response(with_content=False)] * (AnthropicLLMClient.EMPTY_RESPONSE_RETRIES + 1)
        client = _make_client(monkeypatch, *results)
        with pytest.raises(RuntimeError, match="连续返回空响应"):
            client.chat([{"role": "user", "content": "hi"}])
        assert len(client._messages.calls) == AnthropicLLMClient.EMPTY_RESPONSE_RETRIES + 1


class TestAnthropicBaseUrl:
    def test_trailing_v1_is_stripped(self):
        client = AnthropicLLMClient(api_key="sk-test", base_url="https://api.example.com/v1")
        assert "/v1" not in str(client.client.base_url)

    def test_missing_base_url_uses_sdk_default(self):
        client = AnthropicLLMClient(api_key="sk-test")
        assert str(client.client.base_url).startswith("https://api.anthropic.com")


class TestBudgetTokens:
    def test_half_of_max_tokens(self):
        assert AnthropicLLMClient._budget_tokens(8192) == 4096

    def test_floored_at_1024(self):
        assert AnthropicLLMClient._budget_tokens(2048) == 1024

    def test_capped_at_32000(self):
        assert AnthropicLLMClient._budget_tokens(100000) == 32000

    def test_small_max_tokens_kept_below_max(self):
        assert AnthropicLLMClient._budget_tokens(1024) < 1024
        assert AnthropicLLMClient._budget_tokens(1024) >= 1


class TestAnthropicNewParams:
    def test_reasoning_effort_accepted_but_ignored(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="enabled", reasoning_effort="high")
        params = client._messages.calls[0]
        assert "reasoning_effort" not in params
        assert params["thinking"]["type"] == "enabled"

    def test_max_context_trims_messages(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        long = "字" * 4000
        client.chat([{"role": "user", "content": long}], max_context_tokens=100)
        params = client._messages.calls[0]
        assert len(params["messages"][0]["content"]) < 4000

    def test_zero_ctx_falls_back_to_global(self, monkeypatch):
        client = _make_client(monkeypatch, _response())
        client.default_max_context_tokens = 100
        long = "字" * 4000
        client.chat([{"role": "user", "content": long}], max_context_tokens=0)
        assert len(client._messages.calls[0]["messages"][0]["content"]) < 4000
