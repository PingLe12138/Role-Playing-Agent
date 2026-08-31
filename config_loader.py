import json
from pathlib import Path
import re
import threading
from typing import Dict, List, Optional, Tuple

from AnthropicLLMClient import AnthropicLLMClient
from LLMStreamClient import LLMStreamClient
import paths
from RPA_langGraph.context_blocks import block_id_for, render_new_context_blocks
from RPA_langGraph.prompts import SYSTEM_RULES

_DEFAULT_CONFIG_PATH = str(paths.DEFAULT_CONFIG_PATH)
_node_params: Optional[dict] = None
_node_prompts: Optional[dict] = None
_node_contexts: Optional[dict] = None
_default_config: Optional[dict] = None
_system_rules: Optional[str] = None
_image_gen_config: Optional[dict] = None
_embedding_model_path: Optional[str] = None
_setup_config: Optional[dict] = None

# API keys that mean "not configured yet" — they come from the shipped
# config.template.json and must never count as a real credential when the
# first-run wizard checks whether the LLM connection is usable.
# / 表示「尚未配置」的占位密钥——来自随仓库分发的 config.template.json，
#   首次引导检查 LLM 是否可用时不能把它们当成真实凭据。
SETUP_PLACEHOLDER_API_KEYS = frozenset(
    {"your-api-key-here", "your_api_key", "YOUR_API_KEY", "sk-xxx", "changeme"}
)

# Default local embedding-model directory (overridable via config.json
# `embedding.model_path`). / 本地嵌入模型目录默认值（可由 config.json 的
# embedding.model_path 覆盖）。
EMBEDDING_MODEL_PATH_DEFAULT = "models/Qwen3-Embedding-0.6B"

# Defaults for the scene-image generation feature (overridable via config.json
# `image_generation` section). / 场景插画功能的默认配置（可由 config.json 的
# image_generation 段覆盖）。
IMAGE_GENERATION_DEFAULTS: dict = {
    "enabled": False,
    "comfyui_base_url": "http://127.0.0.1:8188",
    "checkpoint": "animagine-xl-4.0.safetensors",
    "width": 896,
    "height": 1152,
    "steps": 30,
    "cfg": 6.0,
    "sampler_name": "dpmpp_2m",
    "scheduler": "karras",
    "negative_prompt": (
        "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
        "fewer digits, cropped, worst quality, low quality, normal quality, "
        "jpeg artifacts, signature, watermark, username, blurry"
    ),
    "interval_seconds": 180,
    "max_per_session": 30,
    "llm_decision_enabled": True,
    "timeout_seconds": 300,
    "poll_interval_seconds": 1.0,
}

# Template context-section parsing:  === 标题 === 后跟 {placeholder}
# / 模板上下文节解析：=== 标题 === 后跟 {placeholder}
_SECTION_RE = re.compile(r"===\s*[^=\n]+?\s*===\s*\n\{[a-z_]+\}")
_SLOT_RE = re.compile(r"\x00(\d+)\x00")
_SECTION_PH_RE = re.compile(r"\{([a-z_]+)\}\s*$")


def load_config(path: Optional[str] = None) -> dict:
    """Load config.json. `path` defaults to the project-root anchored
    config.json (an explicit relative/absolute path is honored as-is).

    / 加载 config.json。path 缺省时锚定项目根的 config.json（显式传入的
      相对/绝对路径原样生效）。
    """
    with open(path or paths.CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_default_config() -> dict:
    global _default_config
    if _default_config is None:
        with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
            _default_config = json.load(f)
    return _default_config


def get_node_params() -> dict:
    global _node_params
    if _node_params is None:
        defaults = _load_default_config().get("node_params", {})
        overrides = load_config().get("node_params", {})
        _node_params = {**defaults, **overrides}
    return _node_params


def get_node_prompts() -> dict:
    global _node_prompts
    if _node_prompts is None:
        defaults = _load_default_config().get("node_prompts", {})
        overrides = load_config().get("node_prompts", {})
        _node_prompts = {**defaults, **overrides}
    return _node_prompts


def get_node_prompt(node_name: str) -> Optional[str]:
    """Return the effective prompt for a node (default + override merged)."""
    prompts = get_node_prompts()
    return prompts.get(node_name)


def get_node_contexts() -> dict:
    """Return the effective per-node context-block lists (defaults + overrides).

    Each entry is an ordered list of block items: either a plain string (block
    id) or a dict with id / optional title / enabled / args.
    / 返回生效的逐节点上下文块清单（默认 + 覆盖）。每项为块 id 字符串或
      含 id 与可选 title/enabled/args 的对象。
    """
    global _node_contexts
    if _node_contexts is None:
        defaults = _load_default_config().get("node_contexts", {})
        overrides = load_config().get("node_contexts", {})
        merged: dict = {**defaults}
        for k, v in overrides.items():
            merged[k] = v
        _node_contexts = merged
    return _node_contexts


def get_node_context(node_name: str) -> list:
    """Return the ordered context-block list for one node (may be empty)."""
    return list(get_node_contexts().get(node_name, []))


def get_system_rules() -> str:
    """Return the shared system-rules block appended to every node prompt.

    Resolution order: config.json system_rules → defaultconfig.json
    system_rules → RPA_langGraph.prompts.SYSTEM_RULES fallback constant.
    / 返回追加到所有节点提示词末尾的共享系统限制块。解析顺序：
      config.json system_rules → defaultconfig.json system_rules
      → RPA_langGraph.prompts.SYSTEM_RULES 兜底常量。
    """
    global _system_rules
    if _system_rules is None:
        cfg = load_config()
        _system_rules = cfg.get("system_rules") or _load_default_config().get("system_rules") or SYSTEM_RULES
    return _system_rules


class _SafeFormatDict(dict):
    """Missing placeholder keys stay verbatim instead of raising KeyError.

    / 缺失的占位符键原样保留而不抛 KeyError（兼容旧覆盖模板中的未知占位符）。
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def apply_context_config(
    node_name: str, template: str, state: Optional[dict] = None, extra: Optional[dict] = None
) -> Tuple[str, str]:
    """Filter / reorder / append the template's context sections per node config.

    Sections matching a managed block id are reordered by the configured block
    list (disabled blocks leave an empty slot); task-parameter sections and
    unlisted template sections keep their original slots.  Blocks present in
    the config but absent from the template are rendered and returned as
    new_blocks_text for appending after formatting.

    With the default config (block order == template order, all enabled) the
    output is byte-identical to the input template.

    / 按节点上下文配置过滤/重排/追加模板中的上下文节。受管块的节按配置顺序
      重排（禁用的块留空槽）；任务参数节与配置未列出的模板节保留原位置。
      配置中存在但模板缺失的块被渲染并作为 new_blocks_text 返回，供格式化后追加。
      默认配置（块顺序==模板顺序、全部启用）下输出与输入逐字一致。
    """
    if not template:
        return template, ""

    tokens: List[str] = []
    sections: List[str] = []
    pos = 0
    for m in _SECTION_RE.finditer(template):
        tokens.append(template[pos : m.start()])
        tokens.append("\x00%d\x00" % len(sections))
        sections.append(m.group(0))
        pos = m.end()
    tokens.append(template[pos:])
    slots_text = "".join(tokens)

    cfg = [item if isinstance(item, dict) else {"id": item} for item in get_node_context(node_name)]
    cfg_by_id: Dict[str, dict] = {item["id"]: item for item in cfg}
    order = {item["id"]: i for i, item in enumerate(cfg)}

    fixed_fill: Dict[int, str] = {}  # 任务参数节与配置未列节 → 原槽保留
    managed: List[Tuple[str, str]] = []  # 受管启用节 (block_id, section_text)
    existing_ids: set = set()
    for i, sec in enumerate(sections):
        m = _SECTION_PH_RE.search(sec)
        ph = m.group(1) if m else ""
        bid = block_id_for(node_name, ph)
        if bid is None:
            fixed_fill[i] = sec
            continue
        existing_ids.add(bid)
        item = cfg_by_id.get(bid)
        if item is None:
            fixed_fill[i] = sec  # 模板自有节（配置未列出）→ 原槽保留
        elif item.get("enabled", True) is False:
            pass  # 禁用 → 槽留空
        else:
            managed.append((bid, sec))

    managed.sort(key=lambda t: order.get(t[0], 999))

    managed_iter = iter(managed)
    fills: List[str] = []
    for i in range(len(sections)):
        if i in fixed_fill:
            fills.append(fixed_fill[i])
        else:
            fills.append(next(managed_iter, ("", ""))[1])

    new_template = _SLOT_RE.sub(lambda m: fills[int(m.group(1))], slots_text)

    new_blocks = render_new_context_blocks(cfg, existing_ids, state, extra)
    new_blocks_text = "\n\n".join(new_blocks) if new_blocks else ""
    return new_template, new_blocks_text


def build_node_prompt(
    node_name: str,
    template: str,
    *,
    respect_override: bool = True,
    context_state: Optional[dict] = None,
    context_extra: Optional[dict] = None,
    **kwargs,
) -> str:
    """Build a node's final system prompt.

    1. Effective template = node_prompts override or the default template.
    2. Context sections are filtered/reordered per node_contexts config;
       user-added blocks (not in the template) are rendered and appended.
    3. Template is formatted with kwargs (missing placeholders stay verbatim).
    4. The shared system-rules block is appended (dedupe guard included).

    / 构建节点最终系统提示词：
      1. 生效模板 = node_prompts 覆盖或默认模板；
      2. 按 node_contexts 配置过滤/重排上下文节，模板缺失的新增块被渲染并追加；
      3. 用 kwargs 格式化模板（缺失占位符原样保留）；
      4. 末尾追加共享系统限制（含防重守卫）。

    respect_override=False uses template verbatim (departure-memory path).
    / respect_override=False 时跳过覆盖查找（离场记忆路径）。
    """
    base = (get_node_prompt(node_name) or template) if respect_override else template
    base, new_blocks_text = apply_context_config(node_name, base, context_state, context_extra)
    prompt = base.format_map(_SafeFormatDict(kwargs))
    if new_blocks_text:
        prompt = prompt.rstrip() + "\n\n" + new_blocks_text
    rules = get_system_rules()
    if rules and rules not in prompt:
        prompt = prompt.rstrip() + "\n\n" + rules
    return prompt


# ─── Per-node LLM overrides (config.json `node_llm`) ──────────────────────
# A node may override any subset of the global `llm` connection settings.
# Values that are absent, null or empty strings fall back to the global
# section, so a node only has to spell out what actually differs.
# / 节点可覆盖全局 llm 连接设置的任意子集。缺省/null/空字符串回退全局，
#   节点只需填写真正不同的字段。
NODE_LLM_OVERRIDE_KEYS = (
    "protocol",
    "api_key",
    "base_url",
    "default_model",
    "default_temperature",
    "default_max_tokens",
    "is_enable_thinking",
    "timeout_seconds",
    "default_reasoning_effort",
    "max_context_tokens",
)

# Client cache keyed by node name ("" = global).  The parallel todo-batch
# executor calls get_llm() from many threads, so creation is lock-guarded.
# / 以节点名为键的客户端缓存（"" 表示全局）。todo_batch 并行执行时会有多
#   个线程同时调用 get_llm()，因此创建过程加锁保护。
_llm_cache: Dict[str, object] = {}
_llm_fingerprints: Dict[str, dict] = {}
_llm_lock = threading.Lock()


def get_node_llm_configs() -> dict:
    """Return the raw `node_llm` override map from config.json (may be empty).

    / 返回 config.json 中原始的 node_llm 覆盖表（可能为空）。
    """
    return load_config().get("node_llm") or {}


def get_node_llm_config(node_name: str) -> dict:
    """Return one node's raw override dict; `{}` means "inherit everything".

    / 返回单个节点的原始覆盖字典；`{}` 表示「全部继承全局」。
    """
    override = get_node_llm_configs().get(node_name)
    return override if isinstance(override, dict) else {}


def _merge_llm_config(global_cfg: dict, override: dict) -> dict:
    """Overlay a node's non-empty override keys onto the global settings.

    / 把节点的非空覆盖键叠加到全局设置上（缺省/null/空白串一律跳过）。
    """
    merged = dict(global_cfg)
    if not isinstance(override, dict):
        return merged
    for key in NODE_LLM_OVERRIDE_KEYS:
        if key not in override:
            continue
        val = override[key]
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue  # 空字符串视为未配置 → 继承全局
        merged[key] = val
    return merged


def resolve_llm_config(node_name: Optional[str] = None) -> dict:
    """Resolve the effective LLM connection settings for a node.

    Precedence: `node_llm[node]` (non-empty values only) → global `llm`.
    / 解析节点生效的 LLM 连接设置，优先级：node_llm[node]（仅非空值）→ 全局 llm。
    """
    cfg = load_config()
    global_cfg = cfg.get("llm") or {}
    if not node_name:
        return dict(global_cfg)
    return _merge_llm_config(global_cfg, (cfg.get("node_llm") or {}).get(node_name) or {})


def build_llm_client(llm_cfg: dict):
    """Factory: build the LLM client matching `llm_cfg["protocol"]`.

    protocol 缺省/空串/未知值一律回退 openai（向后兼容）；"anthropic"
    返回 AnthropicLLMClient。两者构造与 chat() 签名一致，调用方无需感知协议。
    / 按 llm_cfg["protocol"] 返回对应 LLM 客户端：protocol 缺省/空串/未知值
      回退 OpenAI 兼容客户端；"anthropic" 返回 Anthropic 客户端。
    """
    protocol = (llm_cfg.get("protocol") or "openai").strip().lower()
    try:
        timeout_seconds = float(llm_cfg.get("timeout_seconds", 600))
    except (TypeError, ValueError):
        timeout_seconds = 600.0
    if timeout_seconds <= 0:
        timeout_seconds = 600.0
    common = {
        "api_key": llm_cfg.get("api_key", ""),
        "base_url": llm_cfg.get("base_url"),
        "default_model": llm_cfg.get("default_model", "gpt-4o-mini"),
        "default_temperature": llm_cfg.get("default_temperature"),
        "default_max_tokens": llm_cfg.get("default_max_tokens"),
        "isEnableThinking": llm_cfg.get("is_enable_thinking"),
        "timeout": timeout_seconds,
        "default_reasoning_effort": llm_cfg.get("default_reasoning_effort"),
        "max_context_tokens": llm_cfg.get("max_context_tokens"),
    }
    if protocol == "anthropic":
        return AnthropicLLMClient(**common)
    return LLMStreamClient(**common)


def get_llm(node_name: Optional[str] = None) -> LLMStreamClient:
    """Return the LLM client to use for one node.

    `node_name` selects the `node_llm[node]` override; when the override is
    absent (or resolves to the same settings as global) the shared global
    client is reused.  Clients are cached per node and rebuilt automatically
    whenever the resolved config changes, so editing config.json takes effect
    on the next call even without clear_cache().
    / 返回某节点使用的 LLM 客户端。node_name 选择 node_llm[node] 覆盖；
      覆盖缺失（或与全局解析结果相同）时复用全局客户端。客户端按节点缓存，
      配置变化时自动重建，因此修改 config.json 后即使不主动清缓存也会在
      下次调用时生效。

    Precedence for the values actually sent to the API stays 3-layer:
    `node_params[node]` per-call args (temperature / max_tokens / thinking)
    → this client's defaults (per-node LLM config) → global `llm`.
    / 实际请求参数的优先级仍为三层：node_params[node] 的逐次调用参数
      （温度/最大 Token/思考模式）→ 本客户端默认值（节点级 LLM 配置）→ 全局 llm。
    """
    cfg_all = load_config()
    global_cfg = cfg_all.get("llm") or {}
    if node_name:
        override = (cfg_all.get("node_llm") or {}).get(node_name) or {}
        cfg = _merge_llm_config(global_cfg, override)
    else:
        cfg = dict(global_cfg)
    key = node_name or ""
    if node_name and cfg == global_cfg:
        key = ""  # 无实际覆盖 → 复用全局客户端，避免重复建连
    with _llm_lock:
        cached = _llm_cache.get(key)
        if cached is not None and _llm_fingerprints.get(key) == cfg:
            return cached
        client = build_llm_client(cfg)
        _llm_cache[key] = client
        _llm_fingerprints[key] = cfg
        return client


def is_player_choice_enabled() -> bool:
    """Read the player_choice_enabled feature flag from config.json.
    Defaults to True for backward compatibility (no feature toggle → enabled).
    / 从 config.json 读取 player_choice_enabled 功能开关。默认 True 以向后兼容。
    """
    cfg = load_config()
    return cfg.get("features", {}).get("player_choice_enabled", True)


def get_memory_summarize_interval() -> int:
    """Read the memory summarization interval (in rounds) from config.json.
    Defaults to 10; invalid values fall back to 10.
    / 从 config.json 读取记忆总结间隔（轮数）。默认 10；非法值回退 10。
    """
    cfg = load_config()
    try:
        val = int(cfg.get("features", {}).get("memory_summarize_interval", 10))
    except (TypeError, ValueError):
        val = 10
    return val if val > 0 else 10


def get_embedding_model_path() -> str:
    """Return the local embedding-model directory from config.json
    `embedding.model_path`. Missing/empty/invalid values fall back to
    EMBEDDING_MODEL_PATH_DEFAULT. Cached like the other config singletons.

    / 返回 config.json `embedding.model_path` 指定的本地嵌入模型目录。
      缺失/为空/非法时回退 EMBEDDING_MODEL_PATH_DEFAULT。与其他配置单例一样缓存。
    """
    global _embedding_model_path
    if _embedding_model_path is None:
        cfg = load_config()
        path = cfg.get("embedding", {}).get("model_path")
        raw = path if isinstance(path, str) and path.strip() else EMBEDDING_MODEL_PATH_DEFAULT
        # Relative paths are anchored to the project root; absolute paths stay as-is.
        # / 相对路径锚定到项目根；绝对路径原样保留。
        p = Path(raw)
        _embedding_model_path = str(p) if p.is_absolute() else str(paths.PROJECT_ROOT / p)
    return _embedding_model_path


def get_image_generation_config() -> dict:
    """Return the effective scene-image generation config (defaults + config.json
    `image_generation` overrides, merged shallowly).

    / 返回生效的场景插画配置（默认值 + config.json image_generation 覆盖，浅合并）。
    """
    global _image_gen_config
    if _image_gen_config is None:
        overrides = load_config().get("image_generation", {})
        _image_gen_config = {**IMAGE_GENERATION_DEFAULTS, **overrides}
    return _image_gen_config


def get_setup_config() -> dict:
    """Return the first-run wizard state (`setup` section of config.json).

    Shape: {"completed": bool, "completed_at": str|None, "skipped": bool}.
    A missing / malformed section means "never completed" → the wizard runs.
    / 返回首次引导状态（config.json 的 setup 段）。结构：
      {"completed": bool, "completed_at": str|None, "skipped": bool}。
      缺失或格式非字典视为「从未完成」→ 触发引导。
    """
    global _setup_config
    if _setup_config is None:
        section = load_config().get("setup")
        _setup_config = section if isinstance(section, dict) else {}
    return _setup_config


def is_setup_completed() -> bool:
    """True once the first-run setup wizard has been completed (or skipped).
    / 首次引导完成（或跳过）后为 True。"""
    return bool(get_setup_config().get("completed"))


def is_llm_configured() -> bool:
    """True when the global `llm.api_key` holds a non-placeholder credential.

    Used by the wizard to pre-check / badge the LLM step; a key equal to the
    template placeholder (or empty) counts as unconfigured.
    / 全局 llm.api_key 是否为非占位凭据。占位密钥或空串视为未配置。
    """
    llm = load_config().get("llm") or {}
    api_key = str(llm.get("api_key") or "").strip()
    return bool(api_key) and api_key.lower() not in {k.lower() for k in SETUP_PLACEHOLDER_API_KEYS}


def clear_cache(
    *,
    llm: bool = True,
    node_params: bool = True,
    node_prompts: bool = True,
    node_contexts: bool = True,
    system_rules: bool = True,
    image_gen_config: bool = False,
    embedding_model_path: bool = False,
    setup: bool = False,
) -> None:
    """Invalidate the cached singletons so the next accessor re-reads config files.

    / 清除缓存的单例，使下次访问时重新读取文件。Call this after any
    config.json write so the change takes effect on the next graph run / read.
    / 在每次写入 config.json 后调用，使改动在下次图运行/读取时生效。
    """
    global _node_params, _node_prompts, _node_contexts, _system_rules  # noqa: PLW0603
    global _image_gen_config, _embedding_model_path, _setup_config  # noqa: PLW0603
    if setup:
        _setup_config = None
    if llm:
        with _llm_lock:
            _llm_cache.clear()
            _llm_fingerprints.clear()
    if node_params:
        _node_params = None
    if node_prompts:
        _node_prompts = None
    if node_contexts:
        _node_contexts = None
    if system_rules:
        _system_rules = None
    if image_gen_config:
        _image_gen_config = None
    if embedding_model_path:
        _embedding_model_path = None
