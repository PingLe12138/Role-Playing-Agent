"""Context block registry for configurable per-node prompt injection.

Every node prompt template keeps its original `=== 标题 ===` / `{placeholder}`
section structure.  At prompt-build time, config_loader.apply_context_config()
walks the template sections, maps each placeholder to a context block id,
then filters / reorders / appends sections according to the per-node
`node_contexts` configuration (defaultconfig.json / config.json).

Blocks not present in the template (user-added via the config UI) are
rendered here by the matching render function.

/ 上下文块注册表，支撑可配置的逐节点提示词注入。节点模板保留原有节结构；
  构建提示词时由 config_loader.apply_context_config 按节点上下文配置过滤/
  重排/追加节。模板中不存在的新增块由对应渲染函数在此渲染。
"""

from typing import Any, Dict, List, Optional

from ChromaDBClient import safe_get_chroma
from services.formatters import (
    fmt_all_characters,
    fmt_all_emotion_states,
    fmt_all_memories,
    fmt_all_relationships,
    fmt_emotion_state,
    fmt_env_data,
    fmt_history,
    fmt_node_outputs,
    fmt_user_character,
    fmt_worldview_all,
)
from SQLiteClient import get_db

# ── placeholder → block id overrides per node ─────────────────────────
# 占位符名与块 id 大多一致；此表处理各节点的特殊占位符。
PLACEHOLDER_BLOCK_OVERRIDES: Dict[str, Dict[str, str]] = {
    "director_node": {"characters": "character_cards", "departed": "departed_characters"},
    "actor_node": {
        "user_character_card": "user_character",
        "worldview_entries": "worldview_retrieval",
        "memories": "memories_retrieval",
    },
    "outline_node": {"existing_outline": "outline"},
    "review_env_node": {"previous_env": "env"},
    "review_character_node": {
        "departed_characters": "previous_departed_characters",
        "previous_env": "env",
    },
    "update_relationship_node": {
        "present_characters": "character_cards",
        "existing_relationships": "relationships",
    },
    "introduce_character_node": {"existing_relationships": "relationships"},
    "player_choice_node": {"characters": "character_cards"},
    "player_choice_process": {"characters": "character_cards"},
}

# Global placeholder aliases: placeholder names that differ from their
# block id across several nodes.
# / 全局占位符别名：多个节点中占位符名与块 id 不同的通用映射。
PLACEHOLDER_ALIASES: Dict[str, str] = {
    "env_data": "env",
    "existing_relationships": "relationships",
    "existing_outline": "outline",
    "worldview_entries": "worldview",
}

# Task-parameter placeholders stay in the template body and are never
# managed as context blocks.
# / 任务参数占位符保留在模板正文中，不归上下文块管理。
TASK_PARAM_PLACEHOLDERS = {
    "user_input",
    "instructions",
    "context",
    "choices_text",
    "player_choice",
    "character_name",
    "user_character_id",
}


def block_id_for(node_name: str, placeholder: str) -> Optional[str]:
    if placeholder in TASK_PARAM_PLACEHOLDERS:
        return None
    if node_name in PLACEHOLDER_BLOCK_OVERRIDES and placeholder in PLACEHOLDER_BLOCK_OVERRIDES[node_name]:
        return PLACEHOLDER_BLOCK_OVERRIDES[node_name][placeholder]
    if placeholder in PLACEHOLDER_ALIASES:
        return PLACEHOLDER_ALIASES[placeholder]
    return placeholder


# ── render functions ──────────────────────────────────────────────────
# 渲染函数签名统一为 render(state, extra, args) -> str；db/chroma 使用全局单例。


def _query_worldview(chroma, session_id, worldview_collection_id, query_text, top_k=5):
    if not chroma or not session_id or not worldview_collection_id:
        return []
    collection_name = f"session_{session_id}_worldviewentry_{worldview_collection_id}"
    try:
        results = chroma.query(collection_name, query_texts=[query_text], n_results=top_k)
        docs = results.get("documents", [[]])[0]
        return docs if docs else []
    except Exception:
        return []


def _query_memories(chroma, session_id, character_id, query_text, top_k=5):
    if not chroma or not session_id or not character_id:
        return []
    collection_name = f"session_{session_id}_memory_{character_id}"
    try:
        results = chroma.query(collection_name, query_texts=[query_text], n_results=top_k)
        docs = results.get("documents", [[]])[0]
        return docs if docs else []
    except Exception:
        return []


def _fmt_character_ids(db, ids, none_text='无'):
    # review_character_node 的轻量 ID+名字 行格式
    if not ids:
        return none_text
    parts = []
    for cid in ids:
        row = db.fetchone("SELECT characterName FROM character_info_card WHERE characterID = ?", (cid,))
        name = row["characterName"] if row else cid
        parts.append(f"- {cid} ({name})")
    return "\n".join(parts)


def render_history(state, extra, args):
    return fmt_history(state.get("sessionHistory", []))


def render_recent_history(state, extra, args):
    # introduce 语义：除最新一条用户输入外的最近 10 条
    history = state.get("sessionHistory", [])
    if len(history) <= 1:
        return "无"
    return fmt_history(history[:-1][-10:])


def render_env(state, extra, args):
    return fmt_env_data(state.get("sessionEnvData", {}))


def render_outline(state, extra, args):
    return "\n".join(state.get("outline", [])[-50:])


def render_node_outputs(state, extra, args):
    return fmt_node_outputs(state.get("directorGraphOutput", []))


def render_todo_list(state, extra, args):
    todo_list = state.get("directorToDoList", [])
    if not todo_list:
        return "(空)"
    return "\n".join(
        f"- {{targetNode: {t['targetNode']}, isCompleted: {t['isCompleted']}, extraData: {t['extraData']}}}"
        for t in todo_list
    )


def render_character_cards(state, extra, args):
    db = get_db()
    return fmt_all_characters(db, state.get("sessionPresentCharacter", [])) or "无"


def render_character_card(state, extra, args):
    db = get_db()
    character_id = (extra or {}).get("character_id", "")
    if not character_id:
        return "无"
    row = db.fetchone("SELECT * FROM character_info_card WHERE characterID = ?", (character_id,))
    if not row:
        return "无"
    if (args or {}).get('brief'):
        return f"名称: {row.get('characterName', '')}\n信息: {row.get('characterInfo', '无')}"
    return f"角色ID: {row['characterID']}\n名称: {row['characterName']}\n信息: {row.get('characterInfo', '无')}"


def render_user_character(state, extra, args):
    db = get_db()
    return fmt_user_character(db, state.get("sessionUserCharacterID", ""))


def render_present_characters(state, extra, args):
    db = get_db()
    return fmt_all_characters(db, state.get("sessionPresentCharacter", [])) or "无"


def render_departed_characters(state, extra, args):
    db = get_db()
    return fmt_all_characters(db, state.get("sessionDepartedCharacter", [])) or "无"


def render_all_db_characters(state, extra, args):
    db = get_db()
    user_char_id = state.get("sessionUserCharacterID", "")
    rows = db.fetchall("SELECT * FROM character_info_card")
    if not rows:
        return "无"
    parts = []
    for r in rows:
        cid = r["characterID"]
        if user_char_id and cid == user_char_id:
            continue
        parts.append(f"角色ID: {cid}\n名称: {r['characterName']}\n信息: {r.get('characterInfo', '无')}")
    return "\n---\n".join(parts) if parts else "无"


def render_worldview(state, extra, args):
    db = get_db()
    return fmt_worldview_all(db, state.get("sessionWorldviewCollectionID", ""))


def render_worldview_retrieval(state, extra, args):
    chroma = safe_get_chroma()
    history_text = fmt_history(state.get("sessionHistory", []))
    docs = _query_worldview(
        chroma, state.get("sessionID", ""), state.get("sessionWorldviewCollectionID", ""), history_text
    )
    return "\n".join(docs) if docs else "无"


def render_permanent_worldview(state, extra, args):
    db = get_db()
    wvc = state.get("sessionWorldviewCollectionID", "")
    if not wvc:
        return ""
    rows = db.fetchall(
        "SELECT worldviewCollectionEntryContent FROM worldview_entry WHERE parentID = ? AND isPermanent = 1",
        (wvc,),
    )
    if not rows:
        return ""
    return "\n".join(r.get("worldviewCollectionEntryContent", "") for r in rows)


def render_memories(state, extra, args):
    db = get_db()
    return fmt_all_memories(db, state.get("sessionID", ""), state.get("sessionPresentCharacter", []))


def render_memories_retrieval(state, extra, args):
    chroma = safe_get_chroma()
    character_id = (extra or {}).get("character_id", "")
    history_text = fmt_history(state.get("sessionHistory", []))
    docs = _query_memories(chroma, state.get("sessionID", ""), character_id, history_text)
    return "\n".join(docs) if docs else "无"


def render_existing_memories(state, extra, args):
    db = get_db()
    character_id = (extra or {}).get("character_id", "")
    rows = db.fetchall(
        "SELECT content FROM memory WHERE sessionID = ? AND characterID = ?",
        (state.get("sessionID", ""), character_id),
    )
    return "\n".join(r["content"] for r in rows)


def render_relationships(state, extra, args):
    db = get_db()
    return fmt_all_relationships(db, state.get("sessionID", ""), state.get("sessionPresentCharacter", []))


def render_emotion_state(state, extra, args):
    db = get_db()
    character_id = (extra or {}).get("character_id", "")
    return fmt_emotion_state(db, state.get("sessionID", ""), character_id)


def render_emotion_states(state, extra, args):
    db = get_db()
    return fmt_all_emotion_states(db, state.get("sessionID", ""), state.get("sessionPresentCharacter", []))


def render_previous_characters(state, extra, args):
    db = get_db()
    return _fmt_character_ids(db, state.get("sessionPresentCharacter", []))


def render_previous_departed_characters(state, extra, args):
    db = get_db()
    return _fmt_character_ids(db, state.get("sessionDepartedCharacter", []))


CONTEXT_BLOCKS: Dict[str, Dict[str, Any]] = {
    "history": {"title": "对话历史", "render": render_history, "desc": "对话历史（state）"},
    "recent_history": {"title": "近期对话", "render": render_recent_history, "desc": "最近对话（state，截断）"},
    "env": {"title": "当前环境", "render": render_env, "desc": "场景环境（地点/时间/氛围）"},
    "outline": {"title": "剧情大纲", "render": render_outline, "desc": "已有剧情大纲片段"},
    "node_outputs": {"title": "本轮节点输出", "render": render_node_outputs, "desc": "本轮各子节点输出"},
    "todo_list": {"title": "待办事项", "render": render_todo_list, "desc": "当前 TODO 列表"},
    "character_cards": {"title": "在场角色卡", "render": render_character_cards, "desc": "在场角色信息卡（SQLite）"},
    "character_card": {"title": "角色信息", "render": render_character_card, "desc": "指定角色卡（actor/memory，SQLite）"},
    "user_character": {"title": "用户角色信息", "render": render_user_character, "desc": "用户角色卡（SQLite）"},
    "present_characters": {"title": "在场角色", "render": render_present_characters, "desc": "在场角色（SQLite）"},
    "departed_characters": {"title": "已离场角色", "render": render_departed_characters, "desc": "已离场角色（SQLite）"},
    "all_db_characters": {"title": "全部已存角色", "render": render_all_db_characters, "desc": "数据库中全部角色（introduce 专用）"},
    "worldview": {"title": "世界观设定", "render": render_worldview, "desc": "世界观条目（SQLite 全量）"},
    "worldview_retrieval": {"title": "相关世界观条目", "render": render_worldview_retrieval, "desc": "世界观条目（Chroma 向量检索 top5）"},
    "permanent_worldview": {"title": "常驻世界观设定", "render": render_permanent_worldview, "desc": "常驻世界观条目（SQLite）"},
    "memories": {"title": "角色记忆", "render": render_memories, "desc": "在场角色记忆（SQLite 全量）"},
    "memories_retrieval": {"title": "相关记忆", "render": render_memories_retrieval, "desc": "角色记忆（Chroma 向量检索 top5）"},
    "existing_memories": {"title": "已有记忆", "render": render_existing_memories, "desc": "单角色已有记忆（memory 节点）"},
    "relationships": {"title": "角色关系", "render": render_relationships, "desc": "角色关系图谱（SQLite）"},
    "emotion_state": {"title": "角色当前情绪", "render": render_emotion_state, "desc": "单角色情绪快照（SQLite）"},
    "emotion_states": {"title": "在场角色情绪", "render": render_emotion_states, "desc": "在场角色情绪（SQLite）"},
    "previous_characters": {"title": "本轮执行前的在场角色", "render": render_previous_characters, "desc": "审查前在场角色名单"},
    "previous_departed_characters": {"title": "已离场角色", "render": render_previous_departed_characters, "desc": "审查前已离场角色名单"},
}


def render_new_context_blocks(
    cfg: List[Dict[str, Any]], existing_ids: set, state: Optional[dict], extra: Optional[dict]
) -> List[str]:
    """Render context blocks from cfg that have no matching section in the
    template (user-added blocks).  Returns rendered section strings.

    / 渲染配置中存在但模板中没有对应节的新增块，返回节文本列表。
    """
    out: List[str] = []
    for item in cfg:
        if isinstance(item, str):
            item = {"id": item}
        bid = item.get("id", "")
        if bid in existing_ids:
            continue
        if item.get('enabled', True) is False:
            continue
        block = CONTEXT_BLOCKS.get(bid)
        if not block:
            continue
        title = item.get('title') or block['title']
        content = block['render'](state or {}, extra or {}, item.get('args') or {})
        out.append(f"=== {title} ===\n{content}")
    return out