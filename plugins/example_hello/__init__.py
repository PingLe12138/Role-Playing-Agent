"""Example plugin: demonstrates every plugin-system integration point.

/ 示例插件：演示插件系统的全部接入点。

  1. A director-graph observation node fanned out from review_start (runs in
     parallel with the review chain, joins at review_departure_node).
     一个 Director 图观测节点：从 review_start 扇出，与审查链并行，汇合于
     review_departure_node。
  2. A tiny sub-graph mounted on the supervisor after general_narration_node.
     一个极小子图，挂载到 Supervisor 的 general_narration_node 之后。
  3. A REST endpoint under /api/plugins/example_hello.
     一个 REST 端点。
  4. A frontend page declared in plugin.json (ui/Index.vue).
     plugin.json 声明的前端页面。
"""

_loaded_at = ""

# State-convention reminder: reducer-backed AgentState channels must receive
# *increments* from node returns, never a re-assembled copy of current state.
# / 状态约定提醒：带归约器的 AgentState 通道，节点返回值必须是**增量**，
#   而不是把当前状态重组后整体返回。


def turn_observer_node(state: dict) -> dict:
    """Observation node: logs this turn's node-output count; mutates nothing.

    / 观测节点：记录本轮节点输出数量，不修改任何状态。
    """
    try:
        outputs = state.get("directorGraphOutput") or []
        print(f"[example_hello] turn_observer: 本轮已有 {len(outputs)} 条节点输出", flush=True)
    except Exception:  # noqa: BLE001 - observation must never break the graph
        pass
    return {}


def build_summary_graph():
    """A minimal plugin graph sharing the project's AgentState.

    / 一个最小插件子图，复用项目 AgentState。
    """
    from langgraph.graph import END, START, StateGraph

    from RPA_langGraph.AgentState import AgentState

    def summary_marker(state: AgentState) -> dict:
        print(
            f"[example_hello] summary_marker: 会话 {state.get('sessionID', '')} 经由插件子图",
            flush=True,
        )
        return {}

    builder = StateGraph(AgentState)
    builder.add_node("summary_marker", summary_marker)
    builder.add_edge(START, "summary_marker")
    builder.add_edge("summary_marker", END)
    return builder


def create_router():
    """Build the plugin's FastAPI router (mounted under /api/plugins/example_hello).

    / 构建插件 FastAPI 路由（挂载于 /api/plugins/example_hello 之下）。
    """
    from fastapi import APIRouter

    from plugin_system import registry as plugin_registry

    router = APIRouter()

    @router.get("/hello")
    def hello():
        return {
            "message": "Hello from example_hello plugin!",
            "loaded_at": _loaded_at,
            "graph_contributions": [n.name for n in plugin_registry.nodes if n.plugin_id == "example_hello"]
            + [g.graph_id for g in plugin_registry.graphs if g.plugin_id == "example_hello"],
        }

    return router


def setup(ctx) -> None:
    """Plugin entry point. / 插件入口。"""
    global _loaded_at
    import datetime

    _loaded_at = datetime.datetime.now().isoformat(timespec="seconds")

    # 1) Director-graph node: fan out from review_start, join at the departure
    #    node — the safest mounting mode (no super-step rewrite).
    # / Director 图节点：从 review_start 扇出、汇合到离场节点——最安全的挂载方式
    #   （不改写超步结构）。
    ctx.register_node(
        "example_turn_observer",
        turn_observer_node,
        graph="director",
        label="示例：回合观测",
        node_type="plugin",
        fanout_from="review_start",
        fanout_to="review_departure_node",
    )

    # 2) Sub-graph mounted on the supervisor after the general-narration node.
    # / 子图挂载到 Supervisor 的通用叙述节点之后（普通边改写，串行安全）。
    ctx.register_graph(
        "example_summary_graph",
        build_summary_graph,
        title="示例：总结子图",
        mount_to="supervisor",
        mount_after="general_narration_node",
        label="示例总结子图",
    )

    # 3) REST endpoints. / REST 端点。
    ctx.register_router(create_router())

    # 4) The frontend page comes from plugin.json's "frontend" section and is
    #    auto-registered by the loader; it could also be declared here:
    # / 前端页面由 plugin.json 的 frontend 段自动注册；也可在此手动声明：
    #    ctx.register_page("/plugins/example-hello", title="示例插件")
