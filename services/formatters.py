import json
import re
from typing import Any, Dict, List, Optional, Union

from langchain_core.messages import BaseMessage

from SQLiteClient import SQLiteClient


def fmt_history(history: List[BaseMessage]) -> str:
    lines = []
    for msg in history:
        role = msg.type
        content = msg.content
        if isinstance(content, str) and content.startswith("{"):
            try:
                parsed = json.loads(content)
                if "contentType" in parsed and "content" in parsed:
                    content = parsed["content"]
            except json.JSONDecodeError:
                pass
        lines.append(f"[{role}]\n{content}")
    return "\n\n".join(lines)


def _fmt_character_info(info: str) -> str:
    if not info:
        return "无"
    info = info.strip()
    if not info.startswith("{"):
        return info
    try:
        obj = json.loads(info)
        if not isinstance(obj, dict):
            return info
        LABEL_MAP = {"appearance": "相貌", "personality": "性格", "tone": "语气", "background": "背景", "other": "其他"}
        lines = []
        for k, v in obj.items():
            if v:
                label = LABEL_MAP.get(k, k)
                lines.append(f"【{label}】{v}")
        return "\n".join(lines) if lines else "无"
    except (json.JSONDecodeError, TypeError):
        return info


def fmt_all_characters(db: SQLiteClient, character_ids: List[str]) -> str:
    if not character_ids:
        return "无"
    placeholders = ",".join("?" * len(character_ids))
    rows = db.fetchall(f"SELECT * FROM character_info_card WHERE characterID IN ({placeholders})", tuple(character_ids))
    parts = []
    for r in rows:
        info = _fmt_character_info(r.get("characterInfo", ""))
        parts.append(f"角色ID: {r['characterID']}\n名称: {r['characterName']}\n信息: {info}")
    return "\n---\n".join(parts)


def fmt_user_character(db: SQLiteClient, user_character_id: str = "") -> str:
    if user_character_id:
        row = db.fetchone("SELECT * FROM user_character_info_card WHERE userCharacterID = ?", (user_character_id,))
    else:
        row = db.fetchone("SELECT * FROM user_character_info_card LIMIT 1")
    if not row:
        return "无"
    info = _fmt_character_info(row.get("userCharacterInfo", ""))
    return f"用户角色ID: {row['userCharacterID']}\n名称: {row['userCharacterName']}\n信息: {info}"


def fmt_env_data(env_data: Dict[str, Any]) -> str:
    return (
        f"地点: {env_data.get('location', '未知')}\n"
        f"时间: {env_data.get('time', '未知')}\n"
        f"氛围: {env_data.get('atmosphere', '未知')}"
    )


def fmt_worldview_all(db: SQLiteClient, worldview_collection_id: str) -> str:
    if not worldview_collection_id:
        return "无"
    rows = db.fetchall("SELECT * FROM worldview_entry WHERE parentID = ?", (worldview_collection_id,))
    if not rows:
        return "无"
    return "\n".join(r.get("worldviewCollectionEntryContent", "无") for r in rows)


def fmt_all_memories(db: SQLiteClient, session_id: str, character_ids: List[str]) -> str:
    if not character_ids:
        return "无"
    placeholders = ",".join("?" * len(character_ids))
    params = [session_id] + list(character_ids)
    rows = db.fetchall(
        f"SELECT characterID, content FROM memory WHERE sessionID = ? AND characterID IN ({placeholders})", params
    )
    if not rows:
        return "无"
    parts = []
    for r in rows:
        parts.append(f"[角色 {r['characterID']} 的记忆]\n{r.get('content', '无')}")
    return "\n---\n".join(parts)


def fmt_all_relationships(db: SQLiteClient, session_id: str, character_ids: list[str]) -> str:
    if not character_ids or len(character_ids) < 2:
        return "无"
    placeholders = ",".join("?" * len(character_ids))
    params = tuple(character_ids + character_ids)
    rows = db.fetchall(
        f"SELECT cr.*, c1.characterName AS sourceName, c2.characterName AS targetName "
        f"FROM character_relationship cr "
        f"LEFT JOIN character_info_card c1 ON cr.characterID_1 = c1.characterID "
        f"LEFT JOIN character_info_card c2 ON cr.characterID_2 = c2.characterID "
        f"WHERE cr.sessionID = ? AND cr.characterID_1 IN ({placeholders}) AND cr.characterID_2 IN ({placeholders})",
        (session_id,) + params,
    )
    if not rows:
        return "无"
    parts = []
    for r in rows:
        c1 = r["characterID_1"]
        c2 = r["characterID_2"]
        n1 = r["sourceName"] or c1
        n2 = r["targetName"] or c2
        t = r.get("relationship_type", "neutral")
        s = r.get("strength", 0.5)
        em = r.get("sentiment", 0.0)
        pw = r.get("power_dynamic", 0.0)
        parts.append(f"[{n1}] ⟶ [{n2}]: {t} | 强度 {s:.1f} | 情感 {em:+.1f} | 权力感 {pw:+.1f}")
    if not parts:
        return "无"
    return "\n".join(parts)


def fmt_node_outputs(state_outputs: List[Dict[str, Any]]) -> str:
    outputs = state_outputs or []
    if not outputs:
        return ""
    parts = []
    for item in outputs:
        node = item.get("node", "unknown")
        if node == "actor_node":
            parts.append(
                f"[actor 扮演 {item.get('character', '?')}]\n"
                f"动作: {item.get('action', '')}\n"
                f"心理: {item.get('inner_thought', '')}\n"
                f"对话: {item.get('speech', '')}"
            )
        elif node == "narration_node":
            parts.append(f"[narration 旁白]\n{item.get('result', '')}")
        elif node == "outline_node":
            parts.append(f"[outline 总结]\n{item.get('result', '')}")
        else:
            parts.append(f"[{node}]\n{item}")
    return "\n\n===\n\n".join(parts)


# LLM 输出常见瑕疵：多行 JSON 的最后一个元素后会残留尾逗号（",]" / ",}"），
# json.loads 会报 "Illegal trailing comma"。该正则只删除紧跟 ] 或 } 前的逗号。
_TRAILING_COMMA_RE = re.compile(r",\s*([\]\}])")


def parse_llm_json(response: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
    response = response.strip()
    if response.startswith("\ufeff"):
        response = response.strip("\ufeff").strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[-1]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

    # 优先按原样解析；失败后再尝试清洗尾逗号后的版本（不改变绝大多数正常响应）。
    cleaned = _TRAILING_COMMA_RE.sub(r"\1", response)
    for cand in (response, cleaned):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue

    # 从包裹文本中截取首个 {…} 或 […] 区域（对清洗后的文本截取，保留尾逗号容错）。
    for delim_start, delim_end in [("{", "}"), ("[", "]")]:
        start = cleaned.find(delim_start)
        end = cleaned.rfind(delim_end)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue

    return None


RETRY_FIX_PROMPT = (
    "上一条回复不是合法的 JSON。请重新输出，仅输出一个合法 JSON，不要包含任何解释、思考过程或多余文字。"
)


def chat_json(llm, messages, params=None, retries=1):
    """Call the LLM requesting JSON, retrying once with a corrective prompt if
    the response cannot be parsed. Returns (parsed_data_or_None, raw_response).
    / 请求 JSON 输出；解析失败时附带修正提示重试。返回 (解析结果或 None, 原始响应)。"""
    params = params or {}
    msgs = list(messages)
    last_raw = ""
    for _ in range(retries + 1):
        last_raw = llm.chat(
            msgs,
            temperature=params.get("temperature"),
            max_tokens=params.get("max_tokens"),
            isEnableThinking=params.get("is_enable_thinking"),
            reasoning_effort=params.get("reasoning_effort"),
            max_context_tokens=params.get("max_context_tokens"),
            response_format={"type": "json_object"},
        )
        data = parse_llm_json(last_raw)
        if data is not None:
            return data, last_raw
        msgs = list(msgs) + [{"role": "user", "content": RETRY_FIX_PROMPT}]
    return None, last_raw


def fmt_emotion_state(db: SQLiteClient, session_id: str, character_id: str) -> str:
    row = db.fetchone(
        "SELECT * FROM character_emotion_state WHERE sessionID = ? AND characterID = ? "
        "ORDER BY recordCreatedTime DESC LIMIT 1",
        (session_id, character_id),
    )
    if not row:
        return "无"
    return (
        f"当前情绪：{row['emotionLabel'] or '未知'}\n"
        f"效价：{row['valence']} | 唤醒度：{row['arousal']} | 强度：{row['intensity']}\n"
        f"精力：{row['energy']} | 压力：{row['stress']}"
    )


def fmt_all_emotion_states(db: SQLiteClient, session_id: str, character_ids: list[str]) -> str:
    parts = []
    for cid in character_ids:
        row = db.fetchone(
            "SELECT * FROM character_emotion_state WHERE sessionID = ? AND characterID = ? "
            "ORDER BY recordCreatedTime DESC LIMIT 1",
            (session_id, cid),
        )
        if not row:
            continue
        name_row = db.fetchone("SELECT characterName FROM character_info_card WHERE characterID = ?", (cid,))
        name = name_row["characterName"] if name_row else cid
        parts.append(
            f"【{name}】\n"
            f"情绪：{row['emotionLabel'] or '未知'} | 效价：{row['valence']} | "
            f"唤醒度：{row['arousal']} | 强度：{row['intensity']}\n"
            f"精力：{row['energy']} | 压力：{row['stress']}"
        )
    return "\n\n".join(parts) if parts else "无"
