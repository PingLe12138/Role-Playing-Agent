"""Plugin registry and the context object handed to plugin `setup()`.

The registry is a process-wide singleton filled during `load_plugins()`; graph
builders later pull the entries that target them.
/ 插件注册表与传给插件 setup() 的上下文对象。注册表是进程级单例，在
  load_plugins() 期间填充，图构建时由各 builder 取走属于自己的条目。
"""

import traceback
from typing import Any, Callable, Dict, List, Optional

from plugin_system.models import (
    VALID_GRAPHS,
    VALID_NODE_TYPES,
    ConditionalEdgeSpec,
    EdgeSpec,
    GraphSpec,
    NodeSpec,
    PageSpec,
    PluginLoadError,
    PluginManifest,
)


class PluginRegistry:
    """Collects everything plugins contribute. / 收集插件贡献的全部内容。"""

    def __init__(self) -> None:
        self.manifests: List[PluginManifest] = []
        self.nodes: List[NodeSpec] = []
        self.edges: List[EdgeSpec] = []
        self.conditional_edges: List[ConditionalEdgeSpec] = []
        self.graphs: List[GraphSpec] = []
        self.pages: List[PageSpec] = []
        self.errors: List[PluginLoadError] = []
        self.routers: List[Any] = []  # (APIRouter, prefix) tuples
        self.loaded: bool = False

    # ── registration ──────────────────────────────────────────────────
    def add_manifest(self, manifest: PluginManifest) -> None:
        self.manifests.append(manifest)

    def add_node(self, spec: NodeSpec) -> None:
        if spec.graph not in VALID_GRAPHS:
            raise ValueError(f"未知图 id: {spec.graph}（可选：{', '.join(VALID_GRAPHS)}）")
        if spec.node_type not in VALID_NODE_TYPES:
            spec.node_type = "plugin"
        if any(n.name == spec.name and n.graph == spec.graph for n in self.nodes):
            raise ValueError(f"节点名冲突：{spec.graph} 图上已存在 {spec.name}")
        self.nodes.append(spec)

    def add_edge(self, spec: EdgeSpec) -> None:
        if spec.graph not in VALID_GRAPHS:
            raise ValueError(f"未知图 id: {spec.graph}")
        self.edges.append(spec)

    def add_conditional_edge(self, spec: ConditionalEdgeSpec) -> None:
        if spec.graph not in VALID_GRAPHS:
            raise ValueError(f"未知图 id: {spec.graph}")
        self.conditional_edges.append(spec)

    def add_graph(self, spec: GraphSpec) -> None:
        if any(g.graph_id == spec.graph_id for g in self.graphs):
            raise ValueError(f"图 id 冲突：{spec.graph_id}")
        self.graphs.append(spec)

    def add_page(self, spec: PageSpec) -> None:
        if any(p.path == spec.path for p in self.pages):
            raise ValueError(f"前端页面路径冲突：{spec.path}")
        self.pages.append(spec)

    def add_router(self, router: Any, prefix: str) -> None:
        self.routers.append((router, prefix))

    def add_error(self, error: PluginLoadError) -> None:
        self.errors.append(error)

    def clear(self) -> None:
        """Reset every collection (used by tests and reload).
        / 清空全部集合（测试与重载使用）。
        """
        self.manifests.clear()
        self.nodes.clear()
        self.edges.clear()
        self.conditional_edges.clear()
        self.graphs.clear()
        self.pages.clear()
        self.errors.clear()
        self.routers.clear()
        self.loaded = False

    # ── queries ───────────────────────────────────────────────────────
    def nodes_for(self, graph: str) -> List[NodeSpec]:
        return [n for n in self.nodes if n.graph == graph]

    def edges_for(self, graph: str) -> List[EdgeSpec]:
        return [e for e in self.edges if e.graph == graph]

    def conditional_edges_for(self, graph: str) -> List[ConditionalEdgeSpec]:
        return [c for c in self.conditional_edges if c.graph == graph]

    def graphs_for(self, graph: str) -> List[GraphSpec]:
        return [g for g in self.graphs if g.mount_to == graph]

    def as_dict(self) -> Dict[str, Any]:
        """Serialisable summary for `GET /api/plugins`."""
        return {
            "plugins": [
                {
                    "id": m.id,
                    "name": m.name,
                    "version": m.version,
                    "description": m.description,
                    "author": m.author,
                    "enabled": m.enabled,
                }
                for m in self.manifests
            ],
            "nodes": [
                {"name": n.name, "graph": n.graph, "label": n.label or n.name, "type": n.node_type, "plugin": n.plugin_id}
                for n in self.nodes
            ],
            "graphs": [
                {"id": g.graph_id, "title": g.title, "mount_to": g.mount_to, "plugin": g.plugin_id}
                for g in self.graphs
            ],
            "pages": [
                {
                    "path": p.path,
                    "title": p.title,
                    "plugin": p.plugin_id,
                    "component": p.component,
                    "icon": p.icon,
                }
                for p in self.pages
            ],
            "errors": [
                {"plugin": e.plugin_id, "stage": e.stage, "message": e.message} for e in self.errors
            ],
        }


# Process-wide registry singleton. / 进程级注册表单例。
registry = PluginRegistry()


class PluginContext:
    """Handed to each plugin's `setup()` entry point.

    All `graph` arguments select the target graph: "director" (role-play loop)
    or "supervisor" (top-level router).
    / 传给插件 setup() 的上下文。所有 graph 参数指定目标图："director"
      （角色扮演循环）或 "supervisor"（顶层调度）。
    """

    def __init__(self, manifest: PluginManifest, reg: Optional[PluginRegistry] = None) -> None:
        self.manifest = manifest
        self._reg = reg or registry

    @property
    def plugin_id(self) -> str:
        return self.manifest.id

    def register_node(
        self,
        name: str,
        func: Callable,
        *,
        graph: str = "director",
        label: Optional[str] = None,
        node_type: str = "plugin",
        after: Optional[str] = None,
        before: Optional[str] = None,
        fanout_from: Optional[str] = None,
        fanout_to: Optional[str] = None,
    ) -> None:
        """Register a node, optionally wiring it into the graph.

        Mounting hints (mutually exclusive):
          after=X        — insert between X and X's former successors (serial)
          before=X       — insert between X's predecessors and X (serial)
          fanout_from=X  — run in parallel with X's successors, join at fanout_to

        Note: `after` a node that is a conditional-branch source moves the
        branch onto the new node, which changes super-step boundaries and may
        surface concurrent-state writes.  Prefer `before` or fan-out in that
        case. / 注意：after 一个条件分支源节点会把分支迁移到新节点上，改变超步
        边界并可能触发并发状态写入，此时优先用 before 或扇出。
        """
        hints = [h for h in (after, before, fanout_from) if h]
        if len(hints) > 1:
            raise ValueError("after / before / fanout_from 只能指定其一")
        self._reg.add_node(
            NodeSpec(
                name=name,
                func=func,
                graph=graph,
                label=label,
                node_type=node_type,
                after=after,
                before=before,
                fanout_from=fanout_from,
                fanout_to=fanout_to,
                plugin_id=self.plugin_id,
            )
        )

    def register_edge(self, source: str, target: str, *, graph: str = "director") -> None:
        """Add a plain edge (source/target may be built-in or plugin nodes)."""
        self._reg.add_edge(EdgeSpec(source=source, target=target, graph=graph, plugin_id=self.plugin_id))

    def register_conditional_edge(
        self, source: str, router: Callable, mapping: Dict[Any, str], *, graph: str = "director"
    ) -> None:
        """Add a conditional edge: `router(state) -> mapping[key] -> target`."""
        self._reg.add_conditional_edge(
            ConditionalEdgeSpec(
                source=source, router=router, mapping=dict(mapping or {}), graph=graph, plugin_id=self.plugin_id
            )
        )

    def register_graph(
        self,
        graph_id: str,
        build_fn: Callable,
        *,
        title: str = "",
        parent: Optional[str] = None,
        mount_to: str = "supervisor",
        mount_after: Optional[str] = None,
        label: Optional[str] = None,
    ) -> None:
        """Register a whole graph; it is compiled and mounted as a sub-graph node.

        `build_fn()` must return an **uncompiled** `StateGraph` sharing the
        project's AgentState (or a compatible subset).
        / 注册完整图：框架编译后作为子图节点挂载。build_fn() 必须返回未编译的
          StateGraph，且使用本项目的 AgentState（或兼容子集）。
        """
        self._reg.add_graph(
            GraphSpec(
                graph_id=graph_id,
                build_fn=build_fn,
                title=title or graph_id,
                parent=parent,
                mount_to=mount_to,
                mount_after=mount_after,
                label=label,
                plugin_id=self.plugin_id,
            )
        )

    def register_router(self, router: Any, *, prefix: Optional[str] = None) -> None:
        """Mount a FastAPI APIRouter under `/api/plugins/<plugin_id>` by default.

        The auth middleware guards every /api/* path, so plugin endpoints are
        protected the same way as built-ins.
        / 默认挂载到 /api/plugins/<plugin_id> 下；认证中间件保护所有 /api/*，
          插件端点与内置端点同样受保护。
        """
        self._reg.add_router(router, prefix or f"/api/plugins/{self.plugin_id}")

    def register_page(self, path: str, title: str, *, component: str = "ui/Index.vue", icon: str = "Plugin") -> None:
        """Declare a frontend page (resolved by Vite's plugin glob at build time)."""
        self._reg.add_page(
            PageSpec(plugin_id=self.plugin_id, path=path, title=title, component=component, icon=icon)
        )

    def add_error(self, message: str, stage: str = "setup") -> None:
        """Record a non-fatal problem; the plugin stays disabled for that part."""
        self._reg.add_error(
            PluginLoadError(
                plugin_id=self.plugin_id,
                directory=self.manifest.directory,
                message=message,
                stage=stage,
            )
        )

    @staticmethod
    def format_exception(exc: BaseException) -> str:
        return "".join(traceback.format_exception_only(type(exc), exc)).strip()
