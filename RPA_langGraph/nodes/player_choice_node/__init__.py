"""Player-choice HITL node: dispatches between generate mode (decide whether the
player needs a choice, then block) and resume mode (process a previously pending
choice).

/ 玩家选择 HITL 节点：在生成模式（判断是否需要玩家选择并阻塞）与恢复模式
  （处理先前挂起的选择）之间分发。

Public exports kept stable so existing imports still work:
  * `player_choice_node` — the LangGraph node function.
  * `PLAYER_CHOICE_PROMPT` — the default generate-mode prompt (used by the config API).
/ 保持公开导出稳定，使既有导入仍可用：
  * `player_choice_node` — LangGraph 节点函数。
  * `PLAYER_CHOICE_PROMPT` — 生成模式的默认提示词（被配置 API 使用）。
"""

from typing import Dict, Optional

from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.nodes.player_choice_node._common import PLAYER_CHOICE_PROMPT  # noqa: F401  (re-export)
from RPA_langGraph.nodes.player_choice_node._generate import _generate_choice
from RPA_langGraph.nodes.player_choice_node._process import _process_choice

__all__ = ["player_choice_node", "PLAYER_CHOICE_PROMPT"]


def player_choice_node(state: AgentState) -> Dict[str, Optional[object]]:
    """Player choice node: dispatch to generate or resume mode.
    / 玩家选择节点：分发到生成模式或恢复模式。

    When the graph is invoked with a pendingPlayerChoice (phase="awaiting_player"),
    we skip the LLM "does the player need a choice?" evaluation and go straight
    to processing the player's answer — either from the live thread waiter
    or from the most recent human message in the dialogue history.
    / 当图调用时 state 中携带了 pendingPlayerChoice（phase="awaiting_player"），
      我们跳过 LLM 的"是否需要玩家选择"评估，直接去处理玩家的回答——
      可能来自实时线程等待器，也可能来自对话历史中最近的人类消息。
    """
    pending: Optional[dict] = state.get("pendingPlayerChoice")

    if pending and pending.get("phase") == "awaiting_player":
        # Resume mode: process player's choice
        return _process_choice(state, pending)
    else:
        # Generate mode: evaluate if choice is needed
        return _generate_choice(state)