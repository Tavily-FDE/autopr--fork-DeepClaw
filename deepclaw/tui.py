"""TUI 交互组件 — 键盘选择器 + 参数表单。"""
import os
import sys
from rich.prompt import Prompt
from rich.panel import Panel
from rich.console import Console


def param_form(skill_name: str, param_specs: list[dict], console: Console = None) -> dict | None:
    """交互式参数表单。返回 {name: value} 或 None（取消）。

    param_specs: [{"name":"focus","type":"enum","values":["安全","性能"],"desc":"...","default":"安全"}, ...]
    """
    if not param_specs:
        return {}
    if console is None:
        console = Console()

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]{skill_name}[/bold cyan] — 参数配置\n"
        "[dim]输入值后回车，留空使用默认值，输入 q 取消[/dim]",
        border_style="cyan",
    ))

    values = {}
    for p in param_specs:
        name = p["name"]
        default = p.get("default", "")
        desc = p.get("desc", name)
        ptype = p.get("type", "string")
        required = p.get("required", True)

        hint = f"[dim]({desc})[/dim]"
        if default != "":
            hint += f" [dim][默认: {default}][/dim]"
        if not required:
            hint += " [dim][可选][/dim]"
        if ptype == "enum" and p.get("values"):
            hint += f" [dim][可选: {'/'.join(p['values'])}][/dim]"

        console.print(f"\n[bold]{name}[/bold] {hint}")

        while True:
            val = Prompt.ask("  ", default=str(default) if default != "" else "")
            val = val.strip()
            if val.lower() == "q":
                console.print("[yellow]已取消。[/yellow]")
                return None
            if val == "" and required and default == "":
                console.print(f"[yellow]{name} 为必填。[/yellow]")
                continue
            if val == "":
                val = str(default)

            if ptype == "number" and val:
                try:
                    float(val)
                except ValueError:
                    console.print(f"[yellow]需输入数字。[/yellow]")
                    continue
            elif ptype == "enum" and p.get("values") and val:
                if val not in p["values"]:
                    console.print(f"[yellow]仅可选: {'/'.join(p['values'])}[/yellow]")
                    continue
            elif ptype == "bool":
                val = val.lower() in ("true", "yes", "1", "y")
                val = "true" if val else "false"

            values[name] = str(val)
            break

    return values


def select_from_list(items: list, title: str = "请选择", console=None) -> int | None:
    """
    交互式列表选择器。无滚动残留，原位置刷新。
    items: [{"label": "...", "detail": "..."}, ...]
    返回索引，取消返回 None。
    console 参数保留兼容，实际使用原始 ANSI。
    """
    if not items:
        return None

    idx = 0
    n = len(items)
    total_lines = n + 3  # 顶框 + n行 + 底框 + 提示

    def _term_width() -> int:
        try:
            return os.get_terminal_size().columns
        except Exception:
            return 100

    def _render():
        out = []
        tw = _term_width()
        detail_w = max(20, tw - 36)  # 动态适应终端宽度
        # 顶框（含标题）
        title_text = f"  {title} "
        title_line = title_text + "─" * max(0, tw - len(title_text) - 2)
        out.append(f"\x1b[36m╭{title_line}╮\x1b[0m")
        # 每行 item
        for i, item in enumerate(items):
            marker = "\x1b[1;32m>\x1b[0m" if i == idx else " "
            label = (item.get("label", str(i)) or "")[:20].ljust(20)
            detail = (item.get("detail", "") or "")[:detail_w].ljust(detail_w)
            out.append(f"\x1b[36m│\x1b[0m {marker} \x1b[36m{label}\x1b[0m \x1b[2m{detail}\x1b[0m \x1b[36m│\x1b[0m")
        # 底框
        out.append(f"\x1b[36m╰{'─' * (tw - 2)}╯\x1b[0m")
        # 提示行
        out.append(f"\x1b[2m↑↓ 选择  Enter 确认  Esc/q 取消\x1b[0m")
        return "\n".join(out)

    # 首次渲染
    sys.stdout.write(_render() + "\r\n")
    sys.stdout.flush()

    while True:
        key = _get_key()
        if key == "up":
            idx = (idx - 1) % n
        elif key == "down":
            idx = (idx + 1) % n
        elif key == "enter":
            return idx
        elif key in ("esc", "q"):
            return None
        else:
            continue

        sys.stdout.write(f"\x1b[{total_lines}A")
        sys.stdout.write("\x1b[0J")
        sys.stdout.write(_render())
        sys.stdout.flush()


def _get_key() -> str:
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getch()
        if ch == b'\xe0':
            ch2 = msvcrt.getch()
            if ch2 == b'H': return "up"
            elif ch2 == b'P': return "down"
        elif ch == b'\r': return "enter"
        elif ch == b'\x1b': return "esc"
        elif ch in (b'q', b'Q'): return "q"
        return "unknown"
    else:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(2)
                if ch2 == '[A': return "up"
                elif ch2 == '[B': return "down"
                return "esc"
            elif ch == '\r': return "enter"
            elif ch in ('q', 'Q'): return "q"
            return "unknown"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
