import json
import traceback
from typing import Any, Dict, List

from ChromaDBClient import safe_get_chroma
from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import fmt_env_data, fmt_node_outputs, parse_llm_json
from services.id_utils import generate_character_id
from services.relationship import RelationshipService, seed_bidirectional_relationships
from SQLiteClient import db_lock, get_db
from SSEPublisher import publisher

CHARACTER_REVIEW_PROMPT = (
    """你是一个角色分析节点。
审看子节点的输出，判断是否有新角色出现、已知角色回归、或角色离开场景。

=== 本轮执行前的在场角色 ===
{previous_characters}

=== 已离场角色（之前已离开场景且不会再自动出现的角色） ===
{departed_characters}

=== 用户角色（不计入新角色检测） ===
{user_character_id}

=== 本轮执行前的环境 ===
{previous_env}

=== 各子节点的输出 ===
{node_outputs}

请判断：
1. 是否有新人物出现？如果有，请生成每个人物的角色信息卡（characterID/characterName/characterInfo）。
2. 是否有已离场角色回归？如果有，使用该角色原有的 characterID 填入 new_characters。
3. 是否有角色离开场景？如果有，列出离开角色的 characterID。

characterInfo 必须是一个 JSON 字符串，包含以下字段：
- "appearance": "相貌描述（外貌、衣着、身材等）"
- "personality": "性格描述（性格特点、行为习惯等）"
- "tone": "语气描述（说话方式、语调特点等）"
- "background": "背景描述（身世、经历等）"
- "other": "其他补充描述"

请严格按以下 JSON 格式返回，不要包含其他内容：
{{
    "new_characters": [
        {{"characterID": "唯一ID", "characterName": "名称", "characterInfo": "{{\\"appearance\\": \\"相貌\\", \\"personality\\": \\"性格\\", \\"tone\\": \\"语气\\", \\"background\\": \\"背景\\", \\"other\\": \\"其他\\"}}"}}
    ],
    "departed_characters": ["角色ID1", "角色ID2"]
}}

注意：
- 用户角色 "{user_character_id}" 是玩家角色，不计入新角色检测，也不计入离开角色检测
- 新角色出现和已离场角色回归都填入 new_characters 字段，回归角色必须使用原有的 characterID
- departed_characters 中只包含本轮离开场景的角色，不包括之前已离场的角色
"""
)


def review_character_node(state: AgentState) -> Dict[str, Any]:
    character_ids = state.get("sessionPresentCharacter", [])

    logger.node_start("review_character_node", state)

    publish_node_start(state, "review_character_node", "分析角色变化...")

    node_outputs = fmt_node_outputs(state.get("directorGraphOutput", []))
    if not node_outputs:
        return _handle_no_output(state)

    db = get_db()
    chroma = safe_get_chroma()
    user_char_id = state.get("sessionUserCharacterID", "") or "无"
    departed_ids = state.get("sessionDepartedCharacter", [])

    # DB reads serialized under db_lock: review_env_node starts in the same
    # super-step, and the shared sqlite connection cannot run concurrent
    # statements.
    # / DB 读在 db_lock 下串行执行：review_env_node 与本节点同超步启动，
    #   共享 sqlite 连接不支持并发语句。
    with db_lock:
        previous_characters = _fmt_character_ids(character_ids, db)
        departed_characters = _fmt_character_ids(departed_ids, db) if departed_ids else "无"

    prompt = build_node_prompt(
        "review_character_node",
        CHARACTER_REVIEW_PROMPT,
        context_state=state,
        previous_characters=previous_characters,
        departed_characters=departed_characters,
        user_character_id=user_char_id,
        previous_env=fmt_env_data(state.get("sessionEnvData", {})),
        node_outputs=node_outputs,
    )

    messages = [
        {"role": "system", "content": "你是一个剧情分析助手，负责识别角色变化。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("review_character_node")
    params = get_node_params().get("review_character_node", {})
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
        logger.log_llm("review_character_node", response, params)
    except Exception:
        logger.node_error("review_character_node")
        traceback.print_exc()
        logger.log_llm_error("review_character_node")
        return _handle_no_output(state)

    result = _parse_char_response(response)
    existing_ids = set(character_ids)
    result["new_characters"] = [
        c for c in result.get("new_characters", []) if c.get("characterID", "") not in existing_ids
    ]
    updates: Dict[str, Any] = {}

    resolved_new = []
    with db_lock:
        for char_data in result.get("new_characters", []):
            cname = char_data.get("characterName", "")
            cinfo = char_data.get("characterInfo", "")
            if not cname:
                continue
            existing = db.fetchone("SELECT characterID FROM character_info_card WHERE characterName = ?", (cname,))
            if existing:
                cid = existing["characterID"]
            else:
                cid = char_data.get("characterID", "") or generate_character_id(cname)
                if not cid:
                    continue
            resolved_new.append({"characterID": cid, "characterName": cname, "characterInfo": cinfo})

    new_ids = [item["characterID"] for item in resolved_new]

    departed_ids_out = [cid for cid in result.get("departed_characters", []) if cid and cid in existing_ids]

    session_update_data = {}

    if new_ids or departed_ids_out:
        current_set = set(character_ids)
        final_ids = list(current_set | set(new_ids) - set(departed_ids_out))
        session_update_data["presentCharacter"] = final_ids

        # The whole DB section runs under db_lock: review_env_node now starts
        # in the same super-step, so an open transaction here would otherwise
        # swallow the sibling node's autocommit statements (gotcha: parallel
        # review-chain writes must be serialized).
        # / 整个 DB 段在 db_lock 下执行：review_env_node 现与本节点同超步启动，
        #   若此处打开事务而不加锁，会吞掉兄弟节点的自动提交语句（并行审查链
        #   写入必须串行化）。
        with db_lock:
            db.begin()
            try:
                for item in resolved_new:
                    cid = item["characterID"]
                    cname = item["characterName"]
                    cinfo = item["characterInfo"]
                    if not db.fetchone("SELECT 1 FROM character_info_card WHERE characterID = ?", (cid,)):
                        db.execute(
                            "INSERT INTO character_info_card "
                            "(characterID, characterName, characterInfo, recordCreatedTime, recordUpdatedTime) "
                            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                            (cid, cname, cinfo),
                        )
                db.execute(
                    "UPDATE session SET sessionPresentCharacter = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                    (json.dumps(final_ids, ensure_ascii=False), state.get("sessionID", "")),
                )
                db.commit()
            except Exception:
                db.rollback()
                traceback.print_exc()
                return _handle_no_output(state)

            for cid in new_ids:
                try:
                    chroma.get_or_create_collection(f"session_{state.get('sessionID', '')}_memory_{cid}")
                except Exception:
                    pass

            session_id = state.get("sessionID", "")
            if new_ids and session_id:
                rel_service = RelationshipService(db)
                before_ids = [cid for cid in character_ids if cid not in set(new_ids)]
                # review_character_node gives every newly-arrived character the
                # "初次见面" default (no card-preset lookup, unlike introduce_node).
                # / review_character_node 对所有新角色一律用"初次见面"（不查角色卡预设，与 introduce 不同）。
                seed_bidirectional_relationships(
                    rel_service,
                    session_id,
                    new_ids,
                    before_ids,
                    brand_new_ids=set(new_ids),
                )

        updates["sessionPresentCharacter"] = final_ids
        updates["pendingDepartedIDs"] = departed_ids_out

    if session_update_data:
        publisher.publish("session_update", session_update_data)

    publish_node_complete(state, "review_character_node", "角色分析完毕")

    logger.node_end("review_character_node", updates)
    return updates


def _handle_no_output(state: AgentState) -> Dict[str, Any]:
    return {}


def _fmt_character_ids(character_ids: List[str], db=None) -> str:
    if not character_ids:
        return "无"
    if db:
        parts = []
        for cid in character_ids:
            row = db.fetchone("SELECT characterName FROM character_info_card WHERE characterID = ?", (cid,))
            name = row["characterName"] if row else cid
            parts.append(f"- {cid} ({name})")
        return "\n".join(parts)
    return "\n".join(f"- {cid}" for cid in character_ids)


def _parse_char_response(response: str) -> Dict[str, Any]:
    data = parse_llm_json(response)
    if not isinstance(data, dict):
        return {"new_characters": [], "departed_characters": []}
    return {
        "new_characters": data.get("new_characters", []),
        "departed_characters": data.get("departed_characters", []),
    }
