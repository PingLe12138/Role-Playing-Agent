import json
import traceback
from typing import Any, Dict, List

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import chat_json, fmt_all_characters, parse_llm_json
from SQLiteClient import get_db
from SSEPublisher import publisher

RECALL_PROMPT = (
    """你是一个角色召回分析节点 (Recall)。
分析用户的输入，判断是否需要将已离场角色召回当前场景。

=== 用户最新输入 ===
{user_input}

=== 当前在场角色 ===
{present_characters}

=== 已离场角色（已离开场景且不会再自动出现） ===
{departed_characters}

请判断用户输入中是否在召唤上述已离场角色回归当前场景。
如果用户明确召唤了某个角色，输出该角色的 characterID；如果没有召唤任何角色，输出空列表。

请严格按以下 JSON 格式返回，不要包含其他内容：
{{"recall_ids": ["角色ID1", "角色ID2"]}}

注意：
- 只有用户明确提到要找回/召唤该角色时才算，不要主动将角色召回
- 角色可能以名称而非ID的形式出现在用户输入中，用角色信息卡中的名称做匹配
- 如果角色已在当前在场角色列表中，跳过
"""
)


def recall_node(state: AgentState) -> Dict[str, Any]:
    history = state.get("sessionHistory", [])
    if not history:
        return {}
    last_msg = history[-1]
    if last_msg.type != "human":
        return {}

    publish_node_start(state, "recall_node", "分析角色召回需求...")
    logger.node_start("recall_node", state)

    db = get_db()
    session_id = state.get("sessionID", "")
    user_char_id = state.get("sessionUserCharacterID", "")

    present_ids = state.get("sessionPresentCharacter", [])
    departed_ids = state.get("sessionDepartedCharacter", [])

    prompt = build_node_prompt(
        "recall_node",
        RECALL_PROMPT,
        context_state=state,
        user_input=last_msg.content,
        present_characters=fmt_all_characters(db, present_ids) or "无",
        departed_characters=fmt_all_characters(db, departed_ids) or "无",
    )

    messages = [
        {"role": "system", "content": "你是一个剧情分析助手，负责判断角色召回需求。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("recall_node")
    params = get_node_params().get("recall_node", {})
    try:
        _, response = chat_json(llm, messages, params)
        logger.log_llm("recall_node", response, params)
    except Exception:
        logger.node_error("recall_node")
        traceback.print_exc()
        logger.log_llm_error("recall_node")
        logger.node_end("recall_node", {})
        return {}

    recall_ids = _parse_recall_response(response)
    all_available = set(departed_ids + present_ids)
    if user_char_id:
        all_available.discard(user_char_id)
    recall_ids = [cid for cid in recall_ids if cid in all_available]
    recall_ids = [cid for cid in recall_ids if cid not in present_ids]

    updates: Dict[str, Any] = {}

    if recall_ids:
        merged = list(dict.fromkeys(present_ids + recall_ids))
        updates["sessionPresentCharacter"] = merged

        db.begin()
        try:
            departed_clean = [cid for cid in departed_ids if cid not in recall_ids]
            db.execute(
                "UPDATE session SET sessionPresentCharacter = ?, sessionDepartedCharacter = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                (json.dumps(merged, ensure_ascii=False), json.dumps(departed_clean, ensure_ascii=False), session_id),
            )
            db.commit()
        except Exception:
            db.rollback()
            traceback.print_exc()
            return {}

        publisher.publish("session_update", {"presentCharacter": merged})

    publish_node_complete(state, "recall_node", "召回分析完毕")
    logger.node_end("recall_node", updates)
    return updates


def _parse_recall_response(response: str) -> List[str]:
    data = parse_llm_json(response)
    if not isinstance(data, dict):
        return []
    ids = data.get("recall_ids", [])
    if not isinstance(ids, list):
        return []
    return [str(i) for i in ids if i]
