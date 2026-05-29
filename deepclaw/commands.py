"""命令处理模块 — 所有 / 命令的实现。"""
import os
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from deepclaw.agent import DeepClawAgent
from deepclaw.config import load_config, CONFIG_DIR, save_config
from deepclaw.memory import save_session, list_sessions, load_session, delete_session
from deepclaw.skill import list_skills, get_expected_param_count, load_skill as load_skill_def, get_skill_param_specs
from deepclaw.tui import param_form

_console = Console(force_terminal=True)


def set_console(c):
    global _console
    _console = c


def has_conversation(agent: DeepClawAgent) -> bool:
    return len(agent.messages) > 1


def do_save(agent: DeepClawAgent):
    if has_conversation(agent):
        fname = save_session(agent.get_messages(), agent.model)
        _console.print(f"[dim]对话已保存: {fname}[/dim]")


def cmd_back(agent: DeepClawAgent):
    sessions = list_sessions()
    if not sessions:
        _console.print("[dim]没有已保存的对话记录。[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("时间", style="cyan")
    table.add_column("摘要", style="yellow")
    table.add_column("消息数", justify="right", style="dim")

    for i, s in enumerate(sessions, 1):
        created = s["created"][:16].replace("T", " ")
        table.add_row(str(i), created, s["summary"][:40], str(s["msg_count"]))

    _console.print()
    _console.print(table)
    _console.print("[dim]输入编号加载 | /back delete 删除会话[/dim]")
    _console.print()

    try:
        choice = _console.input("[bold]选择 (回车取消): [/bold]").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not choice:
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(sessions):
            _console.print("[yellow]无效编号。[/yellow]")
            return
    except ValueError:
        _console.print("[yellow]无效输入。[/yellow]")
        return

    filename = sessions[idx]["filename"]
    msgs = load_session(filename)
    if msgs is None:
        _console.print("[red]加载失败。[/red]")
        return

    agent.load_messages(msgs)
    _console.print(f"[green]已加载对话: {sessions[idx]['summary']}[/green]")


def cmd_back_delete():
    sessions = list_sessions()
    if not sessions:
        _console.print("[dim]没有已保存的对话记录。[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("时间", style="cyan")
    table.add_column("摘要", style="yellow")

    for i, s in enumerate(sessions, 1):
        created = s["created"][:16].replace("T", " ")
        table.add_row(str(i), created, s["summary"][:50])

    _console.print()
    _console.print(table)
    _console.print("[dim]输入编号删除（可输入多个，空格分隔）[/dim]")
    _console.print()

    try:
        choice = _console.input("[bold red]删除编号: [/bold red]").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not choice:
        return

    for num in choice.split():
        try:
            idx = int(num) - 1
            if 0 <= idx < len(sessions):
                delete_session(sessions[idx]["filename"])
                _console.print(f"[dim]已删除: {sessions[idx]['summary']}[/dim]")
            else:
                _console.print(f"[yellow]无效编号: {num}[/yellow]")
        except ValueError:
            _console.print(f"[yellow]无效: {num}[/yellow]")


def cmd_export(agent: DeepClawAgent):
    msgs = agent.get_messages()
    if len(msgs) <= 1:
        _console.print("[dim]当前无对话内容。[/dim]")
        return

    lines = ["# DeepClaw 对话记录\n", f"*导出时间: {datetime.now().isoformat()}*\n", f"*模型: {agent.model}*\n", "\n---\n"]
    for m in msgs:
        role = m["role"]
        content = m.get("content", "")
        safe_content = content.replace("\n#", "\n\\#")
        if role == "system":
            continue
        if role == "user":
            lines.append(f"\n### 用户\n\n{safe_content}\n")
        elif role == "assistant":
            lines.append(f"\n### DeepClaw\n\n{safe_content}\n")
        elif role == "tool":
            lines.append(f"\n*[工具结果]*\n\n```\n{content[:500]}\n```\n")

    filename = f"deepclaw_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = Path(os.getcwd()) / filename
    filepath.write_text("\n".join(lines), encoding="utf-8")
    _console.print(f"[green]对话已导出: {filepath}[/green]")


def cmd_clear(agent: DeepClawAgent):
    agent.reset()
    _console.print("[dim]对话已清除，开始新对话。[/dim]")


def cmd_new(agent: DeepClawAgent):
    do_save(agent)
    agent.reset()
    _console.print("[dim]对话已保存，开始新对话。[/dim]")


def cmd_config(agent: DeepClawAgent, args: str):
    args = args.strip().lower()
    cfg = load_config()

    if not args:
        table = Table(show_header=False, border_style="dim")
        table.add_column("项目", style="cyan")
        table.add_column("值", style="yellow")
        table.add_row("API 地址", cfg["base_url"])
        token_display = (
            cfg["auth_token"][:8] + "..." + cfg["auth_token"][-4:]
            if cfg["auth_token"] and len(cfg["auth_token"]) > 12
            else (cfg["auth_token"] or "(未设置)")
        )
        table.add_row("API Key", token_display)
        table.add_row("模型", cfg["model"])
        table.add_row("当前", agent.model)
        _console.print()
        _console.print(table)
        _console.print("[dim]/config model <名称> | /config reload[/dim]")
        return

    if args == "reload":
        new_cfg = load_config()
        if new_cfg["auth_token"]:
            agent.client.api_key = new_cfg["auth_token"]
        agent.model = new_cfg["model"]
        agent.client.base_url = new_cfg["base_url"]
        _console.print("[green]配置已重新加载。[/green]")
        return

    parts = args.split(None, 1)
    key = parts[0]
    value = parts[1] if len(parts) > 1 else ""

    if key == "model" and value:
        agent.model = value
        save_config(cfg["base_url"], cfg["auth_token"], value, cfg.get("tavily_api_key", ""))
        _console.print(f"[green]模型已切换为: {value}[/green]")
    elif key == "url" and value:
        agent.client.base_url = value
        save_config(value, cfg["auth_token"], cfg["model"], cfg.get("tavily_api_key", ""))
        _console.print(f"[green]API 地址已更新。[/green]")
    elif key == "key" and value:
        agent.client.api_key = value
        save_config(cfg["base_url"], value, cfg["model"], cfg.get("tavily_api_key", ""))
        _console.print(f"[green]API Key 已更新。[/green]")
    else:
        _console.print(f"[yellow]用法: /config [model|url|key <value>|reload][/yellow]")


def cmd_skill(agent: DeepClawAgent, args: str):
    args = args.strip()

    if not args or args.lower() == "list":
        skills = list_skills()
        loaded = agent.get_loaded_skills()
        loaded_names = {s["dir_name"] for s in loaded}
        if not skills:
            _console.print("[dim]没有安装任何技能。[/dim]")
            _console.print(f"[dim]将 SKILL.md 放入 {CONFIG_DIR / 'skills' / '<名称>'} 即可安装。[/dim]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("状态", width=4)
        table.add_column("名称", style="cyan")
        table.add_column("参数", style="green")
        table.add_column("描述", style="dim")

        for s in skills:
            status = "[green]●[/green]" if s["dir_name"] in loaded_names else " "
            loaded_skill = next((ls for ls in loaded if ls["dir_name"] == s["dir_name"]), None)
            params_str = ""
            if loaded_skill and loaded_skill.get("params"):
                params_str = ", ".join(loaded_skill["params"])
            table.add_row(status, s["name"], params_str, s.get("description", "")[:60])

        _console.print()
        _console.print(table)
        return

    if args.lower() == "off":
        agent.deactivate_all_skills()
        _console.print("[dim]所有技能已卸载。[/dim]")
        return

    parts = args.split(None, 1)
    name = parts[0].lower()
    raw_params = parts[1].strip() if len(parts) > 1 else ""

    loaded_names = {s["dir_name"] for s in agent.get_loaded_skills()}
    if name in loaded_names:
        agent.deactivate_skill(name)
        _console.print(f"[dim]技能已卸载: {name}[/dim]")
        return

    # 获取参数规格
    param_specs = get_skill_param_specs(name)
    if not param_specs and not load_skill_def(name):
        _console.print(f"[yellow]未找到技能: {name}[/yellow]")
        return

    # 无参数技能直接加载
    if not param_specs:
        agent.activate_skill(name)
        _console.print(f"[green]技能已加载: {name}[/green]")
        return

    # 有参数：未提供时弹出交互表单
    if not raw_params:
        _console.print(f"[dim]技能 {name} 需要参数，进入配置...[/dim]")
        values = param_form(name, param_specs, _console)
        if values is None:
            return
        params_list = [f"{k}={v}" for k, v in values.items()]
    else:
        # 检测是命名参数 (key=value) 还是位置参数
        params_list = raw_params.split()
        if any("=" not in p for p in params_list):
            # 位置参数 → 旧格式兼容
            specs_without_default = [s for s in param_specs if s.get("required", True) and s.get("default", "") == ""]
            if len(params_list) != len(specs_without_default):
                _console.print(f"[yellow]参数数量不匹配: 需要 {len(specs_without_default)} 个，提供了 {len(params_list)} 个[/yellow]")
                _console.print(f"[dim]用法: /skill {name} " + " ".join(f"<{s['name']}>" for s in specs_without_default) + "[/dim]")
                _console.print(f"[dim]或使用命名参数: /skill {name} " + " ".join(f"{s['name']}=值" for s in param_specs) + "[/dim]")
                return
            params_list = [f"{param_specs[i]['name']}={params_list[i]}" for i in range(len(params_list))]

    if agent.activate_skill(name, params_list):
        _console.print(f"[green]技能已加载: {name}[/green]")
    else:
        _console.print(f"[yellow]未找到技能: {name}[/yellow]")
        _console.print(f"[dim]可用技能目录: {CONFIG_DIR / 'skills'}[/dim]")
