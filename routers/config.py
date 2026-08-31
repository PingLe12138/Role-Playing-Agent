"""LLM config, node-params and node-prompt endpoints.

/ LLM 配置、节点参数与节点提示词相关端点。
"""

from datetime import datetime
import json
import os
import shutil
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

import config_loader
from config_loader import load_config
from models import (
    ConfigTestRequest,
    ConfigUpdate,
    FeatureConfigUpdate,
    ImageGenerationTestRequest,
    ImageGenerationUpdate,
    NodeConfigExportData,
    NodeConfigUpdate,
    NodeContextsUpdate,
    NodeLlmUpdate,
    NodeParamsUpdate,
    NodePromptUpdate,
    SetupCompleteRequest,
    SystemRulesUpdate,
)
import paths
from routers.deps import ok

router = APIRouter()

_DEFAULT_CONFIG_PATH = str(paths.DEFAULT_CONFIG_PATH)


def _valid_node_names() -> set:
    try:
        with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
            return set(json.load(f).get("node_params", {}).keys())
    except Exception:
        return set()


def _read_config_safe():
    """Read config.json; return empty dict if file is missing or corrupted.
    / 读取 config.json；若文件缺失或损坏则返回空字典（避免前端白屏 / 500）。"""
    try:
        return load_config()
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_config_or_ensure():
    """Read config.json; if missing, create a default copy from template and
    return that.  This lets the PUT endpoints work even on a fresh checkout
    where the user hasn't manually created config.json yet.
    / 读取 config.json；若缺失则从模板创建默认副本再返回。
      让用户在新检出未手动创建 config.json 时也能通过 PUT 端点写入配置。"""
    if not paths.CONFIG_PATH.is_file() and paths.CONFIG_TEMPLATE_PATH.is_file():
        shutil.copy2(paths.CONFIG_TEMPLATE_PATH, paths.CONFIG_PATH)
    try:
        return load_config()
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_config(cfg: dict) -> None:
    """Persist `cfg` to config.json, backing up the previous file first.

    / 将 cfg 写回 config.json，写入前先备份原文件。
    """
    path = paths.CONFIG_PATH
    backup = paths.PROJECT_ROOT / "config.json.bak"
    if os.path.isfile(path):
        shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)


# ─── LLM Config ──────────────────────────────────────────────


@router.get("/api/config/llm")
def get_llm_config():
    return ok(_read_config_safe().get("llm", {}))


@router.put("/api/config/llm")
def update_llm_config(data: ConfigUpdate):
    cfg = _read_config_or_ensure()
    llm = cfg.setdefault("llm", {})
    for key in data.model_fields_set:
        val = getattr(data, key)
        if val is None:
            if key == "api_key":
                raise HTTPException(status_code=422, detail="api_key 不能为空")
            llm.pop(key, None)
            continue
        if key == "default_temperature" and not (0.0 <= val <= 2.0):
            raise HTTPException(status_code=422, detail="default_temperature 必须在 0~2 之间")
        if key == "default_max_tokens" and val <= 0:
            raise HTTPException(status_code=422, detail="default_max_tokens 必须为正整数")
        if key == "is_enable_thinking" and val not in ("enabled", "disabled"):
            raise HTTPException(status_code=422, detail="is_enable_thinking 只能为 enabled 或 disabled")
        if key == "protocol" and val not in ("openai", "anthropic"):
            raise HTTPException(status_code=422, detail="protocol 只能为 openai 或 anthropic")
        if key == "default_reasoning_effort" and val not in ("low", "medium", "high", "max"):
            raise HTTPException(status_code=422, detail="default_reasoning_effort 只能为 low、medium、high 或 max")
        if key == "max_context_tokens" and val < 0:
            raise HTTPException(status_code=422, detail="max_context_tokens 必须为非负整数（0 表示不裁剪）")
        llm[key] = val
    _write_config(cfg)
    config_loader.clear_cache(llm=True, node_params=False, node_prompts=False)
    return ok(msg="配置已更新，原配置已备份至 config.json.bak，下次对话生效")


@router.post("/api/config/llm/test")
def test_llm_config(data: ConfigTestRequest):
    start = time.time()
    try:
        client = config_loader.build_llm_client(
            {
                "protocol": data.protocol,
                "api_key": data.api_key,
                "base_url": data.base_url,
                "default_model": data.default_model,
            }
        )
        resp = client.chat([{"role": "user", "content": "请回复'连接成功'这四个字，不要包含其他内容。"}])
        elapsed = int((time.time() - start) * 1000)
        return ok({"success": True, "response": resp, "elapsed_ms": elapsed})
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return ok({"success": False, "error": str(e), "elapsed_ms": elapsed})


# ─── Per-node LLM overrides (`node_llm`) ─────────────────────────────────


def _sanitize_node_llm(raw: dict) -> dict:
    """Validate and normalize a `node_llm` map before persisting it.

    Unknown node names are rejected; unknown keys inside a node are dropped;
    empty strings / nulls are dropped so the node inherits the global value.
    / 持久化前校验并规范化 node_llm 映射：未知节点名拒绝；节点内未知键丢弃；
      空字符串/null 丢弃，使该字段继承全局值。
    """
    valid_nodes = _valid_node_names()
    cleaned: dict = {}
    for node_name, override in (raw or {}).items():
        if node_name not in valid_nodes:
            raise HTTPException(status_code=404, detail=f"未知节点: {node_name}")
        if not isinstance(override, dict) or not override:
            continue  # 空覆盖 = 继承全局
        entry: dict = {}
        for key in config_loader.NODE_LLM_OVERRIDE_KEYS:
            if key not in override:
                continue
            val = override[key]
            if val is None or (isinstance(val, str) and not val.strip()):
                continue  # 留空继承全局
            if key == "base_url" and not str(val).startswith(("http://", "https://")):
                raise HTTPException(status_code=422, detail=f"{node_name}.base_url 必须以 http:// 或 https:// 开头")
            if key == "default_temperature" and not (0.0 <= float(val) <= 2.0):
                raise HTTPException(status_code=422, detail=f"{node_name}.default_temperature 必须在 0~2 之间")
            if key == "default_max_tokens" and int(val) <= 0:
                raise HTTPException(status_code=422, detail=f"{node_name}.default_max_tokens 必须为正整数")
            if key == "is_enable_thinking" and val not in ("enabled", "disabled"):
                raise HTTPException(status_code=422, detail=f"{node_name}.is_enable_thinking 只能为 enabled 或 disabled")
            if key == "protocol" and val not in ("openai", "anthropic"):
                raise HTTPException(status_code=422, detail=f"{node_name}.protocol 只能为 openai 或 anthropic")
            if key == "timeout_seconds" and float(val) <= 0:
                raise HTTPException(status_code=422, detail=f"{node_name}.timeout_seconds 必须为正数")
            if key == "default_reasoning_effort" and val not in ("low", "medium", "high", "max"):
                raise HTTPException(status_code=422, detail=f"{node_name}.default_reasoning_effort 只能为 low、medium、high 或 max")
            if key == "max_context_tokens" and int(val) < 0:
                raise HTTPException(status_code=422, detail=f"{node_name}.max_context_tokens 必须为非负整数（0 表示不裁剪）")
            entry[key] = val
        if entry:
            cleaned[node_name] = entry
    return cleaned


@router.get("/api/config/node-llm")
def get_node_llm_config():
    """Return the per-node LLM overrides plus the global `llm` section (used as
    the placeholder / inheritance source in the config UI).

    / 返回逐节点 LLM 覆盖与全局 llm 段（供配置页作为占位符与继承来源）。
    """
    cfg = _read_config_safe()
    return ok({"node_llm": cfg.get("node_llm") or {}, "global": cfg.get("llm") or {}})


@router.put("/api/config/node-llm")
def update_node_llm_config(data: NodeLlmUpdate):
    """Wholesale replace the `node_llm` override map.

    / 整体替换 node_llm 覆盖表。留空的字段继承全局 llm 配置。
    """
    cfg = _read_config_or_ensure()
    cleaned = _sanitize_node_llm(data.node_llm)
    if cleaned:
        cfg["node_llm"] = cleaned
    else:
        cfg.pop("node_llm", None)
    _write_config(cfg)
    config_loader.clear_cache(llm=True, node_params=False, node_prompts=False)
    return ok(msg="节点 LLM 配置已更新，下次对话生效")


@router.get("/api/config/node-params")
def get_node_params_config():
    return ok(config_loader.get_node_params())


@router.put("/api/config/node-params")
def update_node_params_config(data: NodeParamsUpdate):
    cfg = _read_config_or_ensure()
    cfg["node_params"] = data.node_params
    _write_config(cfg)
    config_loader.clear_cache(llm=False, node_params=True, node_prompts=False)
    return ok(msg="节点参数已更新")


# ─── Node Prompts ────────────────────────────────────────────


@router.get("/api/config/node-prompts")
def get_node_prompts_config():
    return ok(config_loader.get_node_prompts())


@router.get("/api/config/node-prompts/defaults")
def get_node_prompts_defaults():
    try:
        with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
            defaults = json.load(f).get("node_prompts", {})
    except Exception:
        defaults = {}
    return ok(defaults)


@router.put("/api/config/node-prompt/{node_name}")
def update_node_prompt_config(node_name: str, data: NodePromptUpdate):
    valid_nodes = _valid_node_names()
    if node_name not in valid_nodes:
        raise HTTPException(status_code=404, detail=f"未知节点: {node_name}")

    cfg = _read_config_or_ensure()
    cfg.setdefault("node_prompts", {})[node_name] = data.prompt
    _write_config(cfg)
    config_loader.clear_cache(llm=False, node_params=False, node_prompts=True)
    return ok(msg=f"节点 {node_name} 的系统提示词已更新")


# ─── Shared System Rules ──────────────────────────────────────


@router.get("/api/config/system-rules")
def get_system_rules_config():
    """Return the effective shared system rules (config override or default).

    / 返回生效的共享系统限制（config.json 覆盖或默认值）。
    """
    return ok({"system_rules": config_loader.get_system_rules()})


@router.put("/api/config/system-rules")
def update_system_rules_config(data: SystemRulesUpdate):
    cfg = _read_config_or_ensure()
    if data.system_rules.strip():
        cfg["system_rules"] = data.system_rules
    else:
        # Empty string removes the override → falls back to the default rules.
        # / 空串移除覆盖 → 回退默认规则。
        cfg.pop("system_rules", None)
    _write_config(cfg)
    config_loader.clear_cache(llm=False, node_params=False, node_prompts=False, node_contexts=False, system_rules=True)
    return ok(msg="系统限制已更新，下次对话生效")


# ─── Node Context Injection ────────────────────────────────────


@router.get("/api/config/node-contexts")
def get_node_contexts_config():
    """Return the effective per-node context-block lists plus the full block
    catalog (id/title/desc) for the config UI picker.

    / 返回生效的逐节点上下文块清单与全量块目录（id/title/desc），供配置页选择器使用。
    """
    from RPA_langGraph.context_blocks import CONTEXT_BLOCKS

    blocks = [
        {"id": bid, "title": b["title"], "desc": b.get("desc", "")} for bid, b in CONTEXT_BLOCKS.items()
    ]
    return ok({"node_contexts": config_loader.get_node_contexts(), "blocks": blocks})


@router.put("/api/config/node-contexts")
def update_node_contexts_config(data: NodeContextsUpdate):
    cfg = _read_config_or_ensure()
    if data.node_contexts:
        cfg["node_contexts"] = data.node_contexts
    else:
        cfg.pop("node_contexts", None)
    _write_config(cfg)
    config_loader.clear_cache(llm=False, node_params=False, node_prompts=False, node_contexts=True)
    return ok(msg="节点上下文注入已更新，下次对话生效")


# ─── Unified Node Config Save ──────────────────────────────────


@router.put("/api/config/node-config")
def update_node_config(data: NodeConfigUpdate):
    cfg = _read_config_or_ensure()
    if data.node_params is not None:
        cfg["node_params"] = data.node_params
    if data.node_prompts is not None:
        cfg["node_prompts"] = data.node_prompts
    if data.node_contexts is not None:
        cfg["node_contexts"] = data.node_contexts
    if data.node_llm is not None:
        cleaned = _sanitize_node_llm(data.node_llm)
        if cleaned:
            cfg["node_llm"] = cleaned
        else:
            cfg.pop("node_llm", None)
    _write_config(cfg)
    config_loader.clear_cache(llm=True, node_params=True, node_prompts=True, node_contexts=True)
    return ok(msg="节点配置已保存")


# ─── Node Config Export / Import ─────────────────────────────────


@router.get("/api/config/node-config/export")
def export_node_config():
    cfg = _read_config_safe()
    node_params = cfg.get("node_params", {})
    node_prompts = cfg.get("node_prompts", {})
    node_contexts = cfg.get("node_contexts", {})
    system_rules = cfg.get("system_rules")
    export_data = NodeConfigExportData(
        exported_at=datetime.now().isoformat(),
        node_params=node_params,
        node_prompts=node_prompts,
        node_contexts=node_contexts,
        system_rules=system_rules,
    )
    filename = "node_config.json"
    encoded_name = quote(filename, safe="")
    return Response(
        content=export_data.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.post("/api/config/node-config/import")
def import_node_config(data: NodeConfigExportData):
    if not data.node_params and not data.node_prompts and data.system_rules is None:
        return ok(msg="配置文件内容为空，未做修改")
    cfg = _read_config_or_ensure()
    if data.node_params:
        cfg["node_params"] = data.node_params
    if data.node_prompts:
        cfg["node_prompts"] = data.node_prompts
    if data.node_contexts:
        cfg["node_contexts"] = data.node_contexts
    if data.system_rules is not None:
        if data.system_rules.strip():
            cfg["system_rules"] = data.system_rules
        else:
            cfg.pop("system_rules", None)
    _write_config(cfg)
    config_loader.clear_cache(llm=False, node_params=True, node_prompts=True, node_contexts=True, system_rules=True)
    return ok(msg="节点配置已导入")


# ─── Feature Toggles ──────────────────────────────────────────


@router.get("/api/config/features")
def get_features_config():
    return ok(_read_config_safe().get("features", {}))


@router.put("/api/config/features")
def update_features_config(data: FeatureConfigUpdate):
    cfg = _read_config_or_ensure()
    features = cfg.setdefault("features", {})
    for key in data.model_fields_set:
        val = getattr(data, key)
        if val is None:
            features.pop(key, None)
            continue
        if key == "memory_summarize_interval" and val <= 0:
            raise HTTPException(status_code=422, detail="memory_summarize_interval 必须为正整数")
        features[key] = val
    _write_config(cfg)
    return ok(msg="功能配置已更新")


# ─── Scene Image Generation (ComfyUI) ────────────────────────────


@router.get("/api/config/image-generation")
def get_image_generation_config_endpoint():
    """Return the effective scene-image generation config (defaults + config.json
    `image_generation` overrides, merged).  / 返回生效的场景插画配置（默认 + 覆盖合并）。"""
    return ok(config_loader.get_image_generation_config())


@router.put("/api/config/image-generation")
def update_image_generation_config(data: ImageGenerationUpdate):
    """Persist `image_generation` overrides into config.json (partial update —
    only the fields present in the request are written; None removes a key).

    / 将 image_generation 覆盖项写入 config.json（部分更新——只写请求中出现的
      字段；None 移除对应键）。"""
    cfg = _read_config_or_ensure()
    section = cfg.setdefault("image_generation", {})
    for key in data.model_fields_set:
        val = getattr(data, key)
        if val is None:
            section.pop(key, None)
            continue
        if key in ("width", "height", "steps") and int(val) <= 0:
            raise HTTPException(status_code=422, detail=f"{key} 必须为正整数")
        if key == "max_per_session" and int(val) <= 0:
            raise HTTPException(status_code=422, detail="max_per_session 必须为正整数")
        if key == "interval_seconds" and int(val) < 0:
            raise HTTPException(status_code=422, detail="interval_seconds 不能为负")
        if key == "cfg" and float(val) <= 0:
            raise HTTPException(status_code=422, detail="cfg 必须为正数")
        section[key] = val
    if not section:
        cfg.pop("image_generation", None)
    _write_config(cfg)
    config_loader.clear_cache(llm=False, node_params=False, node_prompts=False, image_gen_config=True)
    return ok(msg="场景插画配置已更新，下次对话生效")


@router.post("/api/config/image-generation/test")
def test_image_generation_config(data: ImageGenerationTestRequest = None):
    """Probe a ComfyUI server: connectivity + latency + available checkpoints.
    Uses the request body's `comfyui_base_url` when provided (the form's
    unsaved value), otherwise the saved config.  Never raises — returns
    {success: bool} for the frontend.
    / 探测 ComfyUI 服务：连通性 + 延迟 + 可用模型列表。优先使用请求体中的
      comfyui_base_url（表单未保存的值），缺省回退到已保存配置。不抛异常，
      返回 {success: bool} 供前端判断。"""
    from services.comfyui_client import ComfyUIClient, ComfyUIError

    cfg = config_loader.get_image_generation_config()
    base_url = (data and data.comfyui_base_url) or cfg.get(
        "comfyui_base_url", "http://127.0.0.1:8188"
    )
    start = time.time()
    try:
        client = ComfyUIClient(base_url=base_url)
        client.health_check()
        elapsed_ms = int((time.time() - start) * 1000)
        checkpoints: list = []
        try:
            info = client._request_json("/object_info/CheckpointLoaderSimple", timeout=5)
            required = (info.get("CheckpointLoaderSimple", {}) or {}).get("input", {}).get("required", {})
            ckpts = (required or {}).get("ckpt_name", [])
            if isinstance(ckpts, list) and ckpts and isinstance(ckpts[0], list):
                checkpoints = [c for c in ckpts[0] if isinstance(c, str)]
        except Exception:
            checkpoints = []  # object_info 失败不影响连通性结果
        return ok({"success": True, "elapsed_ms": elapsed_ms, "checkpoints": checkpoints})
    except ComfyUIError as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return ok({"success": False, "error": str(e), "elapsed_ms": elapsed_ms})


# ─── First-run Setup Wizard ─────────────────────────────────────
# The wizard runs once per installation: the frontend router redirects to
# /setup until `setup.completed` is persisted in config.json.  All the values
# it collects are written through the regular config endpoints above; this
# section only owns the "has the user been onboarded yet" flag plus a
# pre-flight status payload.
# / 引导每次安装只跑一次：前端路由会把用户重定向到 /setup，直到 config.json
#   中持久化了 setup.completed。向导收集的值仍通过上面的常规配置端点写入，
#   本节只负责「用户是否已完成引导」标记与预检状态。


def _embedding_ready(path: str) -> bool:
    """True when the local embedding-model directory exists and is non-empty.
    / 本地嵌入模型目录存在且非空时为 True。"""
    try:
        return os.path.isdir(path) and bool(os.listdir(path))
    except OSError:
        return False


@router.get("/api/setup/status")
def get_setup_status():
    """Return the onboarding state plus the current values the wizard prefills.

    `llm_configured` is False while `llm.api_key` still holds the template
    placeholder, so a fresh checkout reports "not configured" even though
    config.json exists.
    / 返回引导状态与向导需要预填的当前值。当 llm.api_key 仍是模板占位符时
      llm_configured 为 False——全新检出即便已有 config.json 也判定为未配置。
    """
    cfg = _read_config_safe()
    setup = cfg.get("setup") if isinstance(cfg.get("setup"), dict) else {}
    image_cfg = config_loader.get_image_generation_config()
    embedding_path = config_loader.get_embedding_model_path()
    return ok(
        {
            "completed": bool(setup.get("completed")),
            "completed_at": setup.get("completed_at"),
            "skipped": bool(setup.get("skipped")),
            "llm_configured": config_loader.is_llm_configured(),
            "llm": cfg.get("llm") or {},
            "features": cfg.get("features") or {},
            "embedding": {"path": embedding_path, "ready": _embedding_ready(embedding_path)},
            "image_generation": {
                "enabled": bool(image_cfg.get("enabled")),
                "comfyui_base_url": image_cfg.get("comfyui_base_url", ""),
                "checkpoint": image_cfg.get("checkpoint", ""),
            },
        }
    )


@router.post("/api/setup/complete")
def complete_setup(data: SetupCompleteRequest):
    """Mark the wizard as finished (or skipped) and stamp the completion time.
    / 标记引导完成（或跳过）并写入完成时间。"""
    cfg = _read_config_or_ensure()
    cfg["setup"] = {
        "completed": True,
        "skipped": bool(data.skipped),
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_config(cfg)
    config_loader.clear_cache(
        llm=False, node_params=False, node_prompts=False, node_contexts=False, system_rules=False, setup=True
    )
    return ok(msg="初始化引导已完成")


@router.post("/api/setup/reset")
def reset_setup():
    """Clear the completion flag so the wizard runs again on the next visit.
    Backed by the "re-run setup wizard" button on the config page.
    / 清除完成标记，使下次进入系统时重新运行引导（配置页「重新运行初始化引导」按钮）。"""
    cfg = _read_config_or_ensure()
    cfg.pop("setup", None)
    _write_config(cfg)
    config_loader.clear_cache(
        llm=False, node_params=False, node_prompts=False, node_contexts=False, system_rules=False, setup=True
    )
    return ok(msg="初始化引导已重置，下次进入系统时重新显示")