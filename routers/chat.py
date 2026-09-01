"""Chat endpoints: graph execution lifecycle, SSE stream, player-choice
resume/cancel, and graph topology inspection.

/ 聊天端点：图执行生命周期、SSE 流、玩家选择恢复/取消、图拓扑查看。

This is the bridge between the REST API and the LangGraph state machine.
`_build_state` reconstructs an `AgentState` from SQLite; `_run_graph` invokes
the supervisor graph in a background thread and publishes `graph_complete` /
`history_update` SSE events when it finishes.
/ 这是 REST API 与 LangGraph 状态机之间的桥梁。`_build_state` 从 SQLite 重建 AgentState；
  `_run_graph` 在后台线程中调用 supervisor 图，并在结束时发布 `graph_complete` /
  `history_update` SSE 事件。
"""

import json
import traceback
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from choice_waiter import cancel_choice, submit_choice
from config_loader import get_memory_summarize_interval, is_player_choice_enabled
from graph_logger import logger
from models import ChatRequest
from routers.deps import executor, graph_tasks, history_svc, ok, session_svc
from RPA_langGraph.AgentState import AgentState, EnvData
from RPA_langGraph.supervisor_graph import supervisor_graph
from SSEPublisher import publisher

router = APIRouter()


def _build_state(session_id: str, message: str, is_choice_resume: bool = False) -> AgentState:
    """Build an AgentState by loading session/history from the database.

    / 从数据库加载会话/历史数据，构建 AgentState。

    When `is_choice_resume` is False (regular `/api/chat`), any stale pending
    player choice is cleared so the message starts a fresh turn. When True
    (`/api/chat/choice` fallback), the saved TODOs and director output are
    restored so the graph can resume processing the choice.
    / is_choice_resume=False（普通 /api/chat）时清除陈旧的待处理选择；True（/api/chat/choice
      回退）时恢复保存的 TODO 与导演输出以续接选择处理。
    """
    session = session_svc.get(session_id)
    if not session:
        raise ValueError("会话不存在")

    history_rows = history_svc.list_by_session(session_id)
    history: List[BaseMessage] = []
    for h in history_rows:
        if h["role"] == "user":
            history.append(HumanMessage(content=h["content"]))
        else:
            history.append(AIMessage(content=h["content"]))

    msg_id = f"{session_id}_{len(history)}"
    history.append(HumanMessage(content=message, id=msg_id))

    env = session.get("sessionEnvData", {})
    if isinstance(env, str):
        try:
            env = json.loads(env)
        except Exception:
            env = {"location": "", "time": "", "atmosphere": ""}

    pending_choice_data = session.get("sessionPendingChoice")
    if pending_choice_data and isinstance(pending_choice_data, str):
        try:
            pending_choice_data = json.loads(pending_choice_data)
        except Exception:
            pending_choice_data = None

    if not is_choice_resume:
        if pending_choice_data is not None:
            try:
                session_svc.update(session_id, {"sessionPendingChoice": None})
            except Exception:
                traceback.print_exc()
        pending_choice_data = None

    restored_todos = []
    restored_output = []
    if pending_choice_data and isinstance(pending_choice_data, dict):
        restored_todos = pending_choice_data.get("remainingTodos", [])
        restored_output = pending_choice_data.get("savedDirectorOutput", [])

    return AgentState(
        sessionID=session_id,
        sessionHistory=history,
        sessionEnvData=EnvData(
            location=env.get("location", ""), time=env.get("time", ""), atmosphere=env.get("atmosphere", "")
        ),
        sessionPresentCharacter=session.get("sessionPresentCharacter", []),
        sessionDepartedCharacter=session.get("sessionDepartedCharacter", []),
        outline=session.get("outline", []),
        supervisorToDoList=[],
        directorToDoList=restored_todos,
        supervisorCurrentTask=None,
        directorCurrentTask=None,
        sessionWorldviewCollectionID=session.get("worldviewCollectionID", ""),
        sessionUserCharacterID=session.get("userCharacterID", ""),
        permanentWorldviewCollectionEntry=[],
        directorGraphOutput=restored_output,
        memoryRoundCounter=session.get("memoryRoundCounter", 0),
        memorySummarizeInterval=get_memory_summarize_interval(),
        pendingDepartedIDs=[],
        pendingPlayerChoice=pending_choice_data,
    )


def _run_graph(state: AgentState):
    """Execute supervisor_graph.invoke() in a background thread.

    / 在后台线程中执行 supervisor_graph.invoke()。Always publishes
    `graph_complete` and `history_update` from the finally block so the
    frontend can stop its spinner and refresh regardless of outcome.
    / 无论成功或失败，finally 块都会发布 `graph_complete` 与 `history_update`，
      使前端能停止加载动画并刷新。
    """
    task_key = state["sessionID"]
    graph_tasks[task_key] = "running"
    error = None
    try:
        logger.log_input(state)
        result = supervisor_graph.invoke(state)
        logger.log_output(result)
        graph_tasks[task_key] = "completed"
    except Exception:
        logger.node_error("supervisor_graph")
        error = traceback.format_exc()
        graph_tasks[task_key] = "failed"
        publisher.publish(
            "graph_error",
            {"sessionID": state["sessionID"], "error": str(error)},
        )
    finally:
        try:
            publisher.publish(
                "graph_complete", {"sessionID": state["sessionID"]}
            )
        except Exception:
            logger.node_error("publish_graph_complete")
        try:
            history_rows = history_svc.list_by_session(state["sessionID"])
            publisher.publish(
                "history_update",
                {
                    "sessionID": state["sessionID"],
                    "history": [dict(r) for r in history_rows],
                },
            )
        except Exception:
            logger.node_error("publish_history_update")
    if error:
        traceback.print_exc()


def _submit_graph(state: AgentState) -> None:
    """Submit a graph run to the executor and register its task-status key.
    / 将图执行提交到线程池并登记任务状态键。"""
    task_key = state["sessionID"]
    graph_tasks[task_key] = "pending"
    future = executor.submit(_run_graph, state)
    future.add_done_callback(lambda _: graph_tasks.pop(task_key, None))


@router.post("/api/chat")
def chat(req: ChatRequest):
    try:
        state = _build_state(req.sessionID, req.message)
    except ValueError as e:
        raise HTTPException(400, str(e))

    _submit_graph(state)
    return ok({"sessionID": req.sessionID})


@router.get("/api/chat/status/{session_id}")
def get_chat_status(session_id: str):
    status = graph_tasks.get(session_id, "idle")
    return ok({"status": status})


@router.get("/api/chat/stream")
async def chat_stream():
    return StreamingResponse(
        publisher.subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat/choice")
def submit_player_choice(data: dict):
    """Wake up a waiting graph with the player's choice.

    First tries to signal the live in-progress graph (the waiter). If no waiter
    exists, falls back to a fresh graph run that resumes the pending choice
    from `session.sessionPendingChoice`.
    """
    session_id = data.get("sessionID", "")
    choice_text = data.get("choiceText", "")
    if not session_id:
        raise HTTPException(400, "Missing sessionID")

    if submit_choice(session_id, choice_text):
        return ok(msg="Choice submitted, graph resuming")

    # No live waiter — fall back to a fresh graph run in choice-resume mode.
    session = session_svc.get(session_id)
    pending = session.get("sessionPendingChoice") if session else None
    if not pending:
        raise HTTPException(404, "No pending choice found for this session")
    try:
        state = _build_state(session_id, choice_text, is_choice_resume=True)
    except ValueError as e:
        raise HTTPException(400, str(e))

    _submit_graph(state)
    return ok(msg="Choice submitted (resume run)")


@router.post("/api/chat/choice/cancel")
def cancel_player_choice(data: dict):
    """Signal the waiting graph that the player cancelled the choice.

    If no live waiter exists, just clear the persisted pending choice so the
    frontend can stop showing the panel without erroring.
    """
    session_id = data.get("sessionID", "")
    if not session_id:
        raise HTTPException(400, "Missing sessionID")
    if cancel_choice(session_id):
        return ok(msg="Choice cancelled, graph continuing")

    try:
        session_svc.update(session_id, {"sessionPendingChoice": None})
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, "Failed to clear pending choice")
    return ok(msg="Choice cancelled (persisted cleared)")


@router.get("/api/graph/topology")
def get_graph_topology():
    from RPA_langGraph.director_subgraph import director_subgraph
    from plugin_system import plugin_labels
    from plugin_system.registry import registry as plugin_registry

    NODE_LABELS = {
        "supervisor_node": "用户输入分类",
        "route_next_supervisor_todo": "取下一个 TODO",
        "director_subgraph": "Director 子图",
        "general_narration_node": "通用叙述",
        "recall_node": "角色召回",
        "introduce_character_node": "角色引入",
        "director_node": "剧情状态分析",
        "route_next_todo": "取下一个 TODO",
        "actor_batch_node": "并行角色扮演",
        "note_batch_node": "旁白/大纲并行",
        "review_start": "审查链入口",
        "review_env_node": "环境审看",
        "review_character_node": "角色审看",
        "review_departure_node": "离场分析",
        "memory_node": "记忆总结",
        "player_choice_node": "玩家选择",
        "update_relationship_node": "关系更新",
        "image_gen_node": "场景插画",
    }

    NODE_TYPES = {
        "supervisor_node": "llm",
        "route_next_supervisor_todo": "router",
        "director_subgraph": "subgraph",
        "general_narration_node": "llm",
        "recall_node": "llm",
        "introduce_character_node": "llm",
        "director_node": "llm",
        "route_next_todo": "router",
        "actor_batch_node": "llm",
        "note_batch_node": "llm",
        "review_start": "router",
        "review_env_node": "review",
        "review_character_node": "review",
        "review_departure_node": "review",
        "memory_node": "llm",
        "player_choice_node": "llm",
        "update_relationship_node": "review",
        "image_gen_node": "llm",
    }

    # Plugin-contributed nodes / sub-graphs join the label & type maps without
    # overriding built-ins. / 插件贡献的节点/子图并入标签与类型映射，不覆盖内置项。
    for _name, _lt in plugin_labels().items():
        NODE_LABELS.setdefault(_name, _lt["label"])
        NODE_TYPES.setdefault(_name, _lt["type"])

    def build_graph_data(graph, graph_id, title, parent=None):
        g = graph.get_graph().reid()

        # Determine which nodes to hide based on feature toggles.
        # / 根据功能开关确定要隐藏的节点。
        hidden: set[str] = set()
        if not is_player_choice_enabled():
            hidden.add("player_choice_node")

        nodes = []
        node_ids = set()
        for nid, n in g.nodes.items():
            if nid in ("__start__", "__end__") or nid in hidden:
                continue
            node_ids.add(nid)
            nodes.append({"id": nid, "label": NODE_LABELS.get(nid, n.name), "type": NODE_TYPES.get(nid, "unknown")})
        edges = []
        for e in g.edges:
            if e.source in hidden or e.target in hidden:
                continue
            if e.source not in node_ids and e.target not in node_ids:
                continue
            edges.append({"from": e.source, "to": e.target, "label": e.data or "", "conditional": e.conditional})
        result = {"id": graph_id, "title": title, "nodes": nodes, "edges": edges}
        if parent:
            result["parent"] = parent
        return result

    graphs = [
        build_graph_data(supervisor_graph, "supervisor", "Supervisor 图"),
        build_graph_data(director_subgraph, "director", "Director 子图", parent="supervisor"),
    ]

    # Standalone graphs contributed by plugins are appended (mount_to-based
    # sub-graphs already appear inside their parent graph automatically).
    # / 插件贡献的独立图追加到列表；mount_to 挂载的子图已自动出现在父图中。
    for _spec in plugin_registry.graphs:
        if _spec.compiled is None:
            continue  # 未挂载（如 mount_to 指向不存在的图）→ 不展示
        graphs.append(
            build_graph_data(_spec.compiled, _spec.graph_id, _spec.title or _spec.graph_id, parent=_spec.parent)
        )

    return ok({"graphs": graphs})