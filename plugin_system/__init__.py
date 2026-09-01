"""Plugin system for the RPG narrative engine.

Plugins can contribute new **nodes**, new **edges** and whole new **graphs** to
the built-in LangGraph pipelines, plus REST routers and frontend pages.
/ RPG 叙事引擎插件系统：插件可向内置 LangGraph 流水线贡献新节点、新边与完整
  新图，并可提供 REST 路由与前端页面。

Typical usage in a plugin's `__init__.py`:
/ 插件 __init__.py 中的典型用法：

    def setup(ctx):
        ctx.register_node("my_node", my_node_func, graph="director",
                          label="我的节点", after="director_node")
        ctx.register_page("/plugins/my", title="我的插件")

Loading happens once at startup, before the graph modules are imported (those
compile at import time): `load_plugins()` in `app.py`.
/ 启动时在导入图模块之前加载一次（图在导入时编译）：见 app.py 中的
  load_plugins() 调用。
"""

from plugin_system.graph import apply_plugins, plugin_labels
from plugin_system.loader import discover, load_plugins, plugins_dir, reset_plugins
from plugin_system.models import (
    GRAPH_DIRECTOR,
    GRAPH_SUPERVISOR,
    ConditionalEdgeSpec,
    EdgeSpec,
    GraphSpec,
    NodeSpec,
    PageSpec,
    PluginLoadError,
    PluginManifest,
)
from plugin_system.registry import PluginContext, PluginRegistry, registry

__all__ = [
    "GRAPH_DIRECTOR",
    "GRAPH_SUPERVISOR",
    "ConditionalEdgeSpec",
    "EdgeSpec",
    "GraphSpec",
    "NodeSpec",
    "PageSpec",
    "PluginContext",
    "PluginLoadError",
    "PluginManifest",
    "PluginRegistry",
    "apply_plugins",
    "discover",
    "load_plugins",
    "plugins_dir",
    "plugin_labels",
    "registry",
    "reset_plugins",
]
