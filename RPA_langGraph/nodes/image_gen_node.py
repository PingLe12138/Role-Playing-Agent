"""Scene-image generation node — the last step of the director subgraph.

/ 场景插画生成节点——Director 子图的最后一步。

Runs after the review chain has finalized env data / roster / emotions, so it
sees the freshest snapshot of the turn.  It decides *whether* this turn
deserves an illustration (LLM judge, optional), builds an English SD prompt,
calls the local ComfyUI, persists the PNG under static/scene_images/, writes a
`scene_image` row into session_history, and pushes it to the frontend over SSE.

Failure policy: this node must NEVER break the narrative.  Disabled config,
cooldown / per-session caps, ComfyUI being offline, LLM deciding "no", or any
exception — all end the node gracefully with a logged reason and an empty
state update.

/ 在审看链（环境/角色/情绪已定稿）之后运行，拿到本轮最新快照。节点负责判断
  本回合是否值得生成插画（可选 LLM 判定）、构建英文 SD 提示词、调用本机
  ComfyUI、将 PNG 持久化到 static/scene_images/、写入 scene_image 历史行并
  通过 SSE 推送到前端。

  失败策略：本节点绝不能破坏剧情。配置禁用、冷却/会话上限、ComfyUI 离线、
  LLM 判定"否"、或任何异常——都以记录原因 + 返回空状态更新优雅结束。
"""

from datetime import datetime, timezone
import json
import time
import traceback
from typing import Any, Dict, Optional

from config_loader import build_node_prompt, get_image_generation_config, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.comfyui_client import ComfyUIClient, ComfyUIError
from services.formatters import chat_json, fmt_env_data, fmt_history
from services.id_utils import generate_history_id
from SQLiteClient import db_lock, get_db
from SSEPublisher import publisher

SCENE_IMAGE_TYPE = "scene_image"

IMAGE_GEN_PROMPT = (
    """你是一个动漫场景插画生成节点 (Scene Image)。
根据当前剧情场景，判断本回合是否值得生成一张场景插画，并在值得时输出 Stable Diffusion 英文提示词。

=== 当前环境 ===
{env_data}

=== 本轮剧情内容 ===
{node_outputs}

=== 最近对话 ===
{recent_history}

请判断当前场景是否具备明显的画面感：
- 值得生成：出现了新地点、新人物、重要氛围或光线变化、戏剧性时刻、动作场面等有视觉冲击力的场景
- 不值得生成：纯对话过渡、场景与上一回合基本一致、无视觉变化

若值得生成，请严格按以下 JSON 格式返回，不要包含其他内容：
{{
    "generate": true,
    "prompt": "英文SD提示词",
    "negative": "英文负面提示词或空字符串",
    "caption": "中文一句话画面说明"
}}

若不值得生成：
{{
    "generate": false,
    "reason": "简短原因"
}}

prompt 要求（英文）：
1. 先加质量词：masterpiece, best quality, very aesthetic, absurdres, highres
2. 描述画面主体：人物（外貌、服装、表情、动作）、场景（地点、道具、背景）、氛围（光线、天气、色调）、构图（视角、景别）
3. 日系动漫插画风格，不要写真人摄影词汇（photo, realistic 等）
4. 用逗号分隔标签，简洁准确，50-120 词

negative 要求（英文）：列出低质量与毁图词；不确定时留空字符串（系统会用默认负面提示词）
"""
)


def _parse_sqlite_time(text: Optional[str]) -> Optional[float]:
    """Parse SQLite `datetime('now')` (UTC, "YYYY-MM-DD HH:MM:SS") to epoch.
    / 将 SQLite datetime('now')（UTC）解析为 epoch 秒。"""
    if not text:
        return None
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _image_stats(db, session_id: str) -> tuple[int, Optional[float]]:
    """Return (count, last_created_epoch) of scene_image rows for the session.
    / 返回该会话 scene_image 历史行数 (count) 与最近一张的时间戳 (epoch)。"""
    rows = db.fetchall(
        "SELECT recordCreatedTime FROM session_history "
        "WHERE parentID = ? AND content LIKE ?",
        (session_id, '%"contentType": "scene_image"%'),
    )
    count = len(rows)
    last_epoch = None
    for r in rows:
        ts = _parse_sqlite_time(r.get("recordCreatedTime"))
        if ts is not None and (last_epoch is None or ts > last_epoch):
            last_epoch = ts
    return count, last_epoch


def _build_scene_summary(state: AgentState, node_outputs: str) -> str:
    """Assemble the compact scene snapshot fed to the LLM judge.
    / 组装提供给 LLM 判定的紧凑场景快照。"""
    env_text = fmt_env_data(state.get("sessionEnvData", {}))
    history = state.get("sessionHistory", [])
    recent = fmt_history(history[-12:]) if history else "(空)"
    return (
        f"=== 当前环境 ===\n{env_text}\n\n"
        f"=== 本轮剧情内容 ===\n{node_outputs or '(无)'}\n\n"
        f"=== 最近对话 ===\n{recent}"
    )


def _extract_turn_outputs(state: AgentState) -> str:
    """Extract this turn's actor/narration text from sessionHistory.

    NOTE: directorGraphOutput is cleared by review_departure_node._finish
    BEFORE this node runs, so reading it here would always be empty.  We
    therefore reconstruct the turn content from the latest AI messages
    (actor / narration / general_narration) instead.

    / 从 sessionHistory 提取本回合的角色/旁白文本。

    注意：review_departure_node._finish 在本节点运行前已清空
    directorGraphOutput，从它读取永远为空。故改为从历史中最近的
    AI 消息（actor / narration / general_narration）重建回合内容。
    """
    history = state.get("sessionHistory", [])
    if not history:
        return ""
    parts = []
    for msg in history[-8:]:
        if getattr(msg, "type", "") != "ai":
            continue
        content = getattr(msg, "content", "") or ""
        if not isinstance(content, str):
            continue
        if content.startswith("{"):
            try:
                parsed = json.loads(content)
                if parsed.get("contentType") in ("actor_response", "narration", "general_narration"):
                    content = parsed.get("content", content)
            except (ValueError, TypeError):
                pass
        if content.strip():
            parts.append(content.strip())
    return "\n\n".join(parts)


def _llm_decide(state: AgentState, scene_summary: str) -> Optional[Dict[str, Any]]:
    """Ask the LLM whether to generate an image and get the SD prompt.
    Returns a dict with generate/prompt/negative/caption, or None on failure.
    / 询问 LLM 是否生成插画并获取 SD 提示词。失败返回 None。"""
    prompt = build_node_prompt(
        "image_gen_node",
        IMAGE_GEN_PROMPT,
        context_state=state,
        env_data=fmt_env_data(state.get("sessionEnvData", {})),
        node_outputs=scene_summary,
        recent_history=fmt_history(state.get("sessionHistory", [])[-12:]),
    )
    messages = [
        {"role": "system", "content": "你是动漫插画场景分析助手，负责判断画面感并编写 SD 提示词。"},
        {"role": "user", "content": prompt},
    ]
    llm = get_llm("image_gen_node")
    params = get_node_params().get("image_gen_node", {})
    try:
        data, _raw = chat_json(llm, messages, params)
    except Exception:
        traceback.print_exc()
        logger.log_llm_error("image_gen_node")
        return None
    logger.log_llm("image_gen_node", str(data), params)
    return data if isinstance(data, dict) else None


def _persist_and_publish(state: AgentState, url: str, caption: str, prompt: str) -> None:
    """Write the scene_image history row and push an SSE message event.
    / 写入 scene_image 历史行并通过 SSE 推送消息事件。"""
    content_obj = {
        "url": url,
        "description": caption or "场景插画",
        "prompt": prompt,
        "created_at_epoch": int(time.time()),
    }
    content_str = json.dumps(content_obj, ensure_ascii=False)
    formatted = json.dumps({"contentType": SCENE_IMAGE_TYPE, "content": content_str}, ensure_ascii=False)

    session_id = state.get("sessionID", "")
    history_id = generate_history_id()
    try:
        with db_lock:
            get_db().execute(
                "INSERT INTO session_history "
                "(sessionHistoryID, parentID, role, createdBy, content, "
                "recordCreatedTime, recordUpdatedTime) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (history_id, session_id, SCENE_IMAGE_TYPE, SCENE_IMAGE_TYPE, formatted),
            )
    except Exception:
        traceback.print_exc()

    # Publish the same wrapped payload the history row stores, so live SSE and
    # page-refresh rendering go through the identical frontend parse path.
    # / 推送与历史行相同的包裹格式，实时 SSE 与刷新渲染走同一前端解析路径。
    publisher.publish(
        "message",
        {
            "sessionID": session_id,
            "contentType": SCENE_IMAGE_TYPE,
            "content": formatted,
            "role": SCENE_IMAGE_TYPE,
            "sessionHistoryID": history_id,
        },
    )


def image_gen_node(state: AgentState) -> Dict[str, Any]:
    """Entry point wired into the director subgraph review chain.
    / Director 子图审看链中注册的节点入口。"""
    logger.node_start("image_gen_node", state)
    publish_node_start(state, "image_gen_node", "考虑生成场景插画...")

    cfg = get_image_generation_config()
    session_id = state.get("sessionID", "")

    # 1) Feature toggle / / 功能开关
    if not cfg.get("enabled", False):
        publish_node_complete(state, "image_gen_node", "场景插画功能未启用")
        logger.node_end("image_gen_node", {"skipped": "disabled"})
        return {}

    # 2) Cooldown + per-session cap / / 冷却间隔 + 会话上限
    try:
        with db_lock:
            count, last_epoch = _image_stats(get_db(), session_id)
        if count >= int(cfg.get("max_per_session", 30)):
            publish_node_complete(state, "image_gen_node", f"已达会话插画上限（{count} 张）")
            logger.node_end("image_gen_node", {"skipped": "max_per_session", "count": count})
            return {}
        if last_epoch is not None and (time.time() - last_epoch) < float(cfg.get("interval_seconds", 180)):
            publish_node_complete(state, "image_gen_node", "距离上一张插画时间过近，跳过")
            logger.node_end("image_gen_node", {"skipped": "cooldown", "last_epoch": last_epoch})
            return {}
    except Exception:
        traceback.print_exc()
        logger.node_error("image_gen_node")
        publish_node_complete(state, "image_gen_node", "插画状态检查失败")
        logger.node_end("image_gen_node", {})
        return {}

    # 3) LLM judge (optional) — decides "appropriate moment" + writes the prompt
    # / 3) LLM 判定（可选）——判断"适当契机"并编写提示词
    decision: Optional[Dict[str, Any]] = None
    if cfg.get("llm_decision_enabled", True):
        # directorGraphOutput is cleared by review_departure_node before this
        # node runs → read the turn content from sessionHistory instead.
        # / directorGraphOutput 已被 review_departure_node 清空 → 改从
        #   sessionHistory 读取回合内容。
        node_outputs = _extract_turn_outputs(state)
        if not node_outputs:
            # No actor/narration output this turn → nothing visually new to draw.
            # / 本轮无角色/旁白输出 → 无新画面可画。
            publish_node_complete(state, "image_gen_node", "本轮无剧情内容，跳过插画")
            logger.node_end("image_gen_node", {"skipped": "no_outputs"})
            return {}
        decision = _llm_decide(state, node_outputs)
        if decision is None:
            publish_node_complete(state, "image_gen_node", "插画判定失败，跳过")
            logger.node_end("image_gen_node", {"skipped": "llm_failed"})
            return {}
        if not decision.get("generate"):
            publish_node_complete(state, "image_gen_node", "本轮场景不值得生成插画")
            logger.node_end("image_gen_node", {"skipped": "llm_no", "reason": decision.get("reason", "")})
            return {}
        prompt = str(decision.get("prompt", "")).strip()
        negative = str(decision.get("negative") or "").strip() or str(cfg.get("negative_prompt", ""))
        caption = str(decision.get("caption", "")).strip()
        if not prompt:
            publish_node_complete(state, "image_gen_node", "未获得有效提示词，跳过")
            logger.node_end("image_gen_node", {"skipped": "empty_prompt"})
            return {}
    else:
        # llm_decision_enabled=False → always generate with default negative.
        # / LLM 判定关闭 → 每回合都生成，用默认负面提示词。
        prompt = ""
        negative = str(cfg.get("negative_prompt", ""))
        caption = "场景插画"

    # 4) Generate via local ComfyUI / / 调用本机 ComfyUI 生成
    publish_node_start(state, "image_gen_node", "正在生成场景插画（ComfyUI）...")
    client = ComfyUIClient(str(cfg.get("comfyui_base_url", "http://127.0.0.1:8188")))
    try:
        result = client.generate(
            prompt=prompt,
            negative=negative,
            session_id=session_id,
            checkpoint=str(cfg.get("checkpoint", "animagine-xl-4.0.safetensors")),
            width=int(cfg.get("width", 896)),
            height=int(cfg.get("height", 1152)),
            steps=int(cfg.get("steps", 30)),
            cfg=float(cfg.get("cfg", 6.0)),
            sampler_name=str(cfg.get("sampler_name", "dpmpp_2m")),
            scheduler=str(cfg.get("scheduler", "karras")),
            filename_prefix="rpa_scene",
            timeout_seconds=float(cfg.get("timeout_seconds", 300)),
            poll_interval_seconds=float(cfg.get("poll_interval_seconds", 1.0)),
        )
    except ComfyUIError as e:
        logger.node_error("image_gen_node")
        logger.log_llm_error("image_gen_node")  # reuse the LLM-error log channel for visibility
        traceback.print_exc()
        publish_node_complete(state, "image_gen_node", f"插画生成失败：{e}")
        logger.node_end("image_gen_node", {"error": str(e)})
        return {}
    except Exception as e:
        logger.node_error("image_gen_node")
        traceback.print_exc()
        publish_node_complete(state, "image_gen_node", f"插画生成异常：{e}")
        logger.node_end("image_gen_node", {"error": str(e)})
        return {}

    # 5) Persist + push / / 持久化并推送
    _persist_and_publish(state, result["url"], caption, prompt)
    publish_node_complete(state, "image_gen_node", "场景插画已生成")
    logger.node_end("image_gen_node", {"url": result["url"], "seed": result.get("seed")})
    return {}
