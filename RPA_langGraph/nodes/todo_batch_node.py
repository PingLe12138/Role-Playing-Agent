"""Parallel TODO execution nodes for the director subgraph.

actor_batch_node - runs ALL uncompleted actor TODOs in parallel (one LLM call
per character, thread pool), merging results back in TODO-list order.
note_batch_node  - runs the remaining narration/outline TODOs in parallel.

Design notes / 设计说明:
- LLM calls dominate latency and are thread-safe (shared OpenAI client), so
  they run concurrently; every DB write is serialized under db_lock (see
  SQLiteClient) so parallel workers cannot interleave on the shared sqlite
  connection (the review chain already follows this pattern).
- Results are merged in TODO-list order so sessionHistory and
  directorGraphOutput keep a deterministic order.
- Parallel branches see the same state snapshot: all actors react to the
  same pre-turn history, so NPCs in one wave do not react to each other's
  replies (the director prompt already instructs actors-first ordering).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
from typing import Any, Dict

from config_loader import get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from RPA_langGraph.nodes.actor_node import execute_actor
from RPA_langGraph.nodes.narration_node import execute_narration
from RPA_langGraph.nodes.outline_node import execute_outline

MAX_ACTOR_WORKERS = 4


def _uncompleted_todos(state: AgentState, target_nodes) -> list:
    return [
        t for t in state.get("directorToDoList", [])
        if not t.get("isCompleted") and t.get("targetNode") in target_nodes
    ]


def actor_batch_node(state: AgentState) -> Dict[str, Any]:
    """Run every uncompleted actor TODO in parallel.

    One thread per character; results are merged in TODO-list order so the
    appended history messages and review outputs stay deterministic.  A
    failed worker (LLM or DB error) yields no output for that character but
    never aborts the wave - the TODO is still marked completed, matching the
    single-task actor_node failure semantics.

    / 并行执行所有未完成的 actor TODO。
      每角色一线程，按 TODO 列表顺序合并结果，保证历史与审看输出顺序确定。
      单个 worker 失败（LLM/DB 异常）只损失该角色的输出，不中断整波执行，
      TODO 仍标记完成（与单任务 actor_node 的失败语义一致）。
    """
    todos = _uncompleted_todos(state, ("actor",))
    if not todos:
        return {}

    logger.node_start("actor_batch_node", state)
    publish_node_start(state, "actor_batch_node", f"并行扮演 {len(todos)} 个角色...")

    user_char_id = state.get("sessionUserCharacterID", "")
    tasks = [t for t in todos if t.get("extraData") and t.get("extraData") != user_char_id]

    results: Dict[str, Any] = {}
    params = get_node_params().get("actor_batch_node", {})
    try:
        max_workers = min(int(params.get("max_workers", MAX_ACTOR_WORKERS) or MAX_ACTOR_WORKERS), max(1, len(tasks)))
    except (TypeError, ValueError):
        max_workers = min(MAX_ACTOR_WORKERS, max(1, len(tasks)))
    if tasks:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="actor") as pool:
            futures = {pool.submit(execute_actor, state, t["extraData"]): t for t in tasks}
            for fut in as_completed(futures):
                todo = futures[fut]
                try:
                    results[todo["extraData"]] = fut.result()
                except Exception:
                    traceback.print_exc()
                    results[todo["extraData"]] = None

    history_msgs, graph_outputs, done_todos = [], [], []
    for todo in todos:
        todo["isCompleted"] = True
        done_todos.append(todo)
        r = results.get(todo.get("extraData", ""))
        if r:
            history_msgs.extend(r.get("sessionHistory", []))
            graph_outputs.extend(r.get("directorGraphOutput", []))

    result = {
        "sessionHistory": history_msgs,
        "directorToDoList": done_todos,
        "directorCurrentTask": None,
        "directorGraphOutput": graph_outputs,
    }
    publish_node_complete(state, "actor_batch_node", f"{len(tasks)} 个角色扮演完成")
    logger.node_end("actor_batch_node", result)
    return result


def note_batch_node(state: AgentState) -> Dict[str, Any]:
    """Run the remaining narration/outline TODOs in parallel.

    / 并行执行剩余的 narration/outline TODO（旁白与大纲互相独立，可同时生成）。
    """
    todos = _uncompleted_todos(state, ("narration", "outline"))
    if not todos:
        return {}

    logger.node_start("note_batch_node", state)
    publish_node_start(state, "note_batch_node", "并行生成旁白与剧情总结...")

    results: Dict[str, Any] = {}
    params = get_node_params().get("note_batch_node", {})
    try:
        max_workers = min(int(params.get("max_workers", 2) or 2), max(1, len(todos)))
    except (TypeError, ValueError):
        max_workers = min(2, max(1, len(todos)))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="note") as pool:
        futures = {}
        for todo in todos:
            fn = execute_narration if todo["targetNode"] == "narration" else execute_outline
            futures[pool.submit(fn, state)] = todo
        for fut in as_completed(futures):
            todo = futures[fut]
            try:
                results[todo["targetNode"]] = fut.result()
            except Exception:
                traceback.print_exc()
                results[todo["targetNode"]] = None

    history_msgs, graph_outputs, done_todos = [], [], []
    updated_outline = None
    for todo in todos:
        todo["isCompleted"] = True
        done_todos.append(todo)
        r = results.get(todo["targetNode"])
        if r:
            history_msgs.extend(r.get("sessionHistory", []))
            graph_outputs.extend(r.get("directorGraphOutput", []))
            if "outline" in r:
                updated_outline = r["outline"]

    result: Dict[str, Any] = {
        "sessionHistory": history_msgs,
        "directorToDoList": done_todos,
        "directorCurrentTask": None,
        "directorGraphOutput": graph_outputs,
    }
    if updated_outline is not None:
        result["outline"] = updated_outline
    publish_node_complete(state, "note_batch_node", "旁白/大纲生成完毕")
    logger.node_end("note_batch_node", result)
    return result
