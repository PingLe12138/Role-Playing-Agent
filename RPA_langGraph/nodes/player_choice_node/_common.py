"""Shared helpers for the player-choice node package: prompt templates, string
escaping, and the two "finish" finalizers shared by the generate / process
handlers.

/ 玩家选择节点包的共用辅助：提示词模板、字符串转义、两个被生成/处理
  分支共用的"收尾"函数。"""

import json
import traceback
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from graph_logger import logger
from RPA_langGraph.AgentState import AgentState, ToDoItem
from RPA_langGraph.node_events import publish_node_complete
from services.id_utils import generate_history_id
from SQLiteClient import get_db
from SSEPublisher import publisher


# Escape { and } in strings so player-generated content can't crash `.format()`.
# / 转义 { 与 }，避免玩家生成内容导致 `.format()` 崩溃。
def _safe(v: Any) -> str:
    s = str(v) if v is not None else ""
    return s.replace("{", "{{").replace("}", "}}")


PLAYER_CHOICE_PROMPT = (
    """你是一个玩家选择事件生成节点。

根据当前剧情上下文，判断是否需要为玩家提供一个选择机会。当剧情到达关键抉择点、需要玩家做出决定以推动剧情发展时，生成 2-4 个有意义的选择项。

=== 最近对话 ===
{history}

=== 子节点输出 ===
{node_outputs}

=== 在场角色信息 ===
{characters}

=== 用户角色信息 ===
{user_character}

=== 当前 TODO 列表 ===
{todo_list}

请判断是否需要触发玩家选择：
- 如果当前不需要玩家选择，返回 need_choice=false
- 如果需要，生成 2-4 个选择项，每个选择项应推进不同的剧情方向

请严格按以下 JSON 格式返回，不要包含其他内容：
{{
    "need_choice": false,
    "context": "选择场景描述（一句话，描述当前局面让玩家明白要做什么选择）",
    "choices": [
        {{"id": "1", "text": "选项1描述"}},
        {{"id": "2", "text": "选项2描述"}}
    ]
}}

注意：
- 仅在剧情到达关键决策点时触发选择（如角色提问、面临困境、需要决定行动方向等）
- 每个选项应导向不同的剧情发展方向，且有实质性的区别
- context 应简洁明了，让玩家快速理解当前需要做什么决定
- 不要频繁触发选择，一般每轮对话最多触发一次
"""
)

CHOICE_PROCESS_PROMPT = (
    """你是一个玩家选择结果处理节点。

玩家在以下场景中做出了选择，请根据玩家的选择生成结果并更新 TODO 列表。

=== 选择场景 ===
{context}

=== 可选项目 ===
{choices_text}

=== 玩家选择了 ===
{player_choice}

=== 当前 TODO 列表（部分已完成，部分未完成） ===
{todo_list}

=== 子节点中间输出 ===
{node_outputs}

=== 在场角色信息 ===
{characters}

=== 用户角色信息 ===
{user_character}

=== 最近对话 ===
{history}

请根据玩家的选择：
1. 生成一段描述玩家选择后发生的事情（第三人称叙述）
2. 判断当前 TODO 列表中哪些未完成的 TODO 需要保留、修改或删除
3. 返回更新后的 TODO 列表

请严格按以下 JSON 格式返回，不要包含其他内容：
{{
    "result_narration": "描述玩家选择后发生的情况...",
    "updated_todos": [
        {{"targetNode": "actor", "isCompleted": false, "extraData": "角色ID"}},
        {{"targetNode": "narration", "isCompleted": false, "extraData": ""}}
    ]
}}

注意：
- 只返回仍需执行的 TODO，已完成的不要返回
- 根据玩家的选择合理调整 TODO：可能需要删除某些 TODO、修改 extraData、或新增 TODO
- result_narration 以第三人称叙述，描述玩家选择后的直接结果
"""
)


def _finish_generate(state: AgentState, triggered: bool) -> Dict[str, Any]:
    """Finalize generate mode. Returns state updates.
    / 收尾生成模式，返回状态更新。"""
    if not triggered:
        publish_node_complete(state, "player_choice_node", "无需玩家选择")
    return {}


def _finish_resume(
    state: AgentState,
    pending: dict,
    updated_todos: List[ToDoItem],
    result_narration: str = "",
    player_message: str = "",
) -> Dict[str, Any]:
    """Finalize resume mode: save choice result to DB, update TODOs, clear pending.

    / 收尾恢复模式：把选择结果写入数据库、更新 TODO、清除待处理选择。
    """
    session_id = state.get("sessionID", "")
    db = get_db()

    # Use pending.player_chose (set by waiter) if available, else the passed
    # player_message, else the latest human message in history.
    # / 优先用 waiter 写入的 player_chose，其次用传入的 player_message，最后回退到历史中最近的人类消息。
    if not player_message:
        player_message = pending.get("player_chose", "")
    if not player_message:
        history = state.get("sessionHistory", [])
        for msg in reversed(history):
            if hasattr(msg, "type") and msg.type == "human":
                player_message = msg.content if hasattr(msg, "content") else str(msg)
                break

    result_data = {
        "contentType": "player_choice_result",
        "choice_context": pending.get("context", ""),
        "player_chose": player_message,
        "result": result_narration,
    }
    result_content = json.dumps(result_data, ensure_ascii=False)

    result_history_id = generate_history_id()
    try:
        db.execute(
            "INSERT INTO session_history "
            "(sessionHistoryID, parentID, role, createdBy, content, "
            "recordCreatedTime, recordUpdatedTime) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (result_history_id, session_id, "system", "player_choice_result", result_content),
        )
    except Exception:
        traceback.print_exc()

    # Publish the choice-result message so the frontend appends a bubble.
    publisher.publish(
        "message",
        {
            "sessionID": state.get("sessionID", ""),
            "contentType": "player_choice_result",
            "content": result_content,
            "role": "system",
            "sessionHistoryID": result_history_id,
        },
    )

    try:
        db.execute(
            "UPDATE session SET sessionPendingChoice = NULL, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
            (session_id,),
        )
    except Exception:
        traceback.print_exc()

    publish_node_complete(state, "player_choice_node", "玩家选择处理完成")

    result: Dict[str, Any] = {
        "pendingPlayerChoice": None,
        "directorToDoList": updated_todos if updated_todos else [],
        "directorGraphOutput": [
            {"node": "player_choice_node", "player_choice": player_message, "result": result_narration}
        ],
        "sessionHistory": [AIMessage(content=result_content)],
    }

    logger.node_end("player_choice_node", result)
    return result