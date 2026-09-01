"""Plugin discovery and loading.

Plugins live in `<project root>/plugins/<dir>/`, each holding:
  plugin.json   — manifest (id / name / version / entry / enabled / frontend)
  __init__.py   — `setup(ctx)` entry called at load time
  ui/*.vue      — optional frontend page, picked up by Vite's plugin glob

Loading happens once at process start (before the graph modules are imported,
because those compile at import time).  Every stage is failure-isolated: a
plugin that crashes is recorded in `registry.errors` and skipped.
/ 插件位于 `<项目根>/plugins/<目录>/`，加载在进程启动时一次性完成（须早于图模块
  导入，因为图在导入时编译）。各阶段均做故障隔离：出错的插件记录到
  registry.errors 并跳过。
"""

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import paths

from plugin_system.models import PluginLoadError, PluginManifest
from plugin_system.registry import PluginContext, PluginRegistry

PLUGINS_DIR = paths.PROJECT_ROOT / "plugins"

# Namespace prefix for imported plugin packages (keeps them out of the top-level
# module namespace and avoids clashes with project modules).
# / 插件包的导入命名空间前缀（避免与项目模块重名）。
_PKG_PREFIX = "rpa_plugins"

_REQUIRED_FIELDS = ("id", "name")


def plugins_dir(custom: Optional[str] = None) -> Path:
    """Resolve the plugins directory (config.json `plugins.dir` may override)."""
    if custom:
        return Path(custom)
    try:
        from config_loader import load_config

        configured = (load_config().get("plugins") or {}).get("dir")
        if configured:
            p = Path(configured)
            return p if p.is_absolute() else (paths.PROJECT_ROOT / p)
    except Exception:  # noqa: BLE001 - config may be missing during tests
        pass
    return PLUGINS_DIR


def _disabled_ids() -> set:
    """Plugin ids disabled via config.json `plugins.disabled` (optional)."""
    try:
        from config_loader import load_config

        return set((load_config().get("plugins") or {}).get("disabled") or [])
    except Exception:  # noqa: BLE001
        return set()


def _parse_manifest(path: Path, directory: Path) -> PluginManifest:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("plugin.json 内容必须为 JSON 对象")
    missing = [k for k in _REQUIRED_FIELDS if not str(raw.get(k) or "").strip()]
    if missing:
        raise ValueError(f"plugin.json 缺少必填字段：{', '.join(missing)}")
    return PluginManifest(
        id=str(raw["id"]).strip(),
        name=str(raw["name"]).strip(),
        version=str(raw.get("version") or "0.1.0"),
        description=str(raw.get("description") or ""),
        author=str(raw.get("author") or ""),
        entry=str(raw.get("entry") or "setup"),
        enabled=bool(raw.get("enabled", True)),
        directory=str(directory),
        frontend=raw.get("frontend") if isinstance(raw.get("frontend"), dict) else None,
    )


def discover(base_dir: Optional[str] = None) -> Tuple[List[PluginManifest], List[PluginLoadError]]:
    """Scan the plugins directory for manifests. / 扫描插件目录收集清单。"""
    base = plugins_dir(base_dir)
    manifests: List[PluginManifest] = []
    errors: List[PluginLoadError] = []
    if not base.is_dir():
        return manifests, errors

    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        manifest_path = child / "plugin.json"
        if not manifest_path.is_file():
            continue
        try:
            manifests.append(_parse_manifest(manifest_path, child))
        except Exception as exc:  # noqa: BLE001
            errors.append(
                PluginLoadError(
                    plugin_id=child.name, directory=str(child), message=f"清单解析失败：{exc}", stage="manifest"
                )
            )
    return manifests, errors


def _import_plugin(manifest: PluginManifest, directory: Path):
    """Import a plugin package by path so directory names may contain dashes."""
    init_file = directory / "__init__.py"
    if not init_file.is_file():
        raise FileNotFoundError(f"缺少入口文件：{init_file}")

    pkg_name = f"{_PKG_PREFIX}.{manifest.id.replace('-', '_')}"
    # Let the plugin import its own submodules both absolutely and relatively.
    # / 允许插件内以绝对或相对方式导入自己的子模块。
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

    spec = importlib.util.spec_from_file_location(
        pkg_name, init_file, submodule_search_locations=[str(directory)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为插件 {manifest.id} 构造 import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = module
    spec.loader.exec_module(module)
    return module


def load_plugins(
    base_dir: Optional[str] = None,
    *,
    reg: Optional[PluginRegistry] = None,
    force: bool = False,
) -> PluginRegistry:
    """Discover, import and set up every enabled plugin (idempotent).

    Returns the registry; `force=True` re-scans even if already loaded.
    / 发现、导入并执行所有启用插件的 setup（幂等）。force=True 时强制重新扫描。
    """
    if reg is None:
        from plugin_system.registry import registry as _registry

        reg = _registry

    if reg.loaded and not force:
        return reg

    manifests, errors = discover(base_dir)
    for err in errors:
        reg.add_error(err)

    disabled = _disabled_ids()

    for manifest in manifests:
        if manifest.id in disabled:
            continue  # 被配置禁用
        if not manifest.enabled:
            continue  # 清单自带 enabled=false

        ctx = PluginContext(manifest, reg)
        try:
            module = _import_plugin(manifest, Path(manifest.directory))
        except Exception as exc:  # noqa: BLE001
            reg.add_error(
                PluginLoadError(
                    plugin_id=manifest.id,
                    directory=manifest.directory,
                    message=f"导入失败：{exc}",
                    stage="import",
                )
            )
            continue

        entry = getattr(module, manifest.entry, None)
        if entry is None or not callable(entry):
            reg.add_error(
                PluginLoadError(
                    plugin_id=manifest.id,
                    directory=manifest.directory,
                    message=f"入口函数 {manifest.entry} 不存在或不可调用",
                    stage="setup",
                )
            )
            continue

        try:
            entry(ctx)
        except Exception as exc:  # noqa: BLE001
            reg.add_error(
                PluginLoadError(
                    plugin_id=manifest.id,
                    directory=manifest.directory,
                    message=f"setup 执行失败：{PluginContext.format_exception(exc)}",
                    stage="setup",
                )
            )
            continue

        # Manifest-declared frontend page is auto-registered unless the plugin
        # already declared the same path itself.
        # / 清单声明的前端页自动注册（插件若已自行注册同路径则跳过）。
        if manifest.frontend:
            try:
                if not any(p.path == manifest.frontend.get("path") for p in reg.pages):
                    ctx.register_page(
                        path=manifest.frontend.get("path") or f"/plugins/{manifest.id}",
                        title=manifest.frontend.get("title") or manifest.name,
                        component=manifest.frontend.get("component") or "ui/Index.vue",
                        icon=manifest.frontend.get("icon") or "Plugin",
                    )
            except Exception as exc:  # noqa: BLE001
                reg.add_error(
                    PluginLoadError(
                        plugin_id=manifest.id,
                        directory=manifest.directory,
                        message=f"前端页面注册失败：{exc}",
                        stage="setup",
                    )
                )

        reg.add_manifest(manifest)
        print(f"[plugin_system] 已加载插件 {manifest.id} v{manifest.version}", flush=True)

    reg.loaded = True
    if reg.errors:
        for err in reg.errors:
            print(f"[plugin_system] 插件 {err.plugin_id} 加载错误（{err.stage}）：{err.message}", flush=True)
    return reg


def reset_plugins(reg: Optional[PluginRegistry] = None, *, purge_modules: bool = False) -> None:
    """Clear the registry (tests / reload). / 清空注册表（测试或重载用）。"""
    if reg is None:
        from plugin_system.registry import registry as _registry

        reg = _registry
    if purge_modules:
        for name in list(sys.modules):
            if name == _PKG_PREFIX or name.startswith(_PKG_PREFIX + "."):
                sys.modules.pop(name, None)
    reg.clear()
