import json
import traceback
from typing import Any, Dict

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import fmt_all_characters, fmt_all_memories, fmt_history, fmt_worldview_all
from SQLiteClient import db_lock, get_db
from SSEPublisher import publisher

MAX_OUTLINE_ENTRIES = 100

OUTLINE_PROMPT = (
    """你是一个角色扮演系统的大纲节点 (Outline)。
根据现有剧情大纲、世界观设定、角色记忆和最新的对话记录，总结自上次大纲节点后发生了哪些重要事件。

要求：
1. 以第三人称叙述
2. 关注影响主线的重要事件、关键对话和角色变化
3. 不要重述上次大纲之前的内容
4. 语言简洁清晰，100-200字
5. 直接输出总结文本

"""
    + """

=== 已有剧情大纲 ===
{existing_outline}

=== 对话历史 ===
{history}

=== 在场角色 ===
{character_cards}

=== 世界观设定 ===
{worldview_entries}

=== 角色记忆 ===
{memories}

以上是已经总结过的事件和当前对话数据。
请基于对话历史，找出尚未在已有大纲中记录的新的重大事件（如关键剧情转折、角色关系变化、重要信息揭示等），
生成一段增量总结文字。"""
)


def execute_outline(state: AgentState) -> Dict[str, Any]:
    """Run one outline summarization (used by the parallel note_batch_node).
    Thread-safe: the LLM call runs unlocked; the DB write is serialized under
    db_lock.

    / 生成一次剧情大纲总结（由并行 note_batch_node 调用）。
      线程安全：LLM 调用不加锁，DB 写在 db_lock 下串行化。
    """
    logger.node_start("outline_node", state)

    publish_node_start(state, "outline_node", "总结剧情...")
    db = get_db()

    history = state.get("sessionHistory", [])
    history_text = fmt_history(history)

    character_ids = state.get("sessionPresentCharacter", [])
    # DB reads serialized under db_lock (shared connection — see actor_node).
    # / DB 读在 db_lock 下串行执行（共享连接——见 actor_node）。
    with db_lock:
        character_cards = fmt_all_characters(db, character_ids)
        worldview_entries = fmt_worldview_all(db, state.get("sessionWorldviewCollectionID", ""))
        memories = fmt_all_memories(db, state.get("sessionID", ""), character_ids)
    existing_outline = "\n".join(state.get("outline", [])[-50:])

    prompt = build_node_prompt(
        "outline_node",
        OUTLINE_PROMPT,
        context_state=state,
        existing_outline=existing_outline or "(空)",
        history=history_text or "(空)",
        character_cards=character_cards,
        worldview_entries=worldview_entries,
        memories=memories,
    )

    messages = [
        {"role": "system", "content": "你是一个剧情记录者，负责总结故事中的重大事件。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("outline_node")
    params = get_node_params().get("outline_node", {})
    try:
        response = llm.chat(
            messages,
            temperature=params.get("temperature"),
            max_tokens=params.get("max_tokens"),
            isEnableThinking=params.get("is_enable_thinking"),
            reasoning_effort=params.get("reasoning_effort"),
            max_context_tokens=params.get("max_context_tokens"),
        )
        logger.log_llm("outline_node", response, params)
    except Exception:
        traceback.print_exc()
        logger.log_llm_error("outline_node")
        logger.node_error("outline_node")
        logger.node_end("outline_node", {})
        return {}

    updated_outline = (state.get("outline", []) + [response])[-MAX_OUTLINE_ENTRIES:]
    try:
        with db_lock:
            db.execute(
                "UPDATE session SET outline = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                (json.dumps(updated_outline, ensure_ascii=False), state.get("sessionID", "")),
            )
    except Exception:
        traceback.print_exc()

    publisher.publish("session_update", {"outline": updated_outline})

    publish_node_complete(state, "outline_node", "总结完成")
    result = {
        "outline": updated_outline,
        "directorGraphOutput": [{"node": "outline_node", "result": response}],
    }
    logger.node_end("outline_node", result)
    return result
