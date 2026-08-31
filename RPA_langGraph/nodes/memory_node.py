from typing import Any, Dict

from ChromaDBClient import safe_get_chroma
from config_loader import get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from RPA_langGraph.nodes._memory_utils import generate_character_memories_parallel
from services.formatters import fmt_history
from services.id_utils import generate_memory_id
from SQLiteClient import db_lock, get_db


def memory_node(state: AgentState) -> Dict[str, Any]:
    session_id = state.get("sessionID", "")
    character_ids = state.get("sessionPresentCharacter", [])
    if not character_ids:
        return {}

    logger.node_start("memory_node", state)
    publish_node_start(state, "memory_node", "总结角色记忆...")

    db = get_db()
    chroma = safe_get_chroma()
    history_text = fmt_history(state.get("sessionHistory", []))

    # Phase 1+2: parallel per-character LLM calls (DB reads serialized).
    # / 阶段 1+2：按角色并行 LLM 调用（DB 读已串行化）。
    params = get_node_params().get("memory_node", {})
    results = generate_character_memories_parallel(
        db, session_id, character_ids, history_text, params=params, log_label="memory_node", context_state=state
    )

    # Phase 3: serialized writes in one transaction under db_lock.
    # / 阶段 3：db_lock 保护下的单一事务串行写入。
    try:
        with db_lock:
            db.begin()
            try:
                for character_id in character_ids:
                    content = results.get(character_id)
                    if not content:
                        continue
                    memory_id = generate_memory_id()
                    db.execute(
                        "INSERT INTO memory "
                        "(memoryID, sessionID, characterID, content, recordCreatedTime, recordUpdatedTime) "
                        "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
                        (memory_id, session_id, character_id, content),
                    )
                    try:
                        collection = chroma.get_or_create_collection(
                            f"session_{session_id}_memory_{character_id}"
                        )
                        collection.add(ids=[memory_id], documents=[content])
                    except Exception:
                        pass

                db.execute(
                    "UPDATE session SET memoryRoundCounter = 0 WHERE sessionID = ?",
                    (session_id,),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
    except Exception:
        logger.node_error("memory_node")

    publish_node_complete(state, "memory_node", "记忆总结完毕")
    logger.node_end("memory_node", {"memoryRoundCounter": 0})
    return {"memoryRoundCounter": 0}
