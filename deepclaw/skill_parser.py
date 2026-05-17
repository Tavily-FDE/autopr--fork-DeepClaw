"""Skill 语法解析器 — YAML front matter + 参数类型系统。"""

import re
import yaml
from pathlib import Path
from typing import Optional

# YAML front matter 分隔符
FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# 旧格式参数模式 ($1, $2...)
OLD_PARAM_RE = re.compile(r"\$(\d)")


def parse_skill_file(filepath: Path) -> Optional[dict]:
    """解析 SKILL.md，返回 {params, template, raw_params}。

    支持两种格式：
    1. 新格式：YAML front matter + Jinja2 模板
    2. 旧格式：$1 $2 占位符（自动转换为新格式）
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    m = FRONT_RE.match(content)
    if m:
        # 新格式
        try:
            front_data = yaml.safe_load(m.group(1)) or {}
        except Exception:
            return None
        template = content[m.end():].strip()
        params = _normalize_params(front_data.get("params", {}), template)
        return {
            "name": front_data.get("name", filepath.parent.name),
            "params": params,
            "template": template,
            "is_new_format": True,
        }
    else:
        # 旧格式：提取 $1 $2 ... 作为隐式参数
        nums = {int(m) for m in OLD_PARAM_RE.findall(content)}
        if not nums:
            # 无参数
            return {
                "name": _extract_title(content) or filepath.parent.name,
                "params": [],
                "template": content,
                "is_new_format": False,
            }

        params = []
        for i in range(1, max(nums) + 1):
            params.append({
                "name": f"arg{i}",
                "type": "string",
                "required": i in nums,
                "default": "",
                "desc": f"参数 {i}",
            })

        # 将 $1 $2 替换为 {{ arg1 }} {{ arg2 }}
        def _replace(m):
            idx = int(m.group(1))
            return "{{ " + f"arg{idx}" + " }}"
        template = OLD_PARAM_RE.sub(_replace, content)

        return {
            "name": _extract_title(content) or filepath.parent.name,
            "params": params,
            "template": template,
            "is_new_format": False,
        }


def _extract_title(content: str) -> str:
    m = re.match(r"^#\s+(.+)", content)
    return m.group(1).strip() if m else ""


def _normalize_params(raw_params, template: str) -> list[dict]:
    """将 YAML 中的 params 规范化为统一格式。"""
    if isinstance(raw_params, dict):
        result = []
        for name, spec in raw_params.items():
            if isinstance(spec, str):
                spec = {"type": "enum", "values": spec.split("|")}
            elif isinstance(spec, dict):
                pass
            else:
                spec = {"default": str(spec)}
            result.append({
                "name": name,
                "type": spec.get("type", "string"),
                "required": spec.get("required", True),
                "default": spec.get("default", ""),
                "desc": spec.get("desc", name),
                "values": spec.get("values", []),
            })
        return result
    elif isinstance(raw_params, list):
        return raw_params
    return []


def validate_params(params: list[dict], values: dict) -> tuple[bool, str]:
    """验证参数值，返回 (是否合法, 错误消息)。"""
    for p in params:
        name = p["name"]
        if name not in values or values[name] == "":
            if p["required"] and p["default"] == "":
                return False, f"缺少必要参数: {name}"
            continue

        val = values[name]
        ptype = p["type"]

        if ptype == "number":
            try:
                float(val)
            except ValueError:
                return False, f"参数 {name} 需要数字，得到: {val}"

        elif ptype == "bool":
            if val not in ("true", "false", True, False):
                return False, f"参数 {name} 需要布尔值 (true/false)，得到: {val}"

        elif ptype == "enum" and p.get("values"):
            allowed = set(p["values"])
            if val not in allowed:
                return False, f"参数 {name} 不在允许值中: {allowed}，得到: {val}"

    return True, ""


def apply_defaults(params: list[dict], values: dict) -> dict:
    """对未提供的参数应用默认值。"""
    result = dict(values)
    for p in params:
        if p["name"] not in result or result[p["name"]] == "":
            if "default" in p and p["default"] != "":
                result[p["name"]] = p["default"]
    return result
