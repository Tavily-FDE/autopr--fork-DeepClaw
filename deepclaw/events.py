"""事件总线 — 插件订阅/主程序发布的事件系统。"""


class EventBus:
    def __init__(self):
        self._handlers = {}       # {"event_name": [(plugin_name, callback), ...]}
        self._wildcard = []       # [(plugin_name, callback)] for "*"

    def on(self, event: str, plugin_name: str, callback):
        self._handlers.setdefault(event, []).append((plugin_name, callback))

    def off_plugin(self, plugin_name: str):
        for event in self._handlers:
            self._handlers[event] = [
                (n, cb) for n, cb in self._handlers[event] if n != plugin_name
            ]

    def emit(self, event: str, *args, **kwargs):
        for _plugin_name, callback in self._handlers.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception:
                pass  # 插件异常不影响主程序
