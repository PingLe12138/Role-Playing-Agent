"""Resume mode: process the player's choice response and finalize the turn.

/ 恢复模式：处理玩家的选择响应并收尾本轮。

Reached either by the dispatcher (when the graph is invoked with a pending
`awaiting_player` choice), or inline from `_generate_choice` when the player
answers via the API within the same graph call.
/ 由分发器在图带着 `awaiting_player` 待处理选择被调用时进入，或在玩家于同一图调用内
  通过 API 作答时由 `_generate_choice` 内联进入。
"""

import traceback
from typing import Any, Dict, List

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState, ToDoItem
from RPA_langGraph.node_events import publish_node_start
from RPA_langGraph.nodes.player_choice_node._common import CHOICE_PROCESS_PROMPT, _finish_resume, _safe
from services.formatters import chat_json, fmt_all_characters, fmt_history, fmt_node_outputs, fmt_user_character
from SQLiteClient import get_db


def _process_choice(state: AgentState, pending: dict, player_message: str = "") -> Dict[str, Any]:
    """Resume mode: process the player's choice response.

    If player_message is provided (live blocking mode), use it directly.
    Otherwise (page reload), read from the latest user message in history.
    """
    logger.node_start("player_choice_node", state)
    publish_node_start(state, "player_choice_node", "处理玩家选择...")

    db = get_db()

    # Get the player's message: either from waiter (live) or from history (reload)
    history = state.get("sessionHistory", [])
    if not player_message:
        for msg in reversed(history):
            if hasattr(msg, "type") and msg.type == "human":
                player_message = msg.content if hasattr(msg, "content") else str(msg)
                break

    choices = pending.get("choices", [])
    choices_text = "\n".join([f"[{c.get('id', '')}] {c.get('text', '')}" for c in choices])

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

    node_outputs = fmt_node_outputs(state.get("directorGraphOutput", []))
    character_ids = state.get("sessionPresentCharacter", [])
    characters_text = fmt_all_characters(db, character_ids)
    user_character_text = fmt_user_character(db, state.get("sessionUserCharacterID", ""))
    recent_history = history[-10:] if len(history) > 10 else history
    history_text = fmt_history(recent_history)

    prompt = build_node_prompt(
        "player_choice_process",
        CHOICE_PROCESS_PROMPT,
        context_state=state,
        context=_safe(pending.get("context", "")),
        choices_text=_safe(choices_text),
        player_choice=_safe(player_message),
        todo_list=_safe(todo_text),
        node_outputs=_safe(node_outputs or "(空)"),
        characters=_safe(characters_text or "(空)"),
        user_character=_safe(user_character_text or "(空)"),
        history=_safe(history_text or "(空)"),
    )

    messages = [
        {"role": "system", "content": "你是一个剧情处理助手，负责处理玩家的选择并更新任务列表。"},
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
        return _finish_resume(state, pending, [], player_message=player_message)

    if not isinstance(data, dict):
        return _finish_resume(state, pending, [], player_message=player_message)

    result_narration = str(data.get("result_narration", ""))
    updated_todos_raw = data.get("updated_todos", [])

    updated_todos: List[ToDoItem] = []
    if isinstance(updated_todos_raw, list):
        for item in updated_todos_raw:
            if isinstance(item, dict) and item.get("targetNode") in ("actor", "narration", "outline"):
                updated_todos.append(
                    ToDoItem(targetNode=item["targetNode"], isCompleted=False, extraData=str(item.get("extraData", "")))
                )

    return _finish_resume(state, pending, updated_todos, result_narration, player_message=player_message)