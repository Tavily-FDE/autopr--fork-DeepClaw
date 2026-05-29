"""配置管理 — 纯配置文件，不依赖环境变量。"""

import json
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

# 已知可选的模型列表
MODEL_OPTIONS = [
    {"name": "deepseek-chat",     "desc": "通用对话模型，快速且成本低"},
    {"name": "deepseek-v4-pro",   "desc": "最强推理模型，支持思考过程"},
    {"name": "deepseek-v4-flash", "desc": "快速推理模型，成本更低"},
    {"name": "deepseek-reasoner", "desc": "深度推理模型，适用于复杂逻辑"},
]

CONFIG_DIR = Path.home() / ".deepclaw"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """加载配置：仅从 config.json 读取。返回 {base_url, auth_token, model}"""
    config = {
        "base_url": DEFAULT_BASE_URL,
        "auth_token": "",
        "model": DEFAULT_MODEL,
        "tavily_api_key": "",
    }

    if CONFIG_FILE.exists():
        try:
            raw = CONFIG_FILE.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            file_cfg = json.loads(raw.decode("utf-8"))
            config["base_url"] = file_cfg.get("base_url", DEFAULT_BASE_URL)
            config["auth_token"] = file_cfg.get("auth_token", "")
            config["model"] = file_cfg.get("model", DEFAULT_MODEL)
            config["tavily_api_key"] = file_cfg.get("tavily_api_key", "")
        except Exception:
            pass

    if config["auth_token"]:
        config["base_url"] = config["base_url"].rstrip("/")

    return config


def save_config(base_url: str, auth_token: str, model: str, tavily_api_key: str = ""):
    """保存配置到 ~/.deepclaw/config.json。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "base_url": base_url,
        "auth_token": auth_token,
        "model": model,
        "tavily_api_key": tavily_api_key,
    }
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
