import json
import os
import re
import subprocess
import httpx
from pathlib import Path

from deepclaw.config import load_config

# Tool definitions, compatible with OpenAI/DeepSeek function-calling format.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定路径的文件内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件的绝对或相对路径。",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入指定路径的文件（会覆盖已有文件）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件的绝对或相对路径。",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入文件的内容。",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出指定目录下的文件和子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，默认为当前目录。",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_content",
            "description": "在目录中递归搜索文件内容，支持正则表达式，返回匹配行及文件路径和行号。适用于代码搜索、函数定义查找等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索的正则表达式模式。",
                    },
                    "path": {
                        "type": "string",
                        "description": "要搜索的目录路径，默认为当前目录。",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "在终端中执行一条 shell 命令并返回输出。执行危险操作前会提示确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令。",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "联网搜索，返回相关结果摘要和链接。类似于搜索引擎，支持中文和英文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词。",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "访问指定网页，自动提取正文文本内容。用于阅读搜索结果中的链接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要访问的完整 URL（含 https://）。",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "发送 HTTP 请求（GET/POST/PUT/DELETE），支持自定义请求头和请求体。可用于调用 API、提交表单、发送数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "请求的完整 URL。",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP 方法：GET、POST、PUT、DELETE，默认 GET。",
                    },
                    "headers": {
                        "type": "string",
                        "description": "JSON 格式的请求头，如 {\"Content-Type\":\"application/json\"}，可选。",
                    },
                    "body": {
                        "type": "string",
                        "description": "请求体内容（POST/PUT 时使用），可选。",
                    },
                },
                "required": ["url"],
            },
        },
    },
]

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".svg",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".pyc", ".pyd", ".pyo", ".class",
    ".ttf", ".otf", ".woff", ".woff2",
    ".db", ".sqlite", ".sqlite3",
}

IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", ".deepclaw"}
MAX_FILE_SIZE = 1024 * 1024  # 1MB
MAX_MATCHES = 200
MAX_SEARCH_FILES = 5000  # 最多搜索文件数
READ_MAX_LINES = 500  # read_file 最多返回行数


def execute_tool(name: str, arguments: dict) -> str:
    """执行指定工具，返回结果字符串。"""
    if name == "read_file":
        return _read_file(arguments.get("path", ""))
    elif name == "write_file":
        return _write_file(arguments.get("path", ""), arguments.get("content", ""))
    elif name == "list_directory":
        return _list_directory(arguments.get("path", "."))
    elif name == "search_content":
        return _search_content(arguments.get("pattern", ""), arguments.get("path", "."))
    elif name == "execute_command":
        return _execute_command(arguments.get("command", ""))
    elif name == "search_web":
        return _search_web(arguments.get("query", ""))
    elif name == "fetch_url":
        return _fetch_url(arguments.get("url", ""))
    elif name == "http_request":
        return _http_request(
            arguments.get("url", ""),
            arguments.get("method", "GET"),
            arguments.get("headers", ""),
            arguments.get("body", ""),
        )
    else:
        return f"未知工具: {name}"


def _read_file(path: str) -> str:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"错误: 文件不存在 — {p}"
        if p.is_dir():
            return f"错误: 路径是目录而非文件 — {p}"
        if p.stat().st_size > MAX_FILE_SIZE:
            return f"错误: 文件过大 ({p.stat().st_size} 字节)，超过限制 {MAX_FILE_SIZE} 字节"
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        total_lines = len(lines)
        if total_lines > READ_MAX_LINES:
            content = "\n".join(lines[:READ_MAX_LINES])
            content += f"\n\n... (共 {total_lines} 行，仅显示前 {READ_MAX_LINES} 行)"
        return content
    except PermissionError:
        return f"错误: 没有权限读取 — {path}"
    except Exception as e:
        return f"错误: 读取文件失败 — {e}"


def _write_file(path: str, content: str) -> str:
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入: {p} ({len(content)} 字符)"
    except PermissionError:
        return f"错误: 没有权限写入 — {path}"
    except Exception as e:
        return f"错误: 写入文件失败 — {e}"


def _list_directory(path: str) -> str:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"错误: 目录不存在 — {p}"
        if not p.is_dir():
            return f"错误: 路径不是目录 — {p}"
        entries = []
        for entry in sorted(p.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"  {entry.name}{suffix}")
        if not entries:
            return f"目录为空: {p}"
        return f"{p}:\n" + "\n".join(entries)
    except Exception as e:
        return f"错误: 列目录失败 — {e}"


def _search_content(pattern: str, path: str) -> str:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"错误: 路径不存在 — {p}"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"错误: 无效的正则表达式 — {e}"

        results = []
        files_searched = 0
        files_to_search = [p] if p.is_file() else sorted(p.rglob("*"))

        for fpath in files_to_search:
            if files_searched >= MAX_SEARCH_FILES:
                break
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() in BINARY_EXTENSIONS:
                continue
            if any(part in IGNORE_DIRS for part in fpath.parts):
                continue
            if fpath.stat().st_size > MAX_FILE_SIZE:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            files_searched += 1
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    results.append(f"{fpath}:{i}: {line.strip()}")
                    if len(results) >= MAX_MATCHES:
                        break
            if len(results) >= MAX_MATCHES:
                break

        if not results:
            msg = f"未找到匹配 '{pattern}' 的内容（搜索了 {files_searched} 个文件"
            if files_searched >= MAX_SEARCH_FILES:
                msg += f"，已达上限 {MAX_SEARCH_FILES}"
            return msg + ")"

        header = f"搜索 '{pattern}' — {len(results)} 个匹配"
        if len(results) >= MAX_MATCHES:
            header += f"（已达上限 {MAX_MATCHES}）"
        return header + "\n" + "\n".join(results)

    except Exception as e:
        return f"错误: 搜索失败 — {e}"


DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",           # 递归强制删除根目录
    r"rm\s+-rf\s+~",           # 删除用户目录
    r"del\s+/[fF]\s+/[sS]\s+[A-Z]:\\",  # Windows 盘符级删除
    r">\s*/dev/sd[a-z]",       # 覆写磁盘
    r"dd\s+if=.*of=/dev/sd",   # dd 写磁盘
    r"mkfs\.",                 # 格式化
    r"format\s+[A-Z]:",        # Windows 格式化
    r"^(shutdown|reboot|halt)\b",       # 关机/重启（仅命令开头匹配）
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;:",  # fork bomb
    r"chmod\s+(-R\s+)?777\s+/",  # 危险权限修改根目录
    r"chown\s+-R\s+\S+\s+/",   # 递归改所有者
    r"git\s+push\s+--force.*origin\s+(main|master)",  # force push 主分支
    r"git\s+reset\s+--hard",   # hard reset
    r">>\s*/etc/",             # 写系统配置
]


def _is_dangerous(command: str) -> tuple[bool, str]:
    """检查命令是否危险，返回 (是否危险, 匹配的模式)。"""
    cmd_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True, pattern
    return False, ""


def _execute_command(command: str) -> str:
    dangerous, pattern = _is_dangerous(command)
    if dangerous:
        return (
            f"⛔ 危险命令已拦截\n"
            f"命令: {command}\n"
            f"匹配规则: {pattern}\n"
            f"如需执行，请在终端中手动运行。"
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getcwd(),
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if not output.strip():
            output = f"(退出码: {result.returncode})"
        return output.strip() or "(无输出)"
    except subprocess.TimeoutExpired:
        return "错误: 命令执行超时 (120s)"
    except Exception as e:
        return f"错误: 命令执行失败 — {e}"


def _get_tavily_api_key() -> str:
    """Return Tavily API key from env var or config file, or empty string."""
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        key = load_config().get("tavily_api_key", "")
    return key


def _search_tavily(query: str, api_key: str) -> str:
    """Search using Tavily and return formatted results."""
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, max_results=8, search_depth="basic")

    results = []
    result_count = 0
    for i, r in enumerate(response.get("results", []), 1):
        title = r.get("title", "")
        url = r.get("url", "")
        snippet = r.get("content", "")[:250]
        if title:
            result_count += 1
            results.append(f"{i}. **{title}**")
            if url:
                results.append(f"   {url}")
            if snippet:
                results.append(f"   {snippet}")

    if not results:
        return ""

    return f"搜索 '{query}' — {result_count} 条:\n" + "\n".join(results)


def _search_web(query: str) -> str:
    if not query.strip():
        return "错误: 搜索关键词不能为空"

    # Tavily 搜索（优先）
    tavily_key = _get_tavily_api_key()
    if tavily_key:
        try:
            tavily_result = _search_tavily(query, tavily_key)
            if tavily_result:
                return tavily_result
        except Exception:
            pass  # Fall through to Bing/DuckDuckGo

    results = []
    # Bing 搜索
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(
                "https://www.bing.com/search",
                params={"q": query, "setlang": "zh-hans"},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            if resp.status_code == 200:
                blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', resp.text, re.DOTALL)
                for block in blocks[:8]:
                    link = re.search(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
                    title = re.sub(r'<[^>]+>', '', link.group(2)).strip() if link else ""
                    url = link.group(1) if link else ""
                    sm = re.search(r'(?:<p[^>]*>|class="b_lineclamp[^"]*"[^>]*>)(.*?)(?:</p>|</div>)', block, re.DOTALL)
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()[:250] if sm else ""
                    if title:
                        results.append(f"{len(results)+1}. **{title}**")
                        if url:
                            results.append(f"   {url}")
                        if snippet:
                            results.append(f"   {snippet}")
    except Exception:
        pass

    # 备用 DuckDuckGo
    if not results:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
                    seen = set()
                    for url, text in links:
                        text = re.sub(r'<[^>]+>', '', text).strip()
                        if text and len(text) > 3 and "duckduckgo" not in url and url not in seen:
                            seen.add(url)
                            results.append(f"- [{text}]({url})")
                    results = results[:8]
        except Exception:
            pass

    if not results:
        return f"未找到与 '{query}' 相关的结果。"

    return f"搜索 '{query}' — {len(results)} 条:\n" + "\n".join(results)


def _fetch_url(url: str) -> str:
    if not url.strip():
        return "错误: URL 不能为空"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; DeepClaw/1.0)"},
            )
            if resp.status_code >= 400:
                return f"错误: HTTP {resp.status_code} — 无法访问 {url}"

            html = resp.text
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
            html = re.sub(r'<[^>]+>', ' ', html)
            html = re.sub(r'\s+', ' ', html).strip()

            if len(html) > 3000:
                html = html[:3000] + f"\n\n... (总长度 {len(html)} 字符，已截断)"

            return f"[{url}]\n{html}" if html else f"[{url}] (页面无文本内容)"
    except httpx.TimeoutException:
        return f"错误: 访问 {url} 超时"
    except Exception as e:
        return f"错误: 访问失败 — {e}"


def _http_request(url: str, method: str = "GET", headers: str = "", body: str = "") -> str:
    if not url.strip():
        return "错误: URL 不能为空"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    method = method.strip().upper() or "GET"
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        return f"错误: 不支持的 HTTP 方法: {method}"

    hdrs = {"User-Agent": "Mozilla/5.0 (compatible; DeepClaw/1.0)"}
    if headers.strip():
        try:
            hdrs.update(json.loads(headers))
        except json.JSONDecodeError as e:
            return f"错误: 请求头 JSON 解析失败 — {e}"

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            if method == "GET":
                resp = client.get(url, headers=hdrs)
            elif method == "DELETE":
                resp = client.delete(url, headers=hdrs)
            else:
                resp = client.request(method, url, headers=hdrs, content=body or None)

            result = f"HTTP {resp.status_code}\n"
            # 响应头摘要
            ct = resp.headers.get("content-type", "")
            result += f"Content-Type: {ct}\n"

            # 响应体
            text = resp.text
            if "json" in ct:
                try:
                    parsed = resp.json()
                    text = json.dumps(parsed, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            elif "text/html" in ct:
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()

            if len(text) > 2000:
                text = text[:2000] + f"\n... (总长度 {len(text)} 字符，已截断)"
            result += f"\n{text}" if text else "\n(空响应)"

            return result
    except httpx.TimeoutException:
        return f"错误: 请求 {url} 超时"
    except Exception as e:
        return f"错误: 请求失败 — {e}"
