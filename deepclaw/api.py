"""DeepClawAPI — 插件可调用的稳定契约对象。

主程序在加载插件时注入 api 对象，插件通过 api 调用所有能力。
内部实现可以随意重构，只要 api 接口不变，插件就不会坏。
"""


class ToolRenderer:
    """工具结果渲染器：插件可注册自定义格式化器。"""
    def __init__(self):
        self._renderers = {}  # {tool_name: callback}

    def register(self, tool_name: str, callback):
        self._renderers[tool_name] = callback

    def render(self, tool_name: str, result: str) -> str:
        if tool_name in self._renderers:
            try:
                return self._renderers[tool_name](result)
            except Exception:
                pass
        return result


class StatusBar:
    """UI 状态栏扩展点。"""
    def __init__(self):
        self._messages = {}  # {plugin_name: message}

    def set(self, plugin_name: str, message: str):
        self._messages[plugin_name] = message

    def clear(self, plugin_name: str):
        self._messages.pop(plugin_name, None)

    def render(self) -> str:
        if not self._messages:
            return ""
        return " | ".join(f"[{k}] {v}" for k, v in self._messages.items())


class DeepClawAPI:
    """插件契约对象。插件只应通过此对象与主程序交互。"""

    def __init__(self, agent, config: dict, event_bus, tool_registry: dict, command_registry: dict):
        self._agent = agent
        self.config = config
        self._event_bus = event_bus
        self._tool_registry = tool_registry    # {tool_name: (plugin_name, handler)}
        self._command_registry = command_registry  # {"/cmd": (plugin_name, handler)}
        self.plugin_name = None   # 由 plugin loader 设置

    # ──────── 工具 ────────
    def register_tool(self, tool_def: dict, handler):
        name = tool_def.get("function", {}).get("name", "")
        if name:
            self._tool_registry[name] = (self.plugin_name, tool_def, handler)

    def unregister_tool(self, name: str):
        self._tool_registry.pop(name, None)

    # ──────── 命令 ────────
    def register_command(self, name: str, handler):
        self._command_registry[name] = (self.plugin_name, handler)

    def unregister_command(self, name: str):
        self._command_registry.pop(name, None)

    # ──────── 事件 ────────
    def on(self, event: str, callback):
        self._event_bus.on(event, self.plugin_name, callback)

    # ──────── 代理：只读访问 ────────
    @property
    def model(self) -> str:
        return self._agent.model

    @property
    def messages(self) -> list:
        return list(self._agent.messages)

    def chat_stream(self, user_input: str):
        """代理到 agent.chat_stream，但受事件系统介入。"""
        return self._agent.chat_stream(user_input)

    # ──────── UI ────────
    def __init_sub_ui(self, status_bar: StatusBar, tool_renderer: ToolRenderer):
        self.status_bar = status_bar
        self.tool_renderer = tool_renderer
