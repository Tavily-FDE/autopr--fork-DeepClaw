"""技能系统 v2 — Jinja2 模板 + YAML 参数 + 步骤引擎。"""
import re
from pathlib import Path
from typing import Optional
from jinja2 import Environment, BaseLoader, nodes
from jinja2.ext import Extension

from deepclaw.config import CONFIG_DIR
from deepclaw.skill_parser import parse_skill_file, validate_params, apply_defaults

SKILLS_DIR = CONFIG_DIR / "skills"


# ──── Jinja2 自定义扩展：{% step name %}...{% endstep %} ────
class StepExtension(Extension):
    tags = {"step", "endstep"}
    def __init__(self, environment):
        super().__init__(environment)
        environment.extend(active_steps=[])

    def parse(self, parser):
        tag = next(parser.stream)
        lineno = tag.lineno
        if tag.value == "endstep":
            return nodes.Const("")
        name = self.parse_expression(parser)
        body = parser.parse_statements(["name:endstep"], drop_needle=True)
        self.environment.active_steps.append(name.value if hasattr(name, 'value') else str(name))
        return nodes.CallBlock(
            self.call_method("_render_step", [name]),
            [], [], body,
        ).set_lineno(lineno)

    def _render_step(self, name, caller):
        return ""


class StepStateExtension(Extension):
    """{% current_step %} 输出当前步骤名。"""
    tags = {"current_step"}
    def parse(self, parser):
        lineno = next(parser.stream).lineno
        return nodes.Output([self.call_method("_get_step", lineno=lineno)])

    def _get_step(self):
        steps = self.environment.active_steps
        return steps[-1] if steps else ""


# ──── Jinja2 环境 ────
_JINJA_ENV = Environment(
    loader=BaseLoader(),
    extensions=[StepExtension, StepStateExtension],
    autoescape=False,
    keep_trailing_newline=True,
)


def ensure_skills_dir():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def parse_skill(skill_path: Path, params: list[str] = None) -> Optional[dict]:
    """解析 SKILL.md（兼容旧 API），返回包含 rendered 的字典。"""
    parsed = parse_skill_file(skill_path)
    if not parsed:
        return None

    param_specs = parsed["params"]
    values = {}

    # 旧格式：params 是位置参数列表
    if params and not parsed["is_new_format"]:
        for i, v in enumerate(params):
            if i < len(param_specs):
                values[param_specs[i]["name"]] = v
    elif params:
        # 新格式：key=value 命名参数
        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                values[k.strip()] = v.strip()

    # 验证
    ok, err = validate_params(param_specs, values)
    if not ok:
        return {"_error": err}

    values = apply_defaults(param_specs, values)

    # Jinja2 渲染
    try:
        template = _JINJA_ENV.from_string(parsed["template"])
        # 重置步骤状态
        _JINJA_ENV.active_steps = []
        rendered = template.render(**values)
    except Exception as e:
        rendered = parsed["template"]  # 渲染失败退回原文

    # 移除残留的 Jinja2 未替换标签
    rendered = re.sub(r'{%[^%]*%}', '', rendered)
    rendered = re.sub(r'\{\{[^}]*\}\}', '', rendered)

    dir_name = skill_path.parent.name
    return {
        "name": parsed["name"],
        "dir_name": dir_name,
        "description": _extract_description(parsed["template"]),
        "instructions": rendered,
        "instructions_raw": parsed["template"],
        "params": values,
        "param_specs": param_specs,
        "is_new_format": parsed["is_new_format"],
    }


def get_skill_param_specs(name: str) -> list[dict]:
    """获取技能的参数规格（用于交互式表单）。"""
    ensure_skills_dir()
    skill_dir = SKILLS_DIR / name
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return []
    parsed = parse_skill_file(md)
    return parsed["params"] if parsed else []


def get_expected_param_count(name: str) -> int:
    """旧 API 兼容：返回技能需要的位置参数数量。"""
    ensure_skills_dir()
    skill_dir = SKILLS_DIR / name
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return 0
    parsed = parse_skill_file(md)
    if not parsed:
        return 0
    return sum(1 for p in parsed["params"] if p.get("required", True) and p.get("default", "") == "")


def load_skill(name: str, params: list[str] = None) -> Optional[dict]:
    """加载技能（兼容旧 API）。"""
    ensure_skills_dir()
    skill_dir = SKILLS_DIR / name
    if not skill_dir.is_dir():
        return None
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return None
    return parse_skill(md, params or [])


def list_skills() -> list[dict]:
    """列出所有可用技能。"""
    ensure_skills_dir()
    skills = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if d.is_dir():
            md = d / "SKILL.md"
            if md.exists():
                parsed = parse_skill_file(md)
                if parsed:
                    skills.append({
                        "name": parsed["name"],
                        "dir_name": d.name,
                        "description": _extract_description(parsed["template"]),
                        "param_specs": parsed["params"],
                    })
    return skills


def build_skill_prompt(skills: list[dict]) -> str:
    """构建技能提示词片段。"""
    if not skills:
        return ""
    lines = ["\n## 已加载的技能\n"]
    for s in skills:
        name = s["name"]
        params = s.get("params", {})
        if params:
            param_str = ", ".join(f"{k}={v}" for k, v in params.items())
            name += f" ({param_str})"
        lines.append(f"### {name}")
        if s.get("instructions"):
            lines.append(s["instructions"])
    return "\n".join(lines)


def _extract_description(template: str) -> str:
    m = re.search(r"\*\*Description\*\*:\s*(.+?)(?:\n|$)", template)
    if m:
        return m.group(1).strip()
    m = re.search(r"#\s+(.+)\n+([^\n]+)", template)
    if m:
        return m.group(2).strip()
    return ""
