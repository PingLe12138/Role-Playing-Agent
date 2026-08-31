import time
from typing import Dict, List, Optional

import anthropic
import httpx

from LLMStreamClient import trim_messages


class _EmptyLLMResponseError(Exception):
    """API 返回了缺失 text 块的异常载荷。

    Anthropic /v1/messages 正常响应中 content 数组至少含一个元素；
    若出现空数组或全为非 text 块，属于可重试的瞬时异常载荷。
    """


class AnthropicLLMClient:
    """Anthropic API 请求客户端（非流式，stream=False 硬编码；实时推送由 SSE 层负责）。

    构造与 chat() 签名与 LLMStreamClient 完全一致，供 config_loader 工厂按
    `protocol` 分支实例化；15 个图节点与 formatters.chat_json 只依赖
    `.chat(messages, ...) -> str` 公共接口，无需改动。
    """

    # 收到空响应时的自动重试次数与退避基数（秒），耗尽后抛 RuntimeError
    EMPTY_RESPONSE_RETRIES = 2
    RETRY_BACKOFF_SECONDS = 1.0

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
        default_temperature: float = 0.9,
        isEnableThinking: Optional[str] = "disabled",
        default_max_tokens: int = 2048,
        timeout: float = 600,
        default_reasoning_effort: Optional[str] = None,
        max_context_tokens: Optional[int] = None,
    ):
        """
        :param api_key: Anthropic API 密钥
        :param base_url: 自定义 API 地址。SDK 会在其后自动拼接 /v1/messages，
            因此这里应填主机地址（如 https://api.anthropic.com）；若误带尾部
            /v1 则防御性去除。空值使用 SDK 默认地址。
        :param timeout: 单次请求读超时秒数。连接阶段保持 5s，停机地址快速失败；
            SDK 级自动重试关闭，空响应重试由下方逻辑自行处理。
        """
        normalized_base_url: Optional[str] = None
        if base_url:
            normalized_base_url = base_url.rstrip("/").removesuffix("/v1") or None
        self.client = anthropic.Anthropic(
            api_key=api_key,
            base_url=normalized_base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            max_retries=0,
        )
        self.default_model = default_model
        self.default_temperature = default_temperature if default_temperature is not None else 0.9
        self.isEnableThinking = isEnableThinking if isEnableThinking is not None else "disabled"
        self.default_max_tokens = default_max_tokens if default_max_tokens is not None else 2048
        # reasoning_effort has no Anthropic equivalent top-level parameter; it is
        # accepted for signature parity with LLMStreamClient and ignored.
        # / Anthropic 无等价顶层参数，仅为与 LLMStreamClient 签名对齐而接受并忽略。
        self.default_reasoning_effort = default_reasoning_effort
        self.default_max_context_tokens = max_context_tokens

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        isEnableThinking: Optional[str] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        reasoning_effort: Optional[str] = None,
        max_context_tokens: Optional[int] = None,
    ) -> str:
        """向 /v1/messages 发起一次非流式请求并返回拼接后的文本。

        Anthropic 与 OpenAI 的差异在此收敛：
        - system 消息须为顶层参数，从 messages 中拆出并以 \\n\\n 拼接；
        - max_tokens 为必填参数；
        - 开启 extended thinking 时不得传 temperature，并需 budget_tokens；
        - response_format 无等价参数，忽略（chat_json 靠解析重试兜底）。
        """
        thinking_enabled = (isEnableThinking if isEnableThinking is not None else self.isEnableThinking) == "enabled"
        effective_model = model or self.default_model
        effective_max_tokens = max_tokens or self.default_max_tokens

        # reasoning_effort is accepted for signature parity but has no Anthropic
        # equivalent; max_context_tokens applies the same app-layer trimming.
        # / reasoning_effort 仅为签名对齐接受（Anthropic 无等价参数）；max_context_tokens
        #   与 OpenAI 客户端一致做应用层裁剪。0/空值 = 继承全局默认。
        per_call_ctx = max_context_tokens if isinstance(max_context_tokens, int) and max_context_tokens > 0 else None
        ctx_limit = per_call_ctx if per_call_ctx is not None else self.default_max_context_tokens
        if ctx_limit and ctx_limit > 0:
            messages = trim_messages(messages, ctx_limit)

        system_parts = [m["content"] for m in messages if m.get("role") == "system" and m.get("content")]
        system = "\n\n".join(system_parts) if system_parts else None
        msgs = [m for m in messages if m.get("role") != "system"]

        params: dict = {
            "model": effective_model,
            "max_tokens": effective_max_tokens,
            "messages": msgs,
            "stream": False,
        }
        if system:
            params["system"] = system
        if thinking_enabled:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self._budget_tokens(effective_max_tokens),
            }
            # Anthropic 约束：extended thinking 开启时禁止同时传 temperature
        else:
            params["temperature"] = temperature if temperature is not None else self.default_temperature

        last_error: Optional[_EmptyLLMResponseError] = None
        for attempt in range(self.EMPTY_RESPONSE_RETRIES + 1):
            try:
                response = self.client.messages.create(**params)
            except anthropic.APIError as e:
                raise RuntimeError(f"LLM API 请求失败: {e}") from e

            try:
                return self._extract_content(response, effective_model)
            except _EmptyLLMResponseError as e:
                last_error = e
                if attempt < self.EMPTY_RESPONSE_RETRIES:
                    wait = self.RETRY_BACKOFF_SECONDS * (attempt + 1)
                    print(
                        f"[AnthropicLLMClient] {e}，{wait:.0f}s 后自动重试"
                        f"（第 {attempt + 2}/{self.EMPTY_RESPONSE_RETRIES + 1} 次）",
                        flush=True,
                    )
                    time.sleep(wait)

        raise RuntimeError(f"LLM API 连续返回空响应: {last_error}") from last_error

    @staticmethod
    def _budget_tokens(max_tokens: int) -> int:
        """从 max_tokens 推导 thinking budget_tokens。

        Anthropic 要求 budget_tokens ≥ 1024 且 < max_tokens，上限 32000。
        取 max_tokens 的一半并夹在 [1024, 32000]；若仍不小于 max_tokens
        （max_tokens 过小时），压到 max_tokens - 1。
        """
        budget = max(max_tokens // 2, 1024)
        budget = min(budget, 32000)
        if budget >= max_tokens:
            budget = max(max_tokens - 1, 1)
        return budget

    @staticmethod
    def _extract_content(response, model: str) -> str:
        """拼接 content 数组中所有 type == "text" 块的文本。

        Anthropic 响应 content 为列表，元素类型包括 text / thinking / tool_use 等；
        仅 text 块是给用户的可见内容，thinking 块为推理过程，不返回。
        """
        blocks = getattr(response, "content", None) or []
        texts = [getattr(b, "text", "") for b in blocks if getattr(b, "type", "") == "text"]
        content = "\n".join(t for t in texts if t)
        if not content:
            stop_reason = getattr(response, "stop_reason", None) or "unknown"
            raise _EmptyLLMResponseError(f"模型 {model} 返回空内容（stop_reason={stop_reason}）")
        return content
