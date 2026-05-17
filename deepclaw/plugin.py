"""插件系统 v2 — VS Code 风格架构。

- 稳定 API 契约：插件通过 DeepClawAPI 对象交互，不直接 import 内部模块
- 声明式：plugin.json 中 contributes 声明能力，activationEvents 声明激活时机
- 懒加载：非启动必加载插件按需激活，减少启动时间
- 事件驱动：插件通过 api.on() 订阅主程序事件
- 异常隔离：插件崩溃不影响主程序，标记为 failed
"""

import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Optional

from deepclaw.config import CONFIG_DIR
from deepclaw.events import EventBus
from deepclaw.api import DeepClawAPI, ToolRenderer, StatusBar

PLUGINS_DIR = CONFIG_DIR / "plugins"

# 全局状态
_event_bus = EventBus()
_status_bar = StatusBar()
_tool_renderer = ToolRenderer()
_tool_registry: dict = {}    # {tool_name: (plugin_name, tool_def, handler)}
_command_registry: dict = {} # {"/cmd": (plugin_name, handler)}

_loaded_plugins: dict = {}   # {plugin_name: PluginState}
_available_plugins: dict = {} # {plugin_name: meta} — 预扫描的元数据


class PluginState:
    def __init__(self, name: str, meta: dict, api: DeepClawAPI):
        self.name = name
        self.meta = meta
        self.api = api
        self.module = None
        self.active = False
        self.failed = False
        self.error = ""


def ensure_plugins_dir():
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


def _scan_plugins() -> dict:
    """扫描目录，缓存所有插件的 plugin.json 元数据。"""
    ensure_plugins_dir()
    result = {}
    for d in sorted(PLUGINS_DIR.iterdir()):
        if d.is_dir():
            meta_file = d / "plugin.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    meta["_dir"] = d.name
                    result[d.name] = meta
                except Exception:
                    pass
    return result


def discover_plugins() -> list[dict]:
    """返回所有可用插件元数据（公开 API）。"""
    return list(_scan_plugins().values())


def _should_activate(meta: dict, event: str, payload: str = "") -> bool:
    """根据 activationEvents 判断是否应激活该插件。"""
    events = meta.get("activationEvents", [])
    if not events or "*" in events:
        return True
    for ev in events:
        if ev == event:
            return True
        if ev.startswith("onCommand:") and payload and ev == f"onCommand:{payload}":
            return True
        if ev.startswith("onTool:") and payload and ev == f"onTool:{payload}":
            return True
        if ev == "onStartup":
            return True
    return False


def _load_module(name: str, meta: dict, api: DeepClawAPI) -> PluginState:
    """实际加载插件模块并调用 on_load。异常被捕获隔离。"""
    main_file = PLUGINS_DIR / name / "main.py"

    spec = importlib.util.spec_from_file_location(f"deepclaw_p_{name}", str(main_file))
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    state = PluginState(name, meta, api)

    try:
        spec.loader.exec_module(module)
        state.module = module
        state.active = True

        # 调用生命周期
        if hasattr(module, "on_load") and callable(module.on_load):
            module.on_load(api)
    except Exception:
        state.failed = True
        state.active = False
        state.error = traceback.format_exc()
        sys.modules.pop(spec.name, None)
        return state

    _loaded_plugins[name] = state
    return state


def activate_plugin(name: str, agent=None, event: str = "onStartup", payload: str = "") -> Optional[PluginState]:
    """激活指定插件，返回 PluginState 或 None。"""
    global _available_plugins
    if not _available_plugins:
        _available_plugins = _scan_plugins()

    if name in _loaded_plugins:
        return _loaded_plugins[name]

    meta = _available_plugins.get(name)
    if not meta:
        return None

    if not _should_activate(meta, event, payload):
        return None

    api = DeepClawAPI(
        agent=agent,
        config={},
        event_bus=_event_bus,
        tool_registry=_tool_registry,
        command_registry=_command_registry,
    )
    api.plugin_name = name
    api._DeepClawAPI__init_sub_ui(_status_bar, _tool_renderer)

    return _load_module(name, meta, api)


def unload_plugin(name: str) -> bool:
    """卸载插件：清空注册、移除工具/命令/事件、清理状态。"""
    if name not in _loaded_plugins:
        return False

    state = _loaded_plugins[name]

    # 卸载生命周期
    if state.module and hasattr(state.module, "on_unload") and callable(state.module.on_unload):
        try:
            state.module.on_unload()
        except Exception:
            pass

    # 清除事件订阅
    _event_bus.off_plugin(name)

    # 清除工具
    for tname, (pname, _, _) in list(_tool_registry.items()):
        if pname == name:
            del _tool_registry[tname]

    # 清除命令
    for cname, (pname, _) in list(_command_registry.items()):
        if pname == name:
            del _command_registry[cname]

    # 清除 UI
    _status_bar.clear(name)

    # 清理模块
    mod_name = f"deepclaw_p_{name}"
    sys.modules.pop(mod_name, None)

    del _loaded_plugins[name]
    return True


def activate_startup_plugins(agent) -> list[PluginState]:
    """激活所有声明了 onStartup 的插件。"""
    global _available_plugins
    _available_plugins = _scan_plugins()
    activated = []
    for name, meta in _available_plugins.items():
        if _should_activate(meta, "onStartup"):
            state = activate_plugin(name, agent, "onStartup")
            if state:
                activated.append(state)
    return activated


def activate_by_event(event: str, agent, payload: str = "") -> Optional[PluginState]:
    """按事件激活匹配的插件（用于懒加载）。"""
    global _available_plugins
    if not _available_plugins:
        _available_plugins = _scan_plugins()

    for name, meta in _available_plugins.items():
        if name not in _loaded_plugins and _should_activate(meta, event, payload):
            return activate_plugin(name, agent, event, payload)
    return None


def get_loaded_plugins() -> dict:
    return dict(_loaded_plugins)


def get_all_plugin_tools() -> list:
    """返回所有已激活插件的工具定义。"""
    return [tool_def for _, tool_def, _ in _tool_registry.values()]


def execute_plugin_tool(name: str, arguments: dict) -> Optional[str]:
    """执行插件工具，返回结果或 None（None 表示不是插件工具）。"""
    entry = _tool_registry.get(name)
    if entry:
        _pname, _tool_def, handler = entry
        _event_bus.emit("tool:before", name, arguments)
        try:
            result = handler(arguments)
            rendered = _tool_renderer.render(name, result)
            _event_bus.emit("tool:after", name, rendered)
            return rendered
        except Exception as e:
            return f"插件工具错误: {e}"
    return None


def get_all_plugin_commands() -> dict:
    """返回 {"/cmd": handler}。"""
    return {name: handler for name, (_pname, handler) in _command_registry.items()}


def get_status_bar_text() -> str:
    return _status_bar.render()


def get_event_bus() -> EventBus:
    return _event_bus


def get_tool_renderer() -> ToolRenderer:
    return _tool_renderer
