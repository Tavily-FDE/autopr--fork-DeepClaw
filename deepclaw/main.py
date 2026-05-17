import sys
import os
import ctypes
import argparse

if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32
    STD_OUTPUT_HANDLE = -11
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from deepclaw.agent import DeepClawAgent
from deepclaw.config import load_config, MODEL_OPTIONS
from deepclaw.setup import run_setup
from deepclaw.memory import list_sessions, load_session
from deepclaw.commands import (
    set_console,
    do_save,
    cmd_back, cmd_back_delete, cmd_export,
    cmd_clear, cmd_new, cmd_config, cmd_skill,
)
from deepclaw.plugin import (
    discover_plugins,
    activate_plugin,
    activate_startup_plugins,
    activate_by_event,
    unload_plugin,
    get_loaded_plugins,
    get_all_plugin_commands,
    get_status_bar_text,
)

console = Console(force_terminal=True)

HELP_TEXT = """[bold]可用命令：[/bold]
  /exit, /quit, /q  — 退出（自动保存对话）
  /new             — 保存当前对话并开新对话
  /clear           — 清除对话（不保存）
  /back            — 选择并加载历史对话
  /back delete     — 删除历史对话
  /export          — 导出当前对话为 Markdown
  /skill [名称]    — 列出/加载/卸载技能
  /plugin [名称]   — 列出/加载/卸载插件
  /config          — 查看/修改配置
  /model [名称]    — 查看/切换模型
  /reset           — 重置上下文
  '''              — 开启多行输入模式
  /help            — 显示此帮助

[dim]直接输入自然语言即可与 AI 对话。[/dim]"""


def _cmd_plugin(agent: DeepClawAgent, args: str):
    args = args.strip().lower()

    if not args or args == "list":
        available = discover_plugins()
        loaded = get_loaded_plugins()

        if not available:
            console.print("[dim]没有安装任何插件。[/dim]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("状态", width=4)
        table.add_column("名称", style="cyan")
        table.add_column("模式", style="yellow")
        table.add_column("激活", style="dim")
        table.add_column("描述", style="dim")

        for p in available:
            name = p.get("_dir", p.get("name", "?"))
            state = loaded.get(name)
            if state:
                if state.failed:
                    status = "[red]✗[/red]"
                else:
                    status = "[green]●[/green]"
            else:
                status = " "
            mode = p.get("mode", "tool")
            activation = ", ".join(p.get("activationEvents", ["*"])[:2])
            desc = p.get("description", "")[:40]
            table.add_row(status, name, mode, activation, desc)

        console.print()
        console.print(table)

        # 失败的插件显示错误
        for name, state in loaded.items():
            if state.failed:
                console.print(f"[red]插件 {name} 加载失败:[/red]")
                console.print(f"[dim]{state.error[:200]}[/dim]")
        return

    parts = args.split(None, 1)
    action = parts[0]
    name = parts[1] if len(parts) > 1 else ""

    if action == "load" and name:
        state = activate_plugin(name, agent, "onCommand:/plugin")
        if state:
            if state.failed:
                console.print(f"[red]插件加载失败: {state.error[:200]}[/red]")
            else:
                mode = state.meta.get("mode", "tool")
                console.print(f"[green]插件已加载: {name} (模式: {mode})[/green]")
                if mode == "gui":
                    console.print("[bold cyan]GUI 插件已接管界面。[/bold cyan]")
        else:
            console.print(f"[yellow]未找到插件: {name}[/yellow]")
        return

    if action == "unload" and name:
        if unload_plugin(name):
            console.print(f"[dim]插件已卸载: {name}[/dim]")
        else:
            console.print(f"[yellow]插件未加载或不存在: {name}[/yellow]")
        return

    console.print("[yellow]用法: /plugin [list|load <name>|unload <name>][/yellow]")


def main():
    parser = argparse.ArgumentParser(description="DeepClaw — 本地 AI 助手")
    parser.add_argument("--model", "-m", help="指定模型名称")
    parser.add_argument("--base-url", help="指定 API 地址")
    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    parser.add_argument("--resume", action="store_true", help="加载上次对话")
    parser.add_argument("--plugin", "-p", help="启动时加载插件（逗号分隔）")
    args = parser.parse_args()

    if args.no_color:
        global console
        console = Console(force_terminal=True, color_system=None)
        set_console(console)

    config = load_config()
    if not config.get("auth_token"):
        config = run_setup()

    if args.model:
        config["model"] = args.model
    if args.base_url:
        config["base_url"] = args.base_url.rstrip("/")

    console.print(
        Panel.fit(
            "[bold cyan]DeepClaw[/bold cyan] — 本地 AI 助手\n"
            f"基于 [bold]{config['model']}[/bold] 模型 | 输入 [bold]/help[/bold] 查看帮助 | [bold]/exit[/bold] 退出",
            border_style="cyan",
        )
    )

    agent = DeepClawAgent(config)

    if args.resume:
        sessions = list_sessions()
        if sessions:
            msgs = load_session(sessions[0]["filename"])
            if msgs:
                agent.load_messages(msgs)
                console.print(f"[dim]已恢复上次对话: {sessions[0]['summary']}[/dim]")

    # 激活启动插件
    startup_plugins = activate_startup_plugins(agent)
    for p in startup_plugins:
        if p.failed:
            console.print(f"[red]插件 {p.name} 失败: {p.error[:100]}[/red]")
        else:
            console.print(f"[dim]插件已加载: {p.name}[/dim]")

    # CLI 参数指定插件（跳过已激活的）
    if args.plugin:
        for name in args.plugin.split(","):
            name = name.strip()
            if name in get_loaded_plugins():
                continue
            state = activate_plugin(name, agent, "onStartup")
            if state:
                if state.failed:
                    console.print(f"[red]插件 {name} 失败: {state.error[:100]}[/red]")
                else:
                    console.print(f"[dim]插件已加载: {name}[/dim]")

    while True:
        try:
            user_input = console.input("\n[bold green]>[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            do_save(agent)
            console.print("[dim]再见！[/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # 懒激活：命令匹配触发插件
        if user_input.startswith("/"):
            activate_by_event("onCommand", agent, user_input.split()[0])

        # 检查插件命令
        plugin_cmds = get_all_plugin_commands()
        handled_by_plugin = False
        for cmd_name, handler in plugin_cmds.items():
            if user_input.startswith(cmd_name):
                rest = user_input[len(cmd_name):].strip()
                try:
                    handler(rest)
                except Exception as e:
                    console.print(f"[red]插件命令错误: {e}[/red]")
                handled_by_plugin = True
                break

        if handled_by_plugin:
            continue

        # 多行输入模式
        if user_input == "'''":
            lines = []
            console.print("[dim](多行输入模式，输入 ''' 结束)[/dim]")
            while True:
                try:
                    line = console.input("")
                except (EOFError, KeyboardInterrupt):
                    break
                if line.strip() == "'''":
                    break
                lines.append(line)
            user_input = "\n".join(lines)
            if not user_input.strip():
                continue

        if user_input.startswith("/"):
            lower = user_input.lower()
            if lower.startswith("/skill"):
                cmd_skill(agent, user_input[6:].strip())
                continue
            if lower.startswith("/config"):
                cmd_config(agent, user_input[7:].strip())
                continue
            if lower.startswith("/plugin"):
                _cmd_plugin(agent, user_input[7:].strip())
                continue

            cmd = user_input[1:].strip().lower()
            if cmd in ("exit", "quit", "q"):
                do_save(agent)
                console.print("[dim]再见！[/dim]")
                break
            elif cmd == "help":
                console.print(Panel(HELP_TEXT, border_style="blue"))
                continue
            elif cmd == "back":
                cmd_back(agent)
                continue
            elif cmd == "back delete":
                cmd_back_delete()
                continue
            elif cmd == "export":
                cmd_export(agent)
                continue
            elif cmd == "clear":
                cmd_clear(agent)
                continue
            elif cmd == "new":
                cmd_new(agent)
                continue
            elif cmd == "reset":
                agent.reset()
                console.print("[dim]对话上下文已重置。[/dim]")
                continue
            elif cmd == "model" or cmd.startswith("model "):
                if cmd == "model":
                    table = Table(show_header=True, header_style="bold cyan")
                    table.add_column("状态", width=4)
                    table.add_column("模型", style="cyan")
                    table.add_column("描述", style="dim")
                    for m in MODEL_OPTIONS:
                        status = "[green]●[/green]" if m["name"] == agent.model else " "
                        table.add_row(status, m["name"], m["desc"])
                    console.print()
                    console.print(table)
                    console.print(f"[dim]当前: {agent.model} | /model <名称> 切换[/dim]")
                else:
                    new_model = cmd[6:].strip()
                    agent.model = new_model
                    from deepclaw.config import save_config
                    cfg = load_config()
                    save_config(cfg["base_url"], cfg["auth_token"], new_model)
                    console.print(f"[green]模型已切换: {new_model} (已保存)[/green]")
                continue
            else:
                console.print(f"[yellow]未知命令: /{cmd}[/yellow]")
                continue

        console.print()
        first_text = True
        pending_tools = []
        in_reasoning = False
        try:
            for event in agent.chat_stream(user_input):
                kind = event[0]
                if kind == "reasoning":
                    if pending_tools:
                        console.print(f"\n[dim](已执行: {', '.join(pending_tools)})[/dim]")
                        pending_tools = []
                    if not in_reasoning:
                        in_reasoning = True
                        console.print()
                    console.print(f"[blue dim]{event[1]}[/blue dim]", end="")
                elif kind == "text":
                    if first_text:
                        if pending_tools:
                            console.print(f"\n[dim](已执行: {', '.join(pending_tools)})[/dim]")
                            pending_tools = []
                        if in_reasoning:
                            in_reasoning = False
                            console.print()
                        else:
                            console.print()
                        first_text = False
                    console.print(event[1], end="")
                elif kind == "tool_call":
                    activate_by_event("onTool", agent, event[1])
                    pending_tools.append(event[1])
                elif kind == "error":
                    console.print(f"\n[red]{event[1]}[/red]")
        except Exception as e:
            console.print(f"\n[red]错误: {e}[/red]")
            continue

        console.print()

        # 状态栏
        sb = get_status_bar_text()
        if sb:
            console.print(f"[dim]{sb}[/dim]")


if __name__ == "__main__":
    main()
