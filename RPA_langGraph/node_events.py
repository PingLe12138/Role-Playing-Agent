"""SSE node lifecycle event helpers.

Every graph node currently publishes a `node_start` and `node_complete` event
with the same three-field payload:
/ 每个图节点都会发布 `node_start` 与 `node_complete` 事件，载荷均为相同的三字段：

    {"node": <name>, "sessionID": <sid>, "status": <text>}

Centralising the payload construction here keeps the event shape consistent
across the ~14 nodes and removes ~30 hand-written dict literals.
/ 在此集中构造载荷可让约 14 个节点的事件结构保持一致，并消除约 30 处手写字典。
Nodes that publish other events (`message`, `session_update`, `player_choice`,
...) still import `publisher` directly — only the lifecycle events go through
these helpers.
/ 仍需发布其他事件（message、session_update、player_choice 等）的节点
仍直接导入 `publisher`——此处仅接管生命周期事件。
"""

from typing import Any, Dict

from SSEPublisher import publisher


def _payload(state: Dict[str, Any], node_name: str, status: str, **extra: Any) -> Dict[str, Any]:
    payload = {
        "node": node_name,
        "sessionID": state.get("sessionID", ""),
        "status": status,
    }
    payload.update(extra)
    return payload


def publish_node_start(state: Dict[str, Any], node_name: str, status: str = "", **extra: Any) -> None:
    """Publish the `node_start` lifecycle event.
    / 发布 `node_start` 生命周期事件。

    Extra keyword args are merged into the payload (used by `actor_node`, which
    adds a `character=<id>` field for the frontend).
    / 额外的关键字参数会被合并进载荷（actor_node 用它附加 `character=<id>` 字段）。
    """
    publisher.publish("node_start", _payload(state, node_name, status, **extra))


def publish_node_complete(state: Dict[str, Any], node_name: str, status: str = "", **extra: Any) -> None:
    """Publish the `node_complete` lifecycle event.
    / 发布 `node_complete` 生命周期事件。"""
    publisher.publish("node_complete", _payload(state, node_name, status, **extra))