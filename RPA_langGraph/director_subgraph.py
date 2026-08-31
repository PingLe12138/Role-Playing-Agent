"""Director subgraph — the core role-play loop within a single user turn.
/ Director 子图——单个用户轮次内的核心角色扮演循环。

The subgraph is entered whenever the supervisor classifies the user's input
as role-playing ("director").  It executes these phases in order:
/ 当 supervisor 将用户输入分类为角色扮演（"director"）时进入本子图。按顺序执行以下阶段：

  1. Recall phase: recall_node → introduce_character_node → director_node
       Check if the player is recalling a departed character; generate a
       TODO list (actor / narration / outline items) for the current turn.
     / 召回阶段：检查玩家是否在召回已离场角色；为当前轮次生成 TODO 列表。
  2. Execution phase (parallel waves):
       route_next_todo picks the first uncompleted TODO; then
         actor_batch_node  — ALL uncompleted actor TODOs run in parallel
                           (one LLM call per character, results merged in
                           TODO order) → player_choice_node (may block)
         note_batch_node   — remaining narration/outline TODOs run in
                           parallel → route_next_todo
     / 执行阶段（并行波浪）：取第一个未完成的 TODO 后——
       actor_batch_node：所有未完成 actor TODO 并行执行（每角色一次 LLM，
                         按 TODO 顺序合并结果）→ 玩家选择节点（可能阻塞）；
       note_batch_node：剩余 narration/outline TODO 并行执行 → 回到取 TODO。
  3. Review chain (after all TODOs are done):
       review_start fans out in parallel to
         review_character_node (finalizes the present roster) and
         review_env_node (environment diff)
       then update_relationship_node ‖ review_departure_node (fan-in join)
       → conditionally memory_node (if memoryRoundCounter % interval == 0) → END
     / 审看链（所有 TODO 完成后）：review_start 并行扇出到角色审看（确定最终
       在场名单）与环境审看；随后关系更新 ‖ 离场处理（扇入汇合），
       条件触发记忆总结。

If a pending player_choice exists (e.g. page-refresh resume), the subgraph
skips recall/director and goes straight to player_choice_node.
/ 如果存在待处理的玩家选择（如刷新页面后恢复），子图跳过回忆/导演阶段直接进入选择节点。
"""

from langgraph.graph import END, START, StateGraph

from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.nodes.director_node import director_node
from RPA_langGraph.nodes.image_gen_node import image_gen_node
from RPA_langGraph.nodes.introduce_character_node import introduce_character_node
from RPA_langGraph.nodes.memory_node import memory_node
from RPA_langGraph.nodes.player_choice_node import player_choice_node
from RPA_langGraph.nodes.recall_node import recall_node
from RPA_langGraph.nodes.review_character_node import review_character_node
from RPA_langGraph.nodes.review_departure_node import review_departure_node
from RPA_langGraph.nodes.review_env_node import review_env_node
from RPA_langGraph.nodes.todo_batch_node import actor_batch_node, note_batch_node
from RPA_langGraph.nodes.update_relationship_node import update_relationship_node


def route_director_entry(state: AgentState) -> str:
    """Entry point routing for the director subgraph.
    / Director 子图的入口路由。

    If the state carries a pending player choice (e.g. resumed after a page
    refresh or server restart), skip recall/director and go straight to
    player_choice_node in resume mode.  Otherwise start the normal flow.
    / 如果 state 中包含待处理的玩家选择（如刷新页面或重启服务后恢复），
      跳过 recall/director 阶段，直接进入 player_choice_node 的恢复模式；
      否则按正常流程启动。
    """
    pending = state.get("pendingPlayerChoice")
    if pending and pending.get("phase") == "awaiting_player":
        return "player_choice_node"
    return "recall_node"


def route_next_todo(state: AgentState) -> dict:
    """Pick the first uncompleted TODO and set it as directorCurrentTask.
    / 选取第一个未完成的 TODO，将其设为 directorCurrentTask。
    """
    for todo in state["directorToDoList"]:
        if not todo["isCompleted"]:
            return {"directorCurrentTask": todo}
    return {"directorCurrentTask": None}


def route_after_todo(state: AgentState) -> str:
    """Route to the batch node indicated by the first uncompleted TODO, or
    "review" if every TODO is done.
    / 根据第一个未完成 TODO 路由到对应批处理节点；没有剩余 TODO 则进入审看链。
    """
    task = state.get("directorCurrentTask")
    if task is None:
        return "review"
    return task["targetNode"]


def route_after_player_choice(state: AgentState) -> str:
    """After player_choice_node: end subgraph if still awaiting player.
    / player_choice_node 之后：如果仍在等待玩家选择则结束子图。

    When the choice panel is shown and the player hasn't answered yet,
    pendingPlayerChoice.phase stays "awaiting_player" and we exit the
    subgraph so the supervisor can check for remaining TODOs (there
    shouldn't be any — the choice blocks until answered).
    / 当显示选择面板且玩家尚未响应时，pendingPlayerChoice.phase 仍为
      "awaiting_player"，此时退出子图让 supervisor 检查剩余 TODO（实际上
      不应有剩余——选择会阻塞直到玩家响应）。
    """
    pending = state.get("pendingPlayerChoice")
    if pending and pending.get("phase") == "awaiting_player":
        return "__end__"
    return "route_next_todo"


def route_after_review(state: AgentState) -> str:
    """After the review chain: conditionally run memory node, then always run
    the scene-image node (final step of the subgraph).
    / 审看链之后：条件触发记忆节点，然后始终执行场景插画节点（子图最后一步）。

    Memory summarization runs every N turns (memorySummarizeInterval, default 10).
    memoryRoundCounter is incremented by review_departure_node after each departure.
    / 记忆总结每隔 N 轮运行一次（memorySummarizeInterval，默认 10）。
      memoryRoundCounter 由 review_departure_node 在每次角色离场后递增。
    """
    counter = state.get("memoryRoundCounter", 0)
    interval = state.get("memorySummarizeInterval", 10)
    if interval > 0 and counter > 0 and counter % interval == 0:
        return "memory_node"
    return "image_gen_node"


def review_start(state: AgentState) -> dict:
    """Structural dispatcher at the head of the review chain: a no-op node
    whose two plain edges fan out to review_character_node and review_env_node
    in the same super-step (review_env does not depend on the finalized
    roster, so it can start immediately).

    / 审查链入口的结构分发节点：无操作，用两条普通边在同一超步并行扇出到
      角色审看与环境审看（环境审看不依赖最终在场名单，可立即启动）。
    """
    return {}


def build_director_subgraph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("recall_node", recall_node)
    builder.add_node("introduce_character_node", introduce_character_node)
    builder.add_node("director_node", director_node)
    builder.add_node("route_next_todo", route_next_todo)
    builder.add_node("actor_batch_node", actor_batch_node)
    builder.add_node("note_batch_node", note_batch_node)
    builder.add_node("player_choice_node", player_choice_node)
    builder.add_node("review_env_node", review_env_node)
    builder.add_node("review_character_node", review_character_node)
    builder.add_node("update_relationship_node", update_relationship_node)
    builder.add_node("review_departure_node", review_departure_node)
    builder.add_node("review_start", review_start)
    builder.add_node("memory_node", memory_node)
    builder.add_node("image_gen_node", image_gen_node)

    # Entry routing: check for pending choice
    builder.add_conditional_edges(
        START, route_director_entry, {"player_choice_node": "player_choice_node", "recall_node": "recall_node"}
    )

    builder.add_edge("recall_node", "introduce_character_node")
    builder.add_edge("introduce_character_node", "director_node")
    builder.add_edge("director_node", "route_next_todo")

    # Execution waves: the first uncompleted TODO decides the next batch.
    # / 执行波浪：第一个未完成 TODO 决定下一波批处理节点。
    builder.add_conditional_edges(
        "route_next_todo",
        route_after_todo,
        {
            "actor": "actor_batch_node",
            "narration": "note_batch_node",
            "outline": "note_batch_node",
            "review": "review_start",
        },
    )

    # After the actor wave → player_choice_node once (single HITL check per
    # turn instead of one per actor).
    # / actor 波浪之后只进入一次玩家选择节点（每轮一次 HITL 判定，而非每角色一次）。
    builder.add_edge("actor_batch_node", "player_choice_node")

    # After player_choice_node → conditional (END if choice pending, else continue)
    builder.add_conditional_edges(
        "player_choice_node", route_after_player_choice, {"__end__": END, "route_next_todo": "route_next_todo"}
    )

    builder.add_edge("note_batch_node", "route_next_todo")

    # Review chain: review_start fans out to review_character_node and
    # review_env_node in parallel (plain multi-edge fan-out renders and runs
    # correctly in LangGraph, unlike list-returning conditional paths).
    # update_relationship_node depends on the finalized roster so it follows
    # review_character_node; review_departure_node joins via fan-in edges from
    # review_character_node and review_env_node — it runs exactly once, after
    # the character/env super-step, in parallel with the relationship update,
    # and finalizes the subgraph state.
    # / 审查链：review_start 并行扇出到角色审看与环境审看（普通多边扇出在
    #   LangGraph 中渲染与运行都正确，不同于 list 返回值条件边）。
    #   关系更新依赖最终在场名单，跟在角色审看之后；离场处理经角色审看与
    #   环境审看的扇入边汇合——只执行一次，且在角色/环境超步之后、与关系
    #   更新并行运行，并负责子图收尾清场。
    builder.add_edge("review_start", "review_character_node")
    builder.add_edge("review_start", "review_env_node")

    builder.add_edge("review_character_node", "update_relationship_node")
    builder.add_edge("review_character_node", "review_departure_node")
    builder.add_edge("review_env_node", "review_departure_node")

    # update_relationship_node has no successor state to write — its branch
    # ends here (the graph finishes only when every branch reaches END).
    # / 关系更新节点无后续状态可写，其分支在此结束（图在所有分支到达 END 后才结束）。
    builder.add_edge("update_relationship_node", END)

    builder.add_conditional_edges(
        "review_departure_node", route_after_review, {"memory_node": "memory_node", "image_gen_node": "image_gen_node"}
    )

    # Scene image generation is the final step: runs after memory (if any) and
    # then ends the subgraph. / 场景插画生成是最后一步：在记忆节点（若有）之后
    # 执行，随后结束子图。
    builder.add_edge("memory_node", "image_gen_node")
    builder.add_edge("image_gen_node", END)

    return builder


director_subgraph = build_director_subgraph().compile()
