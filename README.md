# DeepClaw

DeepClaw is a local AI agent powered by DeepSeek models, running in your terminal. It reads/writes files, executes shell commands, searches codebases, and browses the web — autonomously. Features streaming output, context compression, a Jinja2-driven Skill system, and a VS Code-style Plugin architecture for unlimited extensibility. Zero environment variables, one-command setup, ready to work.

## Software Architecture

```
User → CLI (Rich TUI) → Agent Core (streaming + tool-call loop) → DeepSeek API
                              ↓
                    Tool Execution Layer
           (file I/O, shell, grep, web search, HTTP)
                              ↓
              Skill Engine (Jinja2) ←→ Plugin System (hot-load)
```

Built with **Python**, using `openai` SDK for API calls and `Rich` for terminal UI. Skills use Jinja2 templates with YAML front matter; Plugins are dynamically-loaded Python modules following a VS Code Extension-like contract.

## Installation

```bash
git clone https://github.com/your/repo.git
cd DeepClaw
pip install -r requirements.txt
python -m deepclaw
```

On first run, you'll be guided through setup: choose DeepSeek official API (API Key only) or third-party API (Key + URL + model).

## Instructions

| Command | Description |
|---------|-------------|
| `python -m deepclaw` | Launch the interactive CLI |
| `python -m deepclaw --model deepseek-v4-pro` | Start with a specific model |
| `python -m deepclaw --plugin weather` | Load plugins at startup |
| `python -m deepclaw --resume` | Restore last session |

**In-session commands:**
| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/skill <name>` | List / load / unload skills (interactive) |
| `/plugin list` | Manage plugins |
| `/model` | View / switch models |
| `/config` | View / edit configuration |
| `/back` | Load / delete saved sessions |
| `/export` | Export conversation to Markdown |
| `/exit` | Quit (auto-saves session) |

## Built-in Skills

| Skill | Description |
|-------|-------------|
| `python-coder` | Python coding assistant — PEP 8, type hints, testing |
| `git-helper` | Git operations — conventional commits, safety checks |
| `reviewer` | Code reviewer — configurable focus (security / performance / style), strict mode, max issues |
| `supercoder` | Full project workflow — requirements → design → framework → implement → test → iterate |

Skills use Jinja2 templates with YAML parameter specs. Load via `/skill <name>` — interactive forms appear for skills with parameters.

## Plugin System

Plugins run arbitrary Python code with full freedom:

```python
# ~/.deepclaw/plugins/my-plugin/main.py
def on_load(api):
    api.register_tool({"function": {"name": "my_tool", ... }}, handler)
    api.status_bar.set("my-plugin", "Ready")
    api.on("chat:after", lambda resp: print(resp))
```

Extensions can: inject tools, register commands, subscribe to events, run background services, or even take over the UI entirely (`mode: gui`).

## Contribution

1. Fork the repository
2. Create `Feat_xxx` branch
3. Commit your code
4. Create Pull Request

Skills and plugins can be contributed by adding a directory to `~/.deepclaw/skills/` or `~/.deepclaw/plugins/` with the required files — no fork needed for content contributions.

## License

MIT License — see [LICENSE](LICENSE).
