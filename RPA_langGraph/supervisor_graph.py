"""Top-level LangGraph that orchestrates user input → role-play / narration.
/ 顶层 LangGraph 图：调度用户输入 → 角色扮演 / 叙事指令。

Flow:
  START → supervisor_node (LLM classifies input)
        → route_next_supervisor_todo (pick first uncompleted TODO)
        → route_after_supervisor_todo (conditional edge):
            "director"          → director_subgraph (full character-play cycle)
            "general_narration" → general_narration_node (one-shot narration)
        → after subgraph ends, loop back to route_next_supervisor_todo
        → no more TODOs → END
/ 流程说明：
  START → supervisor_node（LLM 分类用户输入）
        → route_next_supervisor_todo（取第一个未完成的 TODO）
        → route_after_supervisor_todo（条件边）：
            "director"          → director_subgraph（完整的角色扮演流程）
            "general_narration" → general_narration_node（一次性叙述）
        → 子图结束后回到 route_next_supervisor_todo 继续循环
        → 无剩余 TODO → END
"""

from langgraph.graph import END, START, StateGraph

from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.director_subgraph import director_subgraph
from RPA_langGraph.nodes.general_narration_node import general_narration_node
from RPA_langGraph.nodes.supervisor_node import supervisor_node


def route_next_supervisor_todo(state: AgentState) -> dict:
    for todo in state["supervisorToDoList"]:
        if not todo["isCompleted"]:
            return {"supervisorCurrentTask": todo}
    return {"supervisorCurrentTask": None, "supervisorToDoList": []}


def route_after_supervisor_todo(state: AgentState) -> str:
    task = state.get("supervisorCurrentTask")
    if task is None:
        return "__end__"
    return task["targetNode"]


def build_supervisor_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("supervisor_node", supervisor_node)
    builder.add_node("route_next_supervisor_todo", route_next_supervisor_todo)
    builder.add_node("director_subgraph", director_subgraph)
    builder.add_node("general_narration_node", general_narration_node)

    builder.add_edge(START, "supervisor_node")
    builder.add_edge("supervisor_node", "route_next_supervisor_todo")

    builder.add_conditional_edges(
        "route_next_supervisor_todo",
        route_after_supervisor_todo,
        {"director": "director_subgraph", "general_narration": "general_narration_node", "__end__": END},
    )

    builder.add_edge("director_subgraph", "route_next_supervisor_todo")
    builder.add_edge("general_narration_node", "route_next_supervisor_todo")

    return builder


supervisor_graph = build_supervisor_graph().compile()
