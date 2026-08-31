"""Generate mode: evaluate whether the player needs a choice, and if so, block
the graph until the player responds (or cancels / times out).

/ 生成模式：判断玩家是否需要选择，若需要则阻塞图直到玩家响应
  （或取消 / 超时）。

Outcomes / 结果:
  * Cancel  → clear the pending choice from DB; graph continues with remaining TODOs.
    / 取消 → 从数据库清除待处理选择；图继续执行剩余 TODO。
  * Timeout → persist the pending choice in DB; the supervisor task is force-completed
    so the worker exits cleanly; the next `/api/chat` resumes via supervisor short-circuit.
    / 超时 → 将待处理选择持久化到数据库；强制完成 supervisor 任务使 worker 干净退出；
      下次 `/api/chat` 通过 supervisor 短路恢复。
  * Respond → player answered via API; call `_process_choice` inline within this same
    graph invocation and return the result immediately.
    / 响应 → 玩家通过 API 做出选择；在本图调用内直接调用 `_process_choice` 并立即返回结果。
"""

import json
import traceback
from typing import Any, Dict

from choice_waiter import CANCEL_SENTINEL, wait_for_choice
from config_loader import build_node_prompt, get_llm, get_node_params, is_player_choice_enabled
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from RPA_langGraph.nodes.player_choice_node._common import PLAYER_CHOICE_PROMPT, _finish_generate, _safe
from RPA_langGraph.nodes.player_choice_node._process import _process_choice
from services.formatters import chat_json, fmt_all_characters, fmt_history, fmt_node_outputs, fmt_user_character
from services.id_utils import generate_history_id
from SQLiteClient import get_db
from SSEPublisher import publisher


def _generate_choice(state: AgentState) -> Dict[str, Any]:
    # Feature toggle: if player choice is disabled, short-circuit immediately
    # (before any SSE or LLM calls so the frontend graph also stays clean).
    # / 功能开关：若玩家选择功能已禁用，立即短路返回
    #   （在 SSE/LLM 调用之前，所以前端图结构也保持干净）。
    if not is_player_choice_enabled():
        logger.node_start("player_choice_node", state)
        logger.node_end("player_choice_node", {"triggered": False, "disabled": True})
        return {}

    logger.node_start("player_choice_node", state)
    publish_node_start(state, "player_choice_node", "分析是否需要玩家选择...")

    db = get_db()

    # Prepare context
    history = state.get("sessionHistory", [])
    recent_history = history[-10:] if len(history) > 10 else history
    history_text = fmt_history(recent_history)
    node_outputs = fmt_node_outputs(state.get("directorGraphOutput", []))
    character_ids = state.get("sessionPresentCharacter", [])
    characters_text = fmt_all_characters(db, character_ids)
    user_character_text = fmt_user_character(db, state.get("sessionUserCharacterID", ""))

    # Format TODO list
    todo_list = state.get("directorToDoList", [])
    todo_text = (
        "\n".join(
            [
                f"- {{targetNode: {t['targetNode']}, isCompleted: {t['isCompleted']}, extraData: {t['extraData']}}}"
                for t in todo_list
            ]
        )
        if todo_list
        else "(空)"
    )

    prompt = build_node_prompt(
        "player_choice_node",
        PLAYER_CHOICE_PROMPT,
        context_state=state,
        history=_safe(history_text or "(空)"),
        node_outputs=_safe(node_outputs or "(空)"),
        characters=_safe(characters_text or "(空)"),
        user_character=_safe(user_character_text or "(空)"),
        todo_list=_safe(todo_text),
    )

    messages = [
        {"role": "system", "content": "你是一个剧情分析师，负责判断是否需要玩家做出选择。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("player_choice_node")
    params = get_node_params().get("player_choice_node", {})
    try:
        data, response = chat_json(llm, messages, params)
        logger.log_llm("player_choice_node", response, params)
    except Exception:
        traceback.print_exc()
        logger.node_error("player_choice_node")
        logger.log_llm_error("player_choice_node")
        return _finish_generate(state, triggered=False)

    if not isinstance(data, dict):
        return _finish_generate(state, triggered=False)

    need_choice = bool(data.get("need_choice", False))
    if not need_choice:
        logger.node_end("player_choice_node", {"triggered": False})
        return _finish_generate(state, triggered=False)

    choices = data.get("choices", [])
    if not isinstance(choices, list) or len(choices) < 2:
        logger.node_end("player_choice_node", {"triggered": False})
        return _finish_generate(state, triggered=False)

    context = str(data.get("context", "请做出选择"))

    # Save choice prompt to session_history
    session_id = state.get("sessionID", "")
    choice_history_id = generate_history_id()
    choice_content = json.dumps(
        {"contentType": "player_choice", "context": context, "choices": choices}, ensure_ascii=False
    )
    try:
        db.execute(
            "INSERT INTO session_history "
            "(sessionHistoryID, parentID, role, createdBy, content, "
            "recordCreatedTime, recordUpdatedTime) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (choice_history_id, session_id, "system", "player_choice", choice_content),
        )
    except Exception:
        traceback.print_exc()

    # Build pending choice data (used for page-refresh / timeout recovery and inline processing)
    pending_data = {
        "phase": "awaiting_player",
        "choices": choices,
        "context": context,
        "remainingTodos": [t for t in todo_list if not t["isCompleted"]],
        "savedDirectorOutput": state.get("directorGraphOutput", []),
        "choiceHistoryId": choice_history_id,
    }

    # Persist pending choice immediately so a browser refresh (or server
    # restart) during the wait can still resume it via /api/chat/choice.
    # The live/inline and resume paths both clear this on success/_finish_resume.
    try:
        db.execute(
            "UPDATE session SET sessionPendingChoice = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
            (json.dumps(pending_data, ensure_ascii=False), session_id),
        )
    except Exception:
        traceback.print_exc()

    # Push SSE
    publisher.publish(
        "player_choice",
        {
            "sessionID": state.get("sessionID", ""),
            "context": context,
            "choices": choices,
            "sessionHistoryID": choice_history_id,
        },
    )

    publish_node_complete(state, "player_choice_node", "已生成玩家选择事件")

    # Block and wait for player choice via SSE → frontend → API
    choice_text = wait_for_choice(session_id)

    if choice_text == CANCEL_SENTINEL:
        # Player cancelled: clear pending state, continue with remaining TODOs
        try:
            db.execute(
                "UPDATE session SET sessionPendingChoice = NULL, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                (session_id,),
            )
        except Exception:
            traceback.print_exc()

        publish_node_complete(state, "player_choice_node", "玩家取消了选择")
        logger.node_end("player_choice_node", {"triggered": True, "cancelled": True})
        return {}

    if choice_text is None:
        # Timeout: persist pending state for page-reload recovery
        try:
            db.execute(
                "UPDATE session SET sessionPendingChoice = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                (json.dumps(pending_data, ensure_ascii=False), session_id),
            )
        except Exception:
            traceback.print_exc()

        result: Dict[str, Any] = {"pendingPlayerChoice": pending_data}
        supervisor_task = state.get("supervisorCurrentTask")
        if supervisor_task:
            supervisor_task["isCompleted"] = True
            result["supervisorToDoList"] = [supervisor_task]
            result["supervisorCurrentTask"] = None
        logger.node_end("player_choice_node", {"triggered": True, "timeout": True})
        return result

    # Player responded via API: process the choice inline within this same graph invocation
    pending_data["player_chose"] = choice_text
    try:
        result = _process_choice(state, pending_data, player_message=choice_text)
    except Exception:
        traceback.print_exc()
        logger.node_error("player_choice_node")
        # Fallback: save pending state so the graph can recover on next run
        try:
            db = get_db()
            db.execute(
                "UPDATE session SET sessionPendingChoice = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                (json.dumps(pending_data, ensure_ascii=False), state.get("sessionID", "")),
            )
        except Exception:
            pass
        result = {"pendingPlayerChoice": pending_data}
        supervisor_task = state.get("supervisorCurrentTask")
        if supervisor_task:
            supervisor_task["isCompleted"] = True
            result["supervisorToDoList"] = [supervisor_task]
            result["supervisorCurrentTask"] = None
    return result