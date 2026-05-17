"""会话持久化模块。"""
import json
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

from deepclaw.config import CONFIG_DIR

SESSIONS_DIR = CONFIG_DIR / "sessions"


def _ensure_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _make_summary(messages: list) -> str:
    for msg in messages:
        if msg["role"] == "user":
            text = msg["content"].strip()
            safe = []
            for ch in text[:30].replace("\n", " ").replace("\r", ""):
                cat = unicodedata.category(ch)
                if cat.startswith("L") or cat.startswith("N") or ch in " -_.":
                    safe.append(ch)
                else:
                    safe.append("_")
            summary = "".join(safe).strip(" _.")
            return summary if summary else "empty"
    return "empty"


def save_session(messages: list, model: str):
    """保存当前对话到 sessions/ 目录。"""
    _ensure_dir()
    summary = _make_summary(messages)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")  # 微秒防冲突
    filename = f"{timestamp}_{summary}.json"
    filepath = SESSIONS_DIR / filename

    data = {
        "created": datetime.now().isoformat(),
        "model": model,
        "summary": summary,
        "messages": messages,
    }
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return filename


def list_sessions() -> list[dict]:
    """列出所有已保存的会话，按时间倒序。"""
    _ensure_dir()
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "filename": f.name,
                "created": data.get("created", ""),
                "summary": data.get("summary", ""),
                "model": data.get("model", ""),
                "msg_count": len(data.get("messages", [])),
            })
        except Exception:
            pass
    return sessions


def load_session(filename: str) -> Optional[list]:
    """加载指定会话的消息列表。"""
    filepath = SESSIONS_DIR / filename
    if not filepath.exists():
        return None
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return data.get("messages", [])
    except Exception:
        return None


def delete_session(filename: str) -> bool:
    """删除指定会话文件。"""
    filepath = SESSIONS_DIR / filename
    if filepath.exists():
        filepath.unlink()
        return True
    return False
