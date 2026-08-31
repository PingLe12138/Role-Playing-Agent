import time
from typing import Dict, List, Optional

import httpx
import openai

# 裁剪追加在内容尾部的截断标记（计入估算 token）
TRUNCATION_MARKER = "\n...[内容已按最大上下文截断]...\n"


def estimate_tokens(content) -> int:
    """Estimate the token count of a message content without a tokenizer.

    Conservative heuristic: Chinese text is roughly 1 token per character,
    English roughly 1 token per 4 chars; `len//2+1` is a safe middle ground
    for the mixed zh/en prompts used by this project.  Supports str and
    OpenAI-style list content (multimodal parts).
    / 无分词器时的消息内容 token 估算。中文约 1 字符 1 token、英文约 4 字符
      1 token，取 len//2+1 作为本项目中英混合提示词的保守折中。支持 str
      与 OpenAI 风格 list content（多模态 part）。
    """
    if isinstance(content, str):
        return len(content) // 2 + 1
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, str):
                total += len(part) // 2 + 1
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    total += len(text) // 2 + 1
        return total
    return 0


def _truncate_content(message: Dict, budget: int) -> Dict:
    """Truncate a single message's content to fit `budget` estimated tokens.

    Keeps the head of the content (semantic continuity) and appends a
    truncation marker.  Non-str content is left untouched.
    / 将单条消息内容截到预算（估算 token）内：保留开头、追加截断标记。
      非 str 内容不截。
    """
    m = dict(message)
    content = m.get("content")
    if not isinstance(content, str):
        return m
    max_chars = max(1, budget * 2 - len(TRUNCATION_MARKER))
    if len(content) > max_chars:
        m["content"] = content[:max_chars] + TRUNCATION_MARKER
    return m


def trim_messages(messages: List[Dict], max_tokens: int) -> List[Dict]:
    """App-layer max-context: trim a message list to an estimated token budget.

    Rules:
    1. Total within budget, empty list, or max_tokens<=0 → returned as-is
       (shallow copy, caller's list is never mutated).
    2. Single message → content truncated at the tail.
    3. Multiple messages → the LAST message is always kept (it is the newest
       user instruction); the others are dropped whole, largest-first, until
       the budget fits; if the last one alone still exceeds the budget it is
       truncated with a marker.
    / 应用层最大上下文：把消息列表裁剪到估算 token 预算内。规则：
      1. 总量达标/空列表/max_tokens<=0 → 原样返回（浅拷贝，不改调用方）；
      2. 单条消息 → 内容尾部截断；
      3. 多条消息 → 始终保留最后一条（最新用户指令），对其余按 token 从大到小
         整条删除直到达标；若仅剩最后一条仍超限，则截尾并追加标记。
    """
    if not messages or not max_tokens or max_tokens <= 0:
        return list(messages)

    def _tokens(m: Dict) -> int:
        return estimate_tokens(m.get("content") if isinstance(m, dict) else None)

    if sum(_tokens(m) for m in messages) <= max_tokens:
        return list(messages)

    trimmed = [dict(m) for m in messages]
    if len(trimmed) == 1:
        return [_truncate_content(trimmed[0], max_tokens)]

    last = trimmed[-1]
    others = trimmed[:-1]
    while others:
        if sum(_tokens(m) for m in others) + _tokens(last) <= max_tokens:
            break
        idx = max(range(len(others)), key=lambda i: _tokens(others[i]))
        others.pop(idx)

    if not others:
        return [_truncate_content(last, max_tokens)]

    if sum(_tokens(m) for m in others) + _tokens(last) > max_tokens:
        remaining = max_tokens - sum(_tokens(m) for m in others)
        if remaining > 0:
            last = _truncate_content(last, remaining)
        else:
            return [_truncate_content(last, max_tokens)]
    return others + [last]


class _EmptyLLMResponseError(Exception):
    """API 返回了缺失 choices/message/content 的异常载荷。

    部分 OpenAI 兼容服务会偶发返回 HTTP 200 但载荷不完整（choices 为空、
    message 为 null 等），属于可重试的瞬时故障。
    """


class LLMStreamClient:
    """OpenAI 兼容 LLM 请求客户端（非流式，stream=False 硬编码；实时推送由 SSE 层负责）"""

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
        :param api_key: API 密钥
        :param base_url: 自定义 API 地址（如 http://localhost:8000/v1）
        :param timeout: 单次请求读超时秒数。非流式长文生成（数千 token）
            远超 120s，过短的超时会让叙事节点必然失败；连接阶段保持 5s，
            停机地址快速失败。SDK 级自动重试关闭——超时重试只会把白等
            时间放大 3 倍，空响应重试由下方逻辑自行处理。
        """
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            max_retries=0,
        )
        self.default_model = default_model
        self.default_temperature = default_temperature if default_temperature is not None else 0.9
        self.isEnableThinking = isEnableThinking if isEnableThinking is not None else "disabled"
        self.default_max_tokens = default_max_tokens if default_max_tokens is not None else 2048
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
        # Per-call args take precedence over the client defaults; absent values
        # fall back to the constructor defaults (which may be None → disabled).
        # / 逐次调用参数优先于客户端默认值；缺省回退构造默认（可为 None → 不启用）。
        # Empty string / 0 mean "inherit the global default" at the per-call layer.
        # / 逐次调用层的空串 / 0 视为「继承全局默认」。
        effort = reasoning_effort if reasoning_effort else self.default_reasoning_effort
        per_call_ctx = max_context_tokens if isinstance(max_context_tokens, int) and max_context_tokens > 0 else None
        ctx_limit = per_call_ctx if per_call_ctx is not None else self.default_max_context_tokens
        if ctx_limit and ctx_limit > 0:
            messages = trim_messages(messages, ctx_limit)

        thinking_enabled = (isEnableThinking if isEnableThinking is not None else self.isEnableThinking) == "enabled"
        params = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
            "stream": False,
            "extra_body": {
                "thinking": {"type": isEnableThinking if isEnableThinking is not None else self.isEnableThinking}
            },
        }
        if response_format:
            params["response_format"] = response_format
        # reasoning_effort is a top-level chat.completions parameter (DeepSeek /
        # OpenAI compatible), sent only while thinking mode is enabled.
        # / reasoning_effort 是 chat.completions 顶层参数（DeepSeek/OpenAI 兼容），
        #   仅在思考模式开启时发送。
        if thinking_enabled and effort:
            params["reasoning_effort"] = effort

        last_error: Optional[_EmptyLLMResponseError] = None
        for attempt in range(self.EMPTY_RESPONSE_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(**params)
            except openai.APIError as e:
                raise RuntimeError(f"LLM API 请求失败: {e}") from e

            try:
                return self._extract_content(response, params["model"])
            except _EmptyLLMResponseError as e:
                last_error = e
                if attempt < self.EMPTY_RESPONSE_RETRIES:
                    wait = self.RETRY_BACKOFF_SECONDS * (attempt + 1)
                    print(
                        f"[LLMStreamClient] {e}，{wait:.0f}s 后自动重试"
                        f"（第 {attempt + 2}/{self.EMPTY_RESPONSE_RETRIES + 1} 次）",
                        flush=True,
                    )
                    time.sleep(wait)

        raise RuntimeError(f"LLM API 连续返回空响应: {last_error}") from last_error

    @staticmethod
    def _extract_content(response, model: str) -> str:
        """防御性提取回复文本。

        原实现直接对 response.choices[0].message.content 取下标，当兼容服务
        返回 choices=None 的载荷时会抛出 TypeError（NoneType object is not
        subscriptable，见 logs/graph_20260822_040538.log 中 actor_node 与
        introduce_character_node 的报错），现改为显式校验并转为可重试错误。
        """
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise _EmptyLLMResponseError(f"模型 {model} 返回异常响应（choices 为空）")

        choice = choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        finish_reason = getattr(choice, "finish_reason", None) or "unknown"

        if not content:
            raise _EmptyLLMResponseError(
                f"模型 {model} 返回空内容（finish_reason={finish_reason}）"
            )
        return content
