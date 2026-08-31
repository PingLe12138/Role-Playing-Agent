import json
import traceback
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, RemoveMessage

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState, ToDoItem
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import chat_json, fmt_history, parse_llm_json
from services.id_utils import generate_history_id
from SQLiteClient import get_db
from SSEPublisher import publisher

SUPERVISOR_PROMPT = (
    """你是一个角色扮演系统的调度节点 (Supervisor)。
根据对话历史和当前用户输入，判断用户输入属于哪一类。

=== 全量对话记录 ===
{history}

请分析用户最近的输入，判断属于以下哪一种，只能选一种：
1. 普通的角色扮演推进（让角色回应、发展剧情）：targetNode = "director"，extraData 为空
2. 对叙述者的指令（让生成特定情节/场景）：targetNode = "general_narration"，extraData 填入指令原文

注意：
- 两种类型是互斥的，不要同时生成多条待办
- 只有当用户输入是明确的、详细的故事情节撰写要求时（如"请写一段..." "请叙述..."），才选择第2种
- 普通的角色对话、行动描述、剧情互动等一律视为第1种
- 如有疑问，一律选择普通的角色扮演推进
- 【extraData 填写要求】选择第2种时，extraData 必须逐字完整保留用户输入的指令原文，
  禁止概括、删减、改写或截断；若指令含"继续/接着写/之后/接下来"等续写词，
  需连同续写的目标（要写到什么结果）一起保留，以便叙述者明确推进方向

请严格按以下 JSON 格式返回一条待办，不要包含其他内容：
{{"targetNode": "director", "extraData": ""}}

或者：

{{"targetNode": "general_narration", "extraData": "具体的指令内容"}}

"""
)


def _parse_supervisor_response(response: str) -> tuple[str, List[ToDoItem]]:
    data = parse_llm_json(response)
    if not isinstance(data, dict):
        return "role_playing", []

    target = data.get("targetNode", "director")
    extra = str(data.get("extraData", ""))
    valid_nodes = {"director", "general_narration"}
    if target not in valid_nodes:
        target = "director"

    content_type = "role_playing" if target == "director" else "generalNarration"
    todo_list = [ToDoItem(targetNode=target, isCompleted=False, extraData=extra)]
    return content_type, todo_list


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    # Short-circuit: if we're resuming a pending player choice, route straight
    # to the director subgraph (which will re-enter player_choice_node resume
    # mode). Don't classify the choice text — it might be e.g. "B. 攻击敌人"
    # which would be misclassified as general_narration by the LLM.
    pending = state.get("pendingPlayerChoice")
    if pending and pending.get("phase") == "awaiting_player":
        return {"supervisorToDoList": [ToDoItem(targetNode="director", isCompleted=False, extraData="")]}

    history = state.get("sessionHistory", [])
    if not history:
        return {"supervisorToDoList": []}

    last_msg = history[-1]
    if last_msg.type != "human":
        return {"supervisorToDoList": []}

    logger.node_start("supervisor_node", state)

    publish_node_start(state, "supervisor_node", "分析用户输入...")
    history_text = fmt_history(history)

    prompt = build_node_prompt(
        "supervisor_node", SUPERVISOR_PROMPT, context_state=state, history=history_text or "(空)"
    )

    messages = [
        {"role": "system", "content": "你是一个剧情调度员，负责分类用户指令并分配处理节点。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("supervisor_node")
    params = get_node_params().get("supervisor_node", {})
    try:
        _, response = chat_json(llm, messages, params)
        logger.log_llm("supervisor_node", response, params)
    except Exception:
        logger.node_error("supervisor_node")
        traceback.print_exc()
        logger.log_llm_error("supervisor_node")
        return {"supervisorToDoList": []}

    content_type, todo_list = _parse_supervisor_response(response)

    if content_type == "generalNarration":
        result = {"sessionHistory": [RemoveMessage(id=last_msg.id)], "supervisorToDoList": todo_list}
    else:
        formatted = json.dumps({"contentType": content_type, "content": last_msg.content}, ensure_ascii=False)

        new_msg = HumanMessage(id=last_msg.id, content=formatted)

        try:
            db = get_db()
            session_id = state.get("sessionID", "")
            history_id = generate_history_id()
            db.execute(
                "INSERT INTO session_history "
                "(sessionHistoryID, parentID, role, createdBy, content, "
                "recordCreatedTime, recordUpdatedTime) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (history_id, session_id, "user", "", formatted),
            )
            publisher.publish(
                "message",
                {
                    "sessionID": state.get("sessionID", ""),
                    "contentType": content_type,
                    "content": last_msg.content,
                    "role": "user",
                    "sessionHistoryID": history_id,
                },
            )
        except Exception:
            traceback.print_exc()

        result = {"sessionHistory": [new_msg], "supervisorToDoList": todo_list}

    publish_node_complete(state, "supervisor_node", "分类完成")
    logger.node_end("supervisor_node", result)
    return result
