"""首次配置引导。"""

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from deepclaw.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    CONFIG_DIR,
    save_config,
    MODEL_OPTIONS,
)

console = Console()


def run_setup() -> dict:
    """首次运行引导，返回完整配置 dict。"""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]DeepClaw 首次配置[/bold cyan]\n\n"
            f"配置将保存到 [dim]{CONFIG_DIR / 'config.json'}[/dim]",
            border_style="cyan",
        )
    )

    # 第一步：选择 API 来源
    console.print()
    console.print("[bold]选择 API 来源:[/bold]")
    console.print("  [cyan]1[/cyan]. 使用 DeepSeek 官方 API — 自动配置，只需 API Key")
    console.print("  [cyan]2[/cyan]. 使用第三方兼容 API — 需手动配置 URL 和模型")

    while True:
        choice = Prompt.ask("选择 (1/2)", default="1")
        if choice in ("1", "2"):
            break
        console.print("[yellow]请输入 1 或 2。[/yellow]")

    if choice == "1":
        return _setup_deepseek()
    else:
        return _setup_third_party()


def _setup_deepseek() -> dict:
    """DeepSeek 官方 API：只输入 Key，自动配置。"""
    console.print()
    console.print("[bold cyan]DeepSeek 官方 API 配置[/bold cyan]")
    console.print(f"[dim]API 地址: {DEFAULT_BASE_URL}[/dim]")

    while True:
        token = Prompt.ask("[bold]API Key[/bold]", password=True)
        if token.strip():
            break
        console.print("[yellow]API Key 不能为空。[/yellow]")

    # 选择模型
    deepseek_models = [m for m in MODEL_OPTIONS if "deepseek" in m["name"]]
    console.print()
    console.print("[bold]选择默认模型:[/bold]")
    for i, m in enumerate(deepseek_models, 1):
        marker = ">" if m["name"] == DEFAULT_MODEL else " "
        console.print(f"  {marker} {i}. [cyan]{m['name']}[/cyan] - [dim]{m['desc']}[/dim]")

    model = DEFAULT_MODEL
    choice = Prompt.ask(f"模型选择 (1-{len(deepseek_models)})", default="1")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(deepseek_models):
            model = deepseek_models[idx]["name"]
    except ValueError:
        pass

    save_config(DEFAULT_BASE_URL, token.strip(), model)
    console.print(f"[green]配置已保存！模型: {model}[/green]")
    return {"base_url": DEFAULT_BASE_URL, "auth_token": token.strip(), "model": model}


def _setup_third_party() -> dict:
    """第三方 API：手动输入全部信息。"""
    console.print()
    console.print("[bold cyan]第三方 API 配置[/bold cyan]")

    while True:
        token = Prompt.ask("[bold]API Key[/bold]", password=True)
        if token.strip():
            break
        console.print("[yellow]API Key 不能为空。[/yellow]")

    url = Prompt.ask("[bold]API 地址[/bold]", default=DEFAULT_BASE_URL)
    url = url.strip() or DEFAULT_BASE_URL
    url = url.rstrip("/")

    console.print()
    console.print("[bold]输入模型名称:[/bold]")
    console.print("[dim](或从已知模型中选择)[/dim]")
    for i, m in enumerate(MODEL_OPTIONS, 1):
        console.print(f"  {i}. [cyan]{m['name']}[/cyan]")

    model = Prompt.ask("模型名称", default=DEFAULT_MODEL).strip() or DEFAULT_MODEL

    save_config(url, token.strip(), model)
    console.print(f"[green]配置已保存！模型: {model}, 地址: {url}[/green]")
    return {"base_url": url, "auth_token": token.strip(), "model": model}
