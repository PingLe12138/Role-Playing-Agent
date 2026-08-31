import json
import traceback
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
from SSEPublisher import publisher


def review_departure_node(state: AgentState) -> Dict[str, Any]:
    """Process characters that left the scene this turn: move them into the
    departed list and generate a first-person departure memory for each.

    / 处理本轮离场角色：移入离场列表，并为每个离场角色生成第一人称离别记忆。

    `memoryRoundCounter` is incremented so that the memory node can trigger
    periodic summaries for all remaining characters.
    / memoryRoundCounter 递增，使 memory 节点能触发对所有剩余角色的周期性总结。

    This node also finalizes the director subgraph state (clearing
    directorGraphOutput / directorToDoList / directorCurrentTask) as the
    subgraph's last review step.
    / 本节点同时收尾子图状态（清空 directorGraphOutput / directorToDoList /
      directorCurrentTask），作为审查链的最后一步。

    Runs in parallel with review_env_node and update_relationship_node: the
    departure memories use parallel LLM calls, and all DB writes are serialized
    under `db_lock` so they cannot interleave with the sibling nodes' writes.
    / 与 review_env_node / update_relationship_node 并行执行：离别记忆使用并行
      LLM 调用，所有 DB 写在 db_lock 下串行化，避免与兄弟节点的写入交错。
    """
    logger.node_start("review_departure_node", state)

    publish_node_start(state, "review_departure_node", "处理离场角色...")

    pending_ids = state.get("pendingDepartedIDs", [])
    if not pending_ids:
        return _finish(state, {})

    db = get_db()
    chroma = safe_get_chroma()
    session_id = state.get("sessionID", "")
    existing_departed = state.get("sessionDepartedCharacter", [])

    new_departed = list(existing_departed)

    # Pre-compute the shared history text once for all departure memories.
    history_text = fmt_history(state.get("sessionHistory", []))
    departure_params = get_node_params().get("review_departure_node", {})

    # Parallel LLM calls for every departing character (DB reads serialized).
    # / 为每个离场角色并行发起 LLM 调用（DB 读已串行化）。
    memories = generate_character_memories_parallel(
        db,
        session_id,
        pending_ids,
        history_text,
        params=departure_params,
        log_label="review_departure_memory",
        llm_node="review_departure_node",
        context_state=state,
    )

    with db_lock:
        db.begin()
        try:
            for cid in pending_ids:
                if cid and cid not in new_departed:
                    new_departed.append(cid)
                content = memories.get(cid)
                if not content:
                    continue
                memory_id = generate_memory_id()
                db.execute(
                    "INSERT INTO memory "
                    "(memoryID, sessionID, characterID, content, recordCreatedTime, recordUpdatedTime) "
                    "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
                    (memory_id, session_id, cid, content),
                )
                try:
                    collection = chroma.get_or_create_collection(f"session_{session_id}_memory_{cid}")
                    collection.add(ids=[memory_id], documents=[content])
                except Exception:
                    pass

            if new_departed != existing_departed:
                db.execute(
                    "UPDATE session SET sessionDepartedCharacter = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                    (json.dumps(new_departed, ensure_ascii=False), session_id),
                )

            db.commit()
        except Exception:
            db.rollback()
            traceback.print_exc()
            return _finish(state, {})

    updates: Dict[str, Any] = {}
    if new_departed != existing_departed:
        updates["sessionDepartedCharacter"] = new_departed
        publisher.publish("session_update", {"sessionDepartedCharacter": new_departed})

    return _finish(state, updates)


def _finish(state: AgentState, updates: Dict[str, Any]) -> Dict[str, Any]:
    updates["pendingDepartedIDs"] = []
    new_counter = state.get("memoryRoundCounter", 0) + 1
    updates["memoryRoundCounter"] = new_counter

    try:
        db = get_db()
        with db_lock:
            db.execute(
                "UPDATE session SET memoryRoundCounter = ? WHERE sessionID = ?",
                (new_counter, state.get("sessionID", "")),
            )
    except Exception:
        pass

    supervisor_task = state.get("supervisorCurrentTask")
    if supervisor_task:
        supervisor_task["isCompleted"] = True
        updates["supervisorToDoList"] = [supervisor_task]
        updates["supervisorCurrentTask"] = None

    # Finalize the director subgraph state before handoff to memory/image nodes.
    # / 收尾子图状态，随后交由 memory / image 节点处理。
    updates["directorGraphOutput"] = []
    updates["directorToDoList"] = []
    updates["directorCurrentTask"] = None

    publish_node_complete(state, "review_departure_node", "离场处理完毕")

    logger.node_end("review_departure_node", updates)
    return updates
