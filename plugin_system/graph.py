"""Applying plugin contributions to a not-yet-compiled graph builder.

Both built-in graphs are assembled by `build_*_graph()` functions that return
an **uncompiled** StateGraph, so plugins may still mutate it (they cannot touch
a compiled graph).  This module owns that mutation.
/ 把插件贡献应用到尚未编译的 builder 上。两个内置图都由 build_*_graph() 返回
  未编译的 StateGraph，因此插件仍可改动它（编译后不可改）。本模块负责这些改动。

LangGraph 1.2 exposes the pre-compile structure as:
  builder.nodes    -> dict[str, StateNodeSpec]
  builder.edges    -> set[tuple[str, str]]        (plain edges)
  builder.branches -> dict[str, dict[str, Branch]] (conditional edges per source)
There is no public remove_edge(), so insertion rewrites these containers
directly.  Verified against langgraph 1.2.9: mid-chain insertion, fan-out and
tail insertion all compile and execute as expected.
/ LangGraph 1.2 的编译前结构如上（无公开 remove_edge），因此插入操作直接改写
  这些容器。已在 langgraph 1.2.9 上验证：链路中间插入、扇出、尾部追加均可
  正常编译执行。
"""

import traceback
from typing import Any, Dict, Iterable, List, Tuple

from plugin_system.models import PluginLoadError
from plugin_system.registry import PluginRegistry

# Sentinel ids used inside builder.edges / builder.branches.
# / builder.edges / branches 中使用的哨兵 id。
START_ID = "__start__"
END_ID = "__end__"


def _iter_edges(builder) -> List[Tuple[str, str]]:
    return list(getattr(builder, "edges", set()))


def _insert_after(builder, anchor: str, new_node: str) -> None:
    """Insert `new_node` between `anchor` and everything `anchor` pointed at.

    anchor → X            becomes   anchor → new → X
    anchor → X1, X2       becomes   anchor → new; new → X1, new → X2

    If `anchor` carries conditional branches, the branch (its router and path
    map) moves onto `new_node`, i.e. the plugin node runs *before* the router.
    That shifts super-step boundaries; only do it when the state fields written
    by the two branches are reducer-backed.
    / 把 new_node 插在 anchor 与它原有后继之间。若 anchor 带条件分支，分支
      （router 与 path map）会迁移到 new_node 上，即插件节点先于路由器执行——
      这会移动超步边界，仅当两个分支写入的状态字段带归约器时才安全。
    """
    targets: List[str] = []
    for src, dst in _iter_edges(builder):
        if src == anchor:
            builder.edges.discard((src, dst))
            targets.append(dst)

    for dst in targets:
        builder.edges.add((anchor, new_node))
        builder.edges.add((new_node, dst))

    if not targets:
        # anchor had no plain outgoing edges (e.g. only conditional ones).
        # / anchor 没有普通出边（例如只有条件边）。
        builder.edges.add((anchor, new_node))

    branches = getattr(builder, "branches", {}) or {}
    if anchor in branches:
        branches[new_node] = branches.pop(anchor)


def _insert_before(builder, anchor: str, new_node: str) -> None:
    """Insert `new_node` between everything pointing at `anchor` and `anchor`.

    X → anchor            becomes   X → new → anchor
    Conditional branches that resolved to `anchor` are retargeted to `new_node`,
    which keeps the branch source (and therefore the super-step) unchanged —
    this is the safer mounting mode.
    / 把 new_node 插在指向 anchor 的边与 anchor 之间。条件分支中目标为 anchor
      的项改写为 new_node，分支源（进而超步）保持不变——这是更安全的挂载方式。
    """
    sources: List[str] = []
    for src, dst in _iter_edges(builder):
        if dst == anchor:
            builder.edges.discard((src, dst))
            sources.append(src)

    for src in sources:
        builder.edges.add((src, new_node))
    builder.edges.add((new_node, anchor))

    for _src, branch_map in (getattr(builder, "branches", {}) or {}).items():
        for _name, branch in branch_map.items():
            ends = getattr(branch, "ends", None)
            if isinstance(ends, dict) and anchor in ends.values():
                branch.ends = {k: (new_node if v == anchor else v) for k, v in ends.items()}


def _fanout(builder, source: str, new_node: str, join_at: str = "") -> None:
    """Run `new_node` in parallel with `source`'s existing successors.

    source → X  (kept)  and  source → new_node (added); when `join_at` is given
    the new node also points there, forming a fan-out / fan-in pair.
    / 让 new_node 与 source 的既有后继并行：保留 source → X，新增
      source → new_node；给定 join_at 时再指向汇合点，形成扇出/扇入。
    """
    builder.edges.add((source, new_node))
    if join_at:
        builder.edges.add((new_node, join_at))


def apply_plugins(builder, graph_id: str, reg: PluginRegistry = None) -> List[str]:
    """Apply every plugin contribution targeting `graph_id` to `builder`.

    Returns the list of mounted element names (for logging / topology).
    Each contribution is applied in isolation: a failing plugin item is recorded
    as a load error and skipped, so one broken plugin cannot break the graph.
    / 把指向 graph_id 的全部插件贡献应用到 builder 上，返回已挂载元素名清单。
      每项独立应用：失败项记录为加载错误并跳过，单个插件出错不会破坏整图。
    """
    if reg is None:
        from plugin_system.registry import registry as _registry

        reg = _registry

    if not reg.loaded:
        # Idempotent safety net: graph modules can be imported before the app
        # had a chance to call load_plugins().
        # / 幂等兜底：图模块可能在应用调用 load_plugins() 之前就被导入。
        from plugin_system.loader import load_plugins

        load_plugins(reg=reg)

    mounted: List[str] = []

    # 1) Sub-graphs first — nodes/edges may reference them by id.
    # / 先处理子图：后续节点/边可能引用子图 id。
    for spec in reg.graphs_for(graph_id):
        try:
            sub = spec.compiled
            if sub is None:
                sub = spec.build_fn()
                if hasattr(sub, "compile"):
                    sub = sub.compile()
                spec.compiled = sub
            builder.add_node(spec.graph_id, sub)
            if spec.mount_after:
                _insert_after(builder, spec.mount_after, spec.graph_id)
            mounted.append(spec.graph_id)
        except Exception as exc:  # noqa: BLE001 - plugin isolation
            reg.add_error(
                PluginLoadError(
                    plugin_id=spec.plugin_id,
                    directory="",
                    message=f"挂载子图 {spec.graph_id} 失败：{exc}",
                    stage="mount",
                )
            )

    # 2) Nodes (with their mounting hint).
    for spec in reg.nodes_for(graph_id):
        try:
            builder.add_node(spec.name, spec.func)
            if spec.after:
                _insert_after(builder, spec.after, spec.name)
            elif spec.before:
                _insert_before(builder, spec.before, spec.name)
            elif spec.fanout_from:
                _fanout(builder, spec.fanout_from, spec.name, spec.fanout_to or "")
            else:
                # Registered without wiring — the plugin is expected to add its
                # own edges; warn so it does not silently become an orphan.
                # / 未连线注册：预期插件自行补边，告警以免静默变成孤立节点。
                print(f"[plugin_system] 警告：节点 {spec.name} 未指定挂载方式且尚未连线", flush=True)
            mounted.append(spec.name)
        except Exception as exc:  # noqa: BLE001
            reg.add_error(
                PluginLoadError(
                    plugin_id=spec.plugin_id,
                    directory="",
                    message=f"挂载节点 {spec.name} 失败：{exc}",
                    stage="mount",
                )
            )

    # 3) Explicit edges / conditional edges.
    for spec in reg.edges_for(graph_id):
        try:
            builder.add_edge(spec.source, spec.target)
            mounted.append(f"{spec.source}->{spec.target}")
        except Exception as exc:  # noqa: BLE001
            reg.add_error(
                PluginLoadError(
                    plugin_id=spec.plugin_id,
                    directory="",
                    message=f"挂载边 {spec.source}->{spec.target} 失败：{exc}",
                    stage="mount",
                )
            )

    for spec in reg.conditional_edges_for(graph_id):
        try:
            builder.add_conditional_edges(spec.source, spec.router, spec.mapping)
            mounted.append(f"{spec.source}-?->")
        except Exception as exc:  # noqa: BLE001
            reg.add_error(
                PluginLoadError(
                    plugin_id=spec.plugin_id,
                    directory="",
                    message=f"挂载条件边 {spec.source} 失败：{exc}",
                    stage="mount",
                )
            )

    return mounted


def plugin_labels(reg: PluginRegistry = None) -> Dict[str, Dict[str, str]]:
    """Label / type lookup for plugin-contributed nodes, for the topology API.
    / 供拓扑端点查询插件节点的中文名与类型。"""
    if reg is None:
        from plugin_system.registry import registry as _registry

        reg = _registry
    out: Dict[str, Dict[str, str]] = {}
    for spec in reg.nodes:
        out[spec.name] = {"label": spec.label or spec.name, "type": spec.node_type}
    for spec in reg.graphs:
        out[spec.graph_id] = {"label": spec.label or spec.title or spec.graph_id, "type": "subgraph"}
    return out


def format_mount_error(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()
