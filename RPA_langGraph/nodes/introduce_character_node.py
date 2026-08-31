import json
import traceback
from typing import Any, Dict, List

from ChromaDBClient import safe_get_chroma
from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.emotion import EmotionStateService, seed_initial_emotions
from services.formatters import fmt_all_characters, fmt_all_relationships, fmt_history, parse_llm_json
from services.id_utils import generate_character_id
from services.relationship import RelationshipService, seed_bidirectional_relationships
from SQLiteClient import get_db
from SSEPublisher import publisher

INTRODUCE_PROMPT = (
    """你是一个角色引入分析节点 (Introduce)。
分析用户的输入，判断用户是否在主动引入（召唤/提及/描述）新的角色进入当前场景。

=== 用户输入 ===
{user_input}

=== 最近的对话历史（用于判断代称指向） ===
{recent_history}

=== 当前在场角色 ===
{present_characters}

=== 数据库中已有的全部角色（按名称匹配） ===
{all_db_characters}

=== 现有角色关系信息（供参考） ===
{existing_relationships}

请判断用户输入中是否引入了当前不在场的角色。对于每个被引入的角色：
1. 如果该角色已存在于"当前在场角色"中 → 忽略，不输出
2. 如果该角色匹配"数据库中已有的全部角色"中的某个角色（按名称匹配）→ characterID 填入该角色的 ID，characterName 和 characterInfo 使用数据库中的值
3. 如果该角色在数据库中不存在 → characterID 留空字符串，characterName 填入角色名称，characterInfo 根据上下文生成角色描述（JSON 格式，包含多角度描述）

characterInfo 必须是一个 JSON 字符串，包含以下字段：
- "appearance": "相貌描述"
- "personality": "性格描述"
- "tone": "语气描述"
- "background": "背景描述"
- "other": "其他补充描述"

对于已在数据库中的角色（即 characterID 有值且已存在于数据库的角色），如果该角色与某个在场角色
在"现有角色关系信息"中不存在任何关系数据，请你根据角色的性格、背景信息以及场景上下文，
推断它们之间应该存在什么样的关系，并填入 relationships 字段中。
关系的维度：
- relationship_type: 关系类型（用中文描述，如"挚友""宿敌""师徒""暗恋对象"等）
- strength: 关系强度 [0~1]
- sentiment: 情感倾向 [-1~1]
- power_dynamic: 权力动态 [-1~1]

如果关系已经在"现有角色关系信息"中存在，则不需要输出该对的关系。
对于全新角色（数据库中不存在），不需要输出 relationships 字段。

请严格按以下 JSON 格式返回，不要包含其他内容：
{{"characters": [
    {{
        "characterID": "已有ID或空",
        "characterName": "名称",
        "characterInfo": "{{\\"appearance\\": \\"相貌\\", \\"personality\\": \\"性格\\", \\"tone\\": \\"语气\\", \\"background\\": \\"背景\\", \\"other\\": \\"其他\\"}}",
        "relationships": [
            {{"characterID": "在场角色的ID", "relationship_type": "挚友", "strength": 0.7, "sentiment": 0.6, "power_dynamic": 0.0}}
        ]
    }}
]}}

注意：
- 角色可能以"他/她/那个人/这位先生"等代称出现在用户输入中，结合对话历史判断是否指向已在场角色
- 如果用户输入中的角色描述明显指向某个已在场角色，不要视为新角色
- 只在用户明确引入一个新的、有名字的或明显是新的人物时才标记为引入
- 不确定时，默认不引入（不要输出该角色）
- 不要将已在当前在场角色列表中的角色重复输出
- 使用角色名称进行匹配，如果数据库中有同名的角色，视为同一角色
- relationships 中每个条目的 characterID 必须是在场角色的 ID，不能是引入角色自己的 ID
"""
)


def introduce_character_node(state: AgentState) -> Dict[str, Any]:
    history = state.get("sessionHistory", [])
    if not history:
        return {}
    last_msg = history[-1]
    if last_msg.type != "human":
        return {}

    session_id = state.get("sessionID", "")
    user_char_id = state.get("sessionUserCharacterID", "")

    publish_node_start(state, "introduce_character_node", "分析角色引入需求...")

    logger.node_start("introduce_character_node", state)

    db = get_db()
    present_ids = state.get("sessionPresentCharacter", [])

    all_db_rows = db.fetchall("SELECT * FROM character_info_card")
    all_db_characters = ""
    if all_db_rows:
        parts = []
        for r in all_db_rows:
            cid = r["characterID"]
            if user_char_id and cid == user_char_id:
                continue
            parts.append(f"角色ID: {cid}\n名称: {r['characterName']}\n信息: {r.get('characterInfo', '无')}")
        all_db_characters = "\n---\n".join(parts) if parts else "无"

    recent = fmt_history(history[-10:]) if len(history) > 1 else "(无)"
    existing_relationships = fmt_all_relationships(db, session_id, present_ids)
    prompt = build_node_prompt(
        "introduce_character_node",
        INTRODUCE_PROMPT,
        context_state=state,
        user_input=last_msg.content,
        recent_history=recent,
        present_characters=fmt_all_characters(db, present_ids) or "无",
        all_db_characters=all_db_characters,
        existing_relationships=existing_relationships,
    )

    messages = [
        {"role": "system", "content": "你是一个角色引入分析助手，负责识别用户是否引入了新角色。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("introduce_character_node")
    params = get_node_params().get("introduce_character_node", {})
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
        logger.log_llm("introduce_character_node", response, params)
    except Exception:
        logger.node_error("introduce_character_node")
        traceback.print_exc()
        logger.log_llm_error("introduce_character_node")
        publish_node_complete(state, "introduce_character_node", "分析失败")
        logger.node_end("introduce_character_node", {})
        return {}

    result = _parse_introduce_response(response)
    existing_ids = set(present_ids)

    resolved_new: List[Dict[str, Any]] = []
    for char_data in result:
        cid = char_data.get("characterID", "").strip()
        cname = char_data.get("characterName", "").strip()
        cinfo = char_data.get("characterInfo", "").strip()

        if not cname:
            continue

        if cid and cid in existing_ids:
            continue

        if not cid or not db.fetchone("SELECT 1 FROM character_info_card WHERE characterID = ?", (cid,)):
            cid = generate_character_id(cname)

        resolved_new.append(
            {
                "characterID": cid,
                "characterName": cname,
                "characterInfo": cinfo,
                "relationships": char_data.get("relationships", []),
            }
        )

    new_ids = [item["characterID"] for item in resolved_new]
    new_ids_to_create = [
        item
        for item in resolved_new
        if not db.fetchone("SELECT 1 FROM character_info_card WHERE characterID = ?", (item["characterID"],))
    ]
    new_ids_set = {item["characterID"] for item in new_ids_to_create}

    updates: Dict[str, Any] = {}

    if new_ids:
        merged = list(dict.fromkeys(present_ids + new_ids))

        db.begin()
        try:
            for item in new_ids_to_create:
                db.execute(
                    "INSERT INTO character_info_card "
                    "(characterID, characterName, characterInfo, recordCreatedTime, recordUpdatedTime) "
                    "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                    (item["characterID"], item["characterName"], item["characterInfo"]),
                )
            db.execute(
                "UPDATE session SET sessionPresentCharacter = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                (json.dumps(merged, ensure_ascii=False), session_id),
            )
            db.commit()
        except Exception:
            db.rollback()
            traceback.print_exc()
            publish_node_complete(state, "introduce_character_node", "更新失败")
            logger.node_end("introduce_character_node", {})
            return {}

        try:
            chroma = safe_get_chroma()
            if chroma:
                for cid in new_ids:
                    chroma.get_or_create_collection(f"session_{session_id}_memory_{cid}")
        except Exception:
            pass

        if session_id:
            rel_service = RelationshipService(db)
            before_ids = [cid for cid in present_ids if cid not in set(new_ids)]

            # Load defaultRelationships presets from the cards of re-introduced
            # pre-existing characters (those in resolved_new but NOT brand-new).
            # / 仅从复用老角色的角色卡加载 defaultRelationships 预设。
            default_map: Dict[str, List[Dict[str, Any]]] = {}
            for item in resolved_new:
                if item["characterID"] not in new_ids_set:
                    row = db.fetchone(
                        "SELECT defaultRelationships FROM character_info_card WHERE characterID = ?",
                        (item["characterID"],),
                    )
                    if row and row["defaultRelationships"]:
                        try:
                            default_map[item["characterID"]] = json.loads(row["defaultRelationships"])
                        except Exception:
                            pass

            # Create bidirectional relationships; brand-new characters get the
            # "初次见面" default, re-introduced ones use card presets when present.
            # / 双向补建关系：全新角色用"初次见面"默认，复用老角色用卡内预设。
            seed_bidirectional_relationships(
                rel_service,
                session_id,
                new_ids,
                before_ids,
                default_map=default_map,
                brand_new_ids=new_ids_set,
            )

            # Seed initial emotion snapshots from each character's card.
            # / 从角色卡写入初始情绪快照。
            emotion_svc = EmotionStateService(db)
            seed_initial_emotions(emotion_svc, db, session_id, new_ids, trigger_summary="角色登场")

        updates["sessionPresentCharacter"] = merged

        publisher.publish("session_update", {"presentCharacter": merged})

    publish_node_complete(state, "introduce_character_node", "角色引入分析完毕")

    logger.node_end("introduce_character_node", updates)
    return updates


def _parse_introduce_response(response: str) -> List[Dict[str, Any]]:
    data = parse_llm_json(response)
    if not isinstance(data, dict):
        return []
    chars = data.get("characters", [])
    if not isinstance(chars, list):
        return []
    result = []
    for c in chars:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("characterID", "") or "")
        cname = str(c.get("characterName", "") or "")
        cinfo = str(c.get("characterInfo", "") or "")
        if not cname:
            continue
        rels_raw = c.get("relationships", [])
        rels = []
        if isinstance(rels_raw, list):
            for r in rels_raw:
                if not isinstance(r, dict):
                    continue
                rid = r.get("characterID", "")
                if not rid:
                    continue
                rels.append(
                    {
                        "characterID": str(rid),
                        "relationship_type": str(r.get("relationship_type", "neutral")),
                        "strength": max(0.0, min(1.0, float(r.get("strength", 0.5)))),
                        "sentiment": max(-1.0, min(1.0, float(r.get("sentiment", 0.0)))),
                        "power_dynamic": max(-1.0, min(1.0, float(r.get("power_dynamic", 0.0)))),
                    }
                )
        result.append({"characterID": cid, "characterName": cname, "characterInfo": cinfo, "relationships": rels})
    return result
