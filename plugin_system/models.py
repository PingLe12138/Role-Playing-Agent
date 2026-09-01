"""Data models for the plugin system.

Every plugin ships a `plugin.json` manifest plus a Python entry function that
receives a `PluginContext`.  The specs below are what the context calls produce;
they are collected in the registry and applied to the (not yet compiled) graph
builders at graph-construction time.
/ 插件系统数据模型。插件由 `plugin.json` 清单 + Python 入口函数（接收
  PluginContext）构成；下列 spec 是上下文调用产物，收集进注册表后，在图构建
  时应用到尚未编译的 builder 上。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

# Built-in graph ids that plugins may attach to.
# / 插件可挂载的内置图 id。
GRAPH_DIRECTOR = "director"
GRAPH_SUPERVISOR = "supervisor"

VALID_GRAPHS = (GRAPH_DIRECTOR, GRAPH_SUPERVISOR)

# Node type used by the topology endpoint for colouring; unknown types fall
# back to "plugin" in the UI.
# / 拓扑端点用于着色的节点类型；未知类型在前端回退为 "plugin"。
VALID_NODE_TYPES = ("llm", "router", "review", "subgraph", "plugin", "unknown")


@dataclass
class PluginManifest:
    """Parsed `plugin.json`. / 解析后的 plugin.json。

    `entry` names the callable looked up on the plugin package (default
    "setup").  `enabled: false` skips loading entirely.
    / entry 为插件包中待调用的函数名（默认 "setup"）；enabled=false 时跳过加载。
    """

    id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    entry: str = "setup"
    enabled: bool = True
    directory: str = ""  # absolute plugin dir (filled by the loader)
    # Optional frontend page: {"path", "title", "component", "icon"}
    frontend: Optional[Dict[str, str]] = None


@dataclass
class NodeSpec:
    """A node contributed by a plugin. / 插件贡献的节点。

    Exactly one mounting hint applies:
      after=X        — insert between X and everything X used to point at
      before=X       — insert between everything pointing at X and X
      fanout_from=X  — run in parallel with X's outgoing edges (join at fanout_to)

    Leaving all of them None registers the node without any edge; the plugin is
    then expected to wire it via register_edge().
    / 三者最多指定其一：after（插在 X 之后）/ before（插在 X 之前）/
      fanout_from（与 X 的出边并行，在 fanout_to 汇合）。全不指定则只注册节点，
      由插件自行用 register_edge 连线。
    """

    name: str
    func: Callable
    graph: str = GRAPH_DIRECTOR
    label: Optional[str] = None
    node_type: str = "plugin"
    after: Optional[str] = None
    before: Optional[str] = None
    fanout_from: Optional[str] = None
    fanout_to: Optional[str] = None
    plugin_id: str = ""


@dataclass
class EdgeSpec:
    """A plain edge contributed by a plugin. / 插件贡献的普通边。"""

    source: str
    target: str
    graph: str = GRAPH_DIRECTOR
    plugin_id: str = ""


@dataclass
class ConditionalEdgeSpec:
    """A conditional edge contributed by a plugin. / 插件贡献的条件边。"""

    source: str
    router: Callable
    mapping: Dict[Any, str] = field(default_factory=dict)
    graph: str = GRAPH_DIRECTOR
    plugin_id: str = ""


@dataclass
class GraphSpec:
    """A whole graph contributed by a plugin.

    `build_fn` must return an **uncompiled** `StateGraph`; the framework
    compiles it and mounts the result as a sub-graph node on `mount_to`
    (at `mount_after` when given, otherwise as a plain edge target).
    / 插件贡献的完整图。build_fn 必须返回**未编译**的 StateGraph；框架编译后
      作为子图节点挂载到 mount_to 上（给定 mount_after 时插在其后）。
    """

    graph_id: str
    build_fn: Callable
    title: str = ""
    parent: Optional[str] = None
    mount_to: str = GRAPH_SUPERVISOR
    mount_after: Optional[str] = None
    label: Optional[str] = None
    plugin_id: str = ""
    # Compiled instance cache: filled on first mount / topology read so the
    # build_fn runs at most once per process.
    # / 编译实例缓存：首次挂载或拓扑读取时填充，保证 build_fn 每进程至多执行一次。
    compiled: Any = None


@dataclass
class PageSpec:
    """A frontend page contributed by a plugin.

    `component` is a path relative to the plugin directory (e.g. "ui/Index.vue")
    and is resolved by Vite's plugin glob at build time.
    / 插件贡献的前端页面。component 为相对插件目录的路径（如 "ui/Index.vue"），
      由 Vite 的插件 glob 在构建期解析。
    """

    plugin_id: str
    path: str
    title: str
    component: str = "ui/Index.vue"
    icon: str = "Plugin"


@dataclass
class PluginLoadError:
    """A plugin that failed to load (kept so one bad plugin cannot kill boot).
    / 加载失败的插件记录（保证单个插件出错不会拖垮启动）。
    """

    plugin_id: str
    directory: str
    message: str
    stage: str  # "manifest" | "import" | "setup"
