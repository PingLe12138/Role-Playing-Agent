import json
import traceback
from typing import Any, Dict

from langchain_core.messages import AIMessage

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import (
    fmt_all_characters,
    fmt_all_emotion_states,
    fmt_all_memories,
    fmt_all_relationships,
    fmt_env_data,
    fmt_history,
    fmt_user_character,
    fmt_worldview_all,
)
from services.id_utils import generate_history_id
from SQLiteClient import db_lock, get_db
from SSEPublisher import publisher

NARRATION_PROMPT = (
    """你是一个角色扮演系统中的旁白节点 (Narration)。
你的任务是根据世界观设定、角色记忆和对话历史，以第三人称生成一段旁白，对当前场景和角色言行做补充性的描述，而不是推动剧情发展。

要求：
1. 以第三人称叙述，描写当前的场景氛围和环境细节，不要主动推进剧情
2. 紧接对话历史的最后一条内容自然延续，不要重述已经发生过的事
3. 语言生动简洁，避免拖沓
4. 直接输出旁白文本，不要包含任何标记、说明或额外格式
5. 禁止自行推进剧情或引入新事件、新角色

"""
    + """

=== 当前环境 ===
{env_data}

=== 对话历史 ===
{history}

=== 在场角色信息卡 ===
{character_cards}

=== 用户角色信息 ===
{user_character}

=== 世界观设定 ===
{worldview_entries}

=== 角色记忆 ===
{memories}

=== 角色关系 ===
{relationships}

=== 在场角色情绪 ===
{emotion_states}

请以第三人称叙述，完美衔接最后一条对话内容，描述场景氛围、角色状态和动作，无需包含对话内容。"""
)


def execute_narration(state: AgentState) -> Dict[str, Any]:
    """Run one narration generation (used by the parallel note_batch_node).
    Thread-safe: the LLM call runs unlocked; the DB write is serialized under
    db_lock.

    / 生成一次旁白（由并行 note_batch_node 调用）。
      线程安全：LLM 调用不加锁，DB 写在 db_lock 下串行化。
    """
    logger.node_start("narration_node", state)

    publish_node_start(state, "narration_node", "生成旁白...")
    db = get_db()

    history = state.get("sessionHistory", [])
    history_text = fmt_history(history)

    character_ids = state.get("sessionPresentCharacter", [])
    # DB reads serialized under db_lock (shared connection — see actor_node).
    # / DB 读在 db_lock 下串行执行（共享连接——见 actor_node）。
    with db_lock:
        character_cards = fmt_all_characters(db, character_ids)
        user_character = fmt_user_character(db, state.get("sessionUserCharacterID", ""))
        worldview_entries = fmt_worldview_all(db, state.get("sessionWorldviewCollectionID", ""))
        memories = fmt_all_memories(db, state.get("sessionID", ""), character_ids)
        relationships_text = fmt_all_relationships(db, state.get("sessionID", ""), character_ids)
        emotion_states = fmt_all_emotion_states(db, state.get("sessionID", ""), character_ids)
    env_data = fmt_env_data(state.get("sessionEnvData", {}))

    prompt = build_node_prompt(
        "narration_node",
        NARRATION_PROMPT,
        context_state=state,
        env_data=env_data,
        history=history_text or "(空)",
        character_cards=character_cards,
        user_character=user_character,
        worldview_entries=worldview_entries,
        memories=memories,
        relationships=relationships_text,
        emotion_states=emotion_states,
    )

    messages = [
        {"role": "system", "content": "你是一个故事叙述者，负责生成第三人称旁白。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("narration_node")
    params = get_node_params().get("narration_node", {})
    try:
        response = llm.chat(
            messages,
            temperature=params.get("temperature"),
            max_tokens=params.get("max_tokens"),
            isEnableThinking=params.get("is_enable_thinking"),
            reasoning_effort=params.get("reasoning_effort"),
            max_context_tokens=params.get("max_context_tokens"),
        )
        logger.log_llm("narration_node", response, params)
    except Exception:
        traceback.print_exc()
        logger.log_llm_error("narration_node")
        logger.node_error("narration_node")
        logger.node_end("narration_node", {})
        return {}

    formatted = json.dumps({"contentType": "narration", "content": response}, ensure_ascii=False)

    try:
        session_id = state.get("sessionID", "")
        history_id = generate_history_id()
        with db_lock:
            db.execute(
                "INSERT INTO session_history "
                "(sessionHistoryID, parentID, role, createdBy, content, "
                "recordCreatedTime, recordUpdatedTime) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (history_id, session_id, "narration", "narration", formatted),
            )
    except Exception:
        traceback.print_exc()

    publisher.publish(
        "message",
        {
            "sessionID": state.get("sessionID", ""),
            "contentType": "narration",
            "content": response,
            "role": "narration",
            "sessionHistoryID": history_id,
        },
    )

    publish_node_complete(state, "narration_node", "旁白生成完毕")
    result = {
        "sessionHistory": [AIMessage(content=formatted)],
        "directorGraphOutput": [{"node": "narration_node", "result": response}],
    }
    logger.node_end("narration_node", result)
    return result
