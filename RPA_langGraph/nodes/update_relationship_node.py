import traceback
from typing import Any, Dict

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import (
    fmt_all_characters,
    fmt_all_emotion_states,
    fmt_all_relationships,
    fmt_node_outputs,
    parse_llm_json,
)
from services.relationship import RelationshipService
from SQLiteClient import db_lock, get_db

RELATIONSHIP_UPDATE_PROMPT = (
    """你是一个角色关系分析节点。
审看本轮子节点的输出，分析在场角色之间的关系变化，更新角色关系数据。

=== 当前在场角色 ===
{present_characters}

=== 已有角色关系（供参考） ===
{existing_relationships}

=== 各子节点的输出 ===
{node_outputs}

=== 各角色当前情绪 ===
{emotion_states}

请分析每个角色对其他在场角色的**单向看法**。
对于每一对角色，分别输出 A 对 B 的看法 和 B 对 A 的看法，它们可能相同也可能不同。

关系类型由你根据角色间的互动自由判断和命名，用中文描述即可，例如：挚友、死敌、暗恋对象、救命恩人、主仆、合作伙伴……

每个单向关系包含以下维度：
- relationship_type: A 视 B 为什么样的存在
- strength: 关系强度 [0~1]，越靠近1表示关系越紧密/重要
- sentiment: 情感倾向 [-1~1]，负值=敌对/厌恶，正值=友善/亲近
- power_dynamic: 权力感知 [-1~1]，负值=A觉得自己被B支配/压制，正值=A觉得自己在支配/压制B，0=平等

规则：
1. 每个角色对每个其他角色都应该输出一条单向关系
2. 如果角色间的互动很明确，A 对 B 和 B 对 A 的感觉可以不同（如 A 暗恋 B，但 B 只把 A 当朋友）
3. 用户角色（{user_character_id}）也参与关系计算（用户角色对其他角色的看法，以及其他角色对用户角色的看法）

请严格按以下 JSON 格式返回，不要包含其他内容：
{{
    "relationships": [
        {{
            "characterID_1": "从谁的角度（看法的主体）",
            "characterID_2": "关于谁（看法的对象）",
            "relationship_type": "挚友",
            "strength": 0.7,
            "sentiment": 0.6,
            "power_dynamic": -0.1
        }},
        {{
            "characterID_1": "从谁的角度",
            "characterID_2": "关于谁",
            "relationship_type": "偶像",
            "strength": 0.9,
            "sentiment": 0.8,
            "power_dynamic": -0.3
        }}
    ]
}}
"""
)

def update_relationship_node(state: AgentState) -> Dict[str, Any]:
    logger.node_start("update_relationship_node", state)

    publish_node_start(state, "update_relationship_node", "分析角色关系变化...")
    node_outputs = fmt_node_outputs(state.get("directorGraphOutput", []))
    if not node_outputs:
        return _finish(state)

    db = get_db()
    session_id = state.get("sessionID", "")
    character_ids = state.get("sessionPresentCharacter", [])
    user_char_id = state.get("sessionUserCharacterID", "")

    if len(character_ids) < 2:
        return _finish(state)

    # DB reads serialized under db_lock: review_departure_node writes in the
    # same super-step, and the shared sqlite connection cannot run concurrent
    # statements (gotcha: parallel review-chain DB access must be serialized).
    # / DB 读在 db_lock 下串行执行：本节点与 review_departure_node 同超步并行，
    #   共享 sqlite 连接不支持并发语句（并行审查链 DB 访问必须串行化）。
    with db_lock:
        emotion_states = fmt_all_emotion_states(db, session_id, character_ids)
        present_text = fmt_all_characters(db, character_ids) or "无"
        existing_relationships = fmt_all_relationships(db, session_id, character_ids)

    prompt = build_node_prompt(
        "update_relationship_node",
        RELATIONSHIP_UPDATE_PROMPT,
        context_state=state,
        present_characters=present_text,
        existing_relationships=existing_relationships,
        node_outputs=node_outputs,
        emotion_states=emotion_states,
        user_character_id=user_char_id or "无",
    )

    messages = [
        {"role": "system", "content": "你是一个剧情分析助手，负责分析角色关系变化。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("update_relationship_node")
    params = get_node_params().get("update_relationship_node", {})
    try:
        response = llm.chat(
            messages,
            temperature=params.get("temperature"),
            max_tokens=params.get("max_tokens"),
            isEnableThinking=params.get("is_enable_thinking"),
            reasoning_effort=params.get("reasoning_effort"),
            max_context_tokens=params.get("max_context_tokens"),
            response_format={"type": "json_object"},
        )
        logger.log_llm("update_relationship_node", response, params)
    except Exception:
        logger.node_error("update_relationship_node")
        traceback.print_exc()
        logger.log_llm_error("update_relationship_node")
        return _finish(state)

    relationships = _parse_relationship_response(response)

    if relationships:
        rel_service = RelationshipService(db)
        valid_ids = set(character_ids)
        if user_char_id:
            valid_ids.add(user_char_id)

        with db_lock:
            for rel in relationships:
                cid1 = rel.get("characterID_1", "")
                cid2 = rel.get("characterID_2", "")
                if cid1 not in valid_ids or cid2 not in valid_ids or cid1 == cid2:
                    continue
                rel["sessionID"] = session_id
                rel_service.upsert(rel)

    publish_node_complete(state, "update_relationship_node", "角色关系分析完毕")
    logger.node_end("update_relationship_node", {})
    return {}


def _parse_relationship_response(response: str) -> list[Dict[str, Any]]:
    data = parse_llm_json(response)
    if not isinstance(data, dict):
        return []
    rels = data.get("relationships", [])
    if not isinstance(rels, list):
        return []
    result = []
    for item in rels:
        if not isinstance(item, dict):
            continue
        rtype = str(item.get("relationship_type", "neutral"))
        result.append(
            {
                "characterID_1": str(item.get("characterID_1", "")),
                "characterID_2": str(item.get("characterID_2", "")),
                "relationship_type": rtype,
                "strength": max(0.0, min(1.0, float(item.get("strength", 0.5)))),
                "sentiment": max(-1.0, min(1.0, float(item.get("sentiment", 0.0)))),
                "power_dynamic": max(-1.0, min(1.0, float(item.get("power_dynamic", 0.0)))),
            }
        )
    return result


def _finish(state: AgentState) -> Dict[str, Any]:
    publish_node_complete(state, "update_relationship_node", "角色关系分析完毕（无数据）")
    logger.node_end("update_relationship_node", {})
    return {}
