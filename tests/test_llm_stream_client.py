from types import SimpleNamespace

import httpx
import openai
import pytest

from LLMStreamClient import LLMStreamClient


def _api_error(message="boom") -> openai.APIError:
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    return openai.APIError(message, request, body=None)


def _response(content="hi", finish_reason="stop", *, with_choices=True, with_message=True):
    choices = []
    if with_choices:
        message = SimpleNamespace(content=content) if with_message else None
        choices = [SimpleNamespace(message=message, finish_reason=finish_reason)]
    return SimpleNamespace(choices=choices)


class _FakeCompletions:
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


def _make_client(monkeypatch, *results) -> LLMStreamClient:
    # 免除真实退避等待
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    client = LLMStreamClient(api_key="sk-test")
    completions = _FakeCompletions(*results)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client._completions = completions  # 供断言调用次数
    return client


class TestChatExtractContent:
    def test_normal_response_returns_content(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="你好"))
        assert client.chat([{"role": "user", "content": "hi"}]) == "你好"

    def test_none_content_with_choices_returns_via_retry_then_raises(self, monkeypatch):
        # content=None 且 finish_reason=length：重试耗尽后抛 RuntimeError 而非 TypeError
        client = _make_client(
            monkeypatch,
            _response(content=None, finish_reason="length"),
            _response(content=None, finish_reason="length"),
            _response(content=None, finish_reason="length"),
        )
        with pytest.raises(RuntimeError, match="空内容"):
            client.chat([{"role": "user", "content": "hi"}])
        assert len(client._completions.calls) == LLMStreamClient.EMPTY_RESPONSE_RETRIES + 1

    def test_empty_choices_retries_then_succeeds(self, monkeypatch):
        # 回归：choices=None 曾直接抛 TypeError('NoneType' object is not subscriptable)
        client = _make_client(monkeypatch, _response(with_choices=False), _response(content="恢复"))
        assert client.chat([{"role": "user", "content": "hi"}]) == "恢复"
        assert len(client._completions.calls) == 2

    def test_message_none_is_tolerated(self, monkeypatch):
        client = _make_client(monkeypatch, _response(with_message=False), _response(content="ok"))
        assert client.chat([{"role": "user", "content": "hi"}]) == "ok"

    def test_exhausted_retries_raise_runtime_error(self, monkeypatch):
        results = [_response(with_choices=False)] * (LLMStreamClient.EMPTY_RESPONSE_RETRIES + 1)
        client = _make_client(monkeypatch, *results)
        with pytest.raises(RuntimeError, match="连续返回空响应"):
            client.chat([{"role": "user", "content": "hi"}])
        assert len(client._completions.calls) == LLMStreamClient.EMPTY_RESPONSE_RETRIES + 1

    def test_api_error_wrapped_as_runtime_error(self, monkeypatch):
        client = _make_client(monkeypatch, _api_error("boom"))
        with pytest.raises(RuntimeError, match="LLM API 请求失败"):
            client.chat([{"role": "user", "content": "hi"}])

    def test_response_format_forwarded(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="{}"))
        client.chat([{"role": "user", "content": "hi"}], response_format={"type": "json_object"})
        assert client._completions.calls[0]["response_format"] == {"type": "json_object"}


class TestReasoningEffort:
    def test_sent_as_top_level_param_when_thinking_enabled(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="enabled", reasoning_effort="high")
        params = client._completions.calls[0]
        assert params["reasoning_effort"] == "high"
        assert params["extra_body"]["thinking"] == {"type": "enabled"}

    def test_not_sent_when_thinking_disabled(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="disabled", reasoning_effort="high")
        assert "reasoning_effort" not in client._completions.calls[0]

    def test_not_sent_when_effort_unset(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="enabled")
        assert "reasoning_effort" not in client._completions.calls[0]

    def test_constructor_default_applies_when_not_overridden(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        client.default_reasoning_effort = "max"
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="enabled")
        assert client._completions.calls[0]["reasoning_effort"] == "max"

    def test_chat_param_precedes_constructor_default(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        client.default_reasoning_effort = "max"
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="enabled", reasoning_effort="low")
        assert client._completions.calls[0]["reasoning_effort"] == "low"

    def test_empty_string_falls_back_to_global(self, monkeypatch):
        # 节点参数层空串 = 继承全局默认
        client = _make_client(monkeypatch, _response(content="ok"))
        client.default_reasoning_effort = "high"
        client.chat([{"role": "user", "content": "hi"}], isEnableThinking="enabled", reasoning_effort="")
        assert client._completions.calls[0]["reasoning_effort"] == "high"


class TestMaxContext:
    def test_trimming_applied_when_over_budget(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        long = "字" * 4000  # 估算约 2001 token
        client.chat([{"role": "user", "content": long}], isEnableThinking="disabled", max_context_tokens=100)
        sent = client._completions.calls[0]["messages"]
        assert len(sent[0]["content"]) < 4000

    def test_no_trimming_within_budget(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        msgs = [{"role": "user", "content": "hi"}]
        client.chat(msgs, max_context_tokens=10000)
        assert client._completions.calls[0]["messages"] == msgs

    def test_zero_ctx_falls_back_to_global(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        client.default_max_context_tokens = 100
        long = "字" * 4000
        client.chat([{"role": "user", "content": long}], isEnableThinking="disabled", max_context_tokens=0)
        sent = client._completions.calls[0]["messages"]
        assert len(sent[0]["content"]) < 4000

    def test_zero_global_means_no_trim(self, monkeypatch):
        client = _make_client(monkeypatch, _response(content="ok"))
        client.default_max_context_tokens = 0
        long = "字" * 4000
        client.chat([{"role": "user", "content": long}], isEnableThinking="disabled")
        sent = client._completions.calls[0]["messages"]
        assert sent[0]["content"] == long


class TestTrimMessages:
    def test_estimate_tokens_basic(self):
        from LLMStreamClient import estimate_tokens

        assert estimate_tokens("ab") == 2  # 2//2+1
        assert estimate_tokens("") == 1  # 0//2+1
        assert estimate_tokens(None) == 0
        assert estimate_tokens([{"text": "abcd"}]) == 3

    def test_last_message_always_kept(self):
        from LLMStreamClient import trim_messages

        big = "字" * 2000  # 估算 1001 token
        msgs = [
            {"role": "user", "content": big},
            {"role": "assistant", "content": big},
            {"role": "user", "content": "最新指令"},
        ]
        out = trim_messages(msgs, 1200)
        assert out[-1]["content"] == "最新指令"
        assert out[0]["role"] == "assistant"  # 大的整条被删除

    def test_single_message_truncated(self):
        from LLMStreamClient import trim_messages

        big = "字" * 4000
        out = trim_messages([{"role": "user", "content": big}], 100)
        assert len(out[0]["content"]) < 4000
        assert "截断" in out[0]["content"]

    def test_does_not_mutate_input(self):
        from LLMStreamClient import trim_messages

        big = "字" * 4000
        msgs = [{"role": "user", "content": big}]
        trim_messages(msgs, 100)
        assert len(msgs[0]["content"]) == 4000
