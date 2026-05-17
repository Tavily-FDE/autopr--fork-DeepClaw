# DeepClaw - 项目计划与方向

## 项目定位

DeepClaw 是一个基于 DeepSeek 模型的本地 Agent 工具，对标 Claude Code，能够在用户电脑上自主完成文件操作、命令执行、代码修改等任务。

## 核心能力

1. **文件控制** — 读取、创建、修改、删除本地文件
2. **命令执行** — 在终端中执行 shell 命令
3. **电脑控制** — 操控文件系统、进程、系统资源
4. **对话交互** — 终端内自然语言对话，理解用户意图并转化为操作

## 技术架构

```
用户 → CLI 界面 → Agent 核心 → DeepSeek API
                   ↓
            工具执行层 (文件/命令/系统)
```

- **语言**: Python（生态丰富，AI/LLM 库成熟）
- **模型**: DeepSeek API（deepseek-chat / deepseek-reasoner）
- **接口形式**: CLI 命令行工具
- **工具系统**: 参考 Claude Code 的 tool use 机制，实现文件读写、命令执行等工具

## 当前目录结构

```
DeepClaw/
├── deepclaw/
│   ├── __init__.py     # 包入口
│   ├── __main__.py     # python -m deepclaw 入口
│   ├── main.py         # CLI 界面 (Rich)
│   ├── agent.py        # Agent 核心循环 (API + tool-call)
│   ├── tools.py        # 工具定义与执行
│   ├── config.py       # 配置加载 (env > 文件 > 引导)
│   └── setup.py        # 首次配置引导
├── requirements.txt    # openai + rich
├── PLAN.md
└── DeepClaw.png
```

## 开发阶段

### 第一阶段：核心 MVP
- [x] DeepSeek API 对接（chat/completion）
- [x] 基础 CLI 对话界面
- [x] 文件读写工具
- [x] Shell 命令执行工具
- [x] 简单的 tool-call 循环
- [x] 配置系统（~/.deepclaw/config.json + 环境变量引导）
- [x] 目录列表工具

### 第二阶段：功能完善
- 多工具并行调用
- 会话历史管理
- 上下文压缩（长对话场景）
- 配置文件系统（.deepclaw 目录）

### 第三阶段：体验增强
- 语法高亮、Markdown 渲染
- 权限控制（命令执行前确认）
- 插件/技能系统
- 跨平台兼容（Windows / macOS / Linux）

## 关键设计决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 语言 | Python | AI 生态最完善，openai SDK 兼容 DeepSeek |
| API 方式 | DeepSeek 原生 API | 兼容 OpenAI SDK 格式，接入简单 |
| CLI 框架 | Rich | 美观的终端 UI，支持 Markdown 渲染 |
| 工具协议 | 参考 Anthropic tool use | 成熟的工具调用范式 |

## 环境变量

DeepSeek API 通过以下三个环境变量配置：

| 变量名 | 用途 |
|--------|------|
| `DEEPCLAW_BASE_URL` | DeepSeek API 地址（默认 `https://api.deepseek.com`） |
| `DEEPCLAW_AUTH_TOKEN` | 认证 Token（API Key） |
| `DEEPCLAW_MODEL` | 模型名称（如 `deepseek-chat`） |

## 待明确事项

- [x] DeepSeek API Key 配置方式（环境变量 / 配置文件）
- [ ] 是否需要多模型切换能力
- [ ] 是否需要 MCP (Model Context Protocol) 支持
