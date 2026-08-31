import json
import traceback
from typing import Any, Dict

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import fmt_env_data, fmt_node_outputs, parse_llm_json
from SQLiteClient import db_lock, get_db
from SSEPublisher import publisher

ENV_REVIEW_PROMPT = (
    """你是一个环境分析节点。
审看子节点的输出，判断场景环境数据是否有变化。

=== 本轮执行前的环境 ===
{previous_env}

=== 各子节点的输出 ===
{node_outputs}

请判断环境数据（地点/时间/氛围）是否发生变化。
如果有变化，请提供新的环境数据。

请严格按以下 JSON 格式返回，不要包含其他内容：
{{
    "env_changed": false,
    "new_env": {{"location": "地点", "time": "时间", "atmosphere": "氛围"}}
}}

注意：
- env_changed 为 true 时，new_env 必须包含所有三个字段
- 即使只有部分变化，也要提供完整的三个字段
- 场景和环境变更应仅基于本轮已发生的内容，不要自行创造新的剧情进展
"""
)


def review_env_node(state: AgentState) -> Dict[str, Any]:
    logger.node_start("review_env_node", state)

    publish_node_start(state, "review_env_node", "分析环境变化...")
    node_outputs = fmt_node_outputs(state.get("directorGraphOutput", []))
    if not node_outputs:
        return _finalize(state, {})

    db = get_db()

    prompt = build_node_prompt(
        "review_env_node",
        ENV_REVIEW_PROMPT,
        context_state=state,
        previous_env=fmt_env_data(state.get("sessionEnvData", {})),
        node_outputs=node_outputs,
    )

    messages = [
        {"role": "system", "content": "你是一个剧情分析助手，负责识别环境变化。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("review_env_node")
    params = get_node_params().get("review_env_node", {})
    try:
        response = llm.chat(
            messages,
            temperature=params.get("temperature"),
            max_tokens=params.get("max_tokens"),
            isEnableThinking=params.get("is_enable_thinking"),
            reasoning_effort=params.get("reasoning_effort"),
            max_context_tokens=params.get("max_context_tokens"),
            response_format={"type": "json_object"},
        )
        logger.log_llm("review_env_node", response, params)
    except Exception:
        logger.node_error("review_env_node")
        traceback.print_exc()
        logger.log_llm_error("review_env_node")
        return _finalize(state, {})

    result = _parse_env_response(response)
    updates: Dict[str, Any] = {}

    if result.get("env_changed"):
        new_env = result.get("new_env", {})
        if new_env and any(new_env.get(k) for k in ("location", "time", "atmosphere")):
            env_update = {
                "location": new_env.get("location", ""),
                "time": new_env.get("time", ""),
                "atmosphere": new_env.get("atmosphere", ""),
            }
            updates["sessionEnvData"] = env_update
            try:
                with db_lock:
                    db.execute(
                        "UPDATE session SET sessionEnvData = ?, recordUpdatedTime = datetime('now') WHERE sessionID = ?",
                        (json.dumps(env_update, ensure_ascii=False), state.get("sessionID", "")),
                    )
            except Exception:
                traceback.print_exc()
            publisher.publish("session_update", {"envData": env_update})

    publish_node_complete(state, "review_env_node", "环境分析完毕")
    logger.node_end("review_env_node", updates)
    return updates


def _parse_env_response(response: str) -> Dict[str, Any]:
    data = parse_llm_json(response)
    if not isinstance(data, dict):
        return {"env_changed": False, "new_env": {}}
    return {"env_changed": bool(data.get("env_changed", False)), "new_env": data.get("new_env", {})}


def _finalize(state: AgentState, updates: Dict[str, Any]) -> Dict[str, Any]:
    return updates
