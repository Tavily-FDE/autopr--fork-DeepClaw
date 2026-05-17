import json
from openai import OpenAI
import httpx

from deepclaw.config import load_config
from deepclaw.tools import TOOLS as BASE_TOOLS, execute_tool as execute_base_tool
from deepclaw.skill import load_skill, build_skill_prompt
from deepclaw.plugin import (
    get_all_plugin_tools,
    execute_plugin_tool,
    get_event_bus,
)

SYSTEM_PROMPT = """\
你是 DeepClaw，一个运行在用户本地的 AI 助手。\
你可以使用工具来读取文件、写入文件、列出目录、搜索文件内容、执行 shell 命令、联网搜索、访问网页。\
当用户给你任务时，主动使用工具来完成。用中文回复，友好且有所帮助。"""


class DeepClawAgent:
    MAX_ITERATIONS = 10
    MAX_CONTEXT_TOKENS = 6000
    COMPRESS_KEEP_LAST = 4

    def __init__(self, config: dict = None, messages: list = None):
        if config is None:
            config = load_config()
        self.client = OpenAI(
            api_key=config["auth_token"],
            base_url=config["base_url"],
            timeout=httpx.Timeout(connect=30.0, read=90.0, write=30.0, pool=10.0),
            max_retries=2,
        )
        self.model = config["model"]
        self._loaded_skills = []
        self.messages = messages or self._build_system_msg()

    def _build_system_msg(self) -> list:
        """构建包含技能指令的系统消息。"""
        prompt = SYSTEM_PROMPT + build_skill_prompt(self._loaded_skills)
        return [{"role": "system", "content": prompt}]

    def _rebuild_system(self):
        """重建系统消息并保留对话历史。"""
        old_system = self.messages[0] if self.messages else None
        new_system = self._build_system_msg()[0]
        if old_system and old_system["content"] == new_system["content"]:
            return
        conversation = [m for m in self.messages if m["role"] != "system"]
        self.messages = [new_system] + conversation

    def get_messages(self) -> list:
        return list(self.messages)

    def load_messages(self, messages: list):
        self.messages = list(messages) if messages else self._build_system_msg()
        # 保留已加载技能但重建系统提示
        if self._loaded_skills:
            self._rebuild_system()

    def activate_skill(self, name: str, params: list[str] = None) -> bool:
        """激活一个技能（用目录名匹配），支持参数替换。"""
        skill = load_skill(name, params or [])
        if not skill:
            return False
        # 去重（按目录名）
        self._loaded_skills = [s for s in self._loaded_skills if s["dir_name"] != skill["dir_name"]]
        self._loaded_skills.append(skill)
        self._rebuild_system()
        return True

    def deactivate_skill(self, name: str) -> bool:
        """停用指定技能（用目录名匹配）。"""
        before = len(self._loaded_skills)
        self._loaded_skills = [s for s in self._loaded_skills if s["dir_name"] != name]
        if len(self._loaded_skills) != before:
            self._rebuild_system()
            return True
        return False

    def deactivate_all_skills(self):
        """停用所有技能。"""
        if self._loaded_skills:
            self._loaded_skills = []
            self._rebuild_system()

    def get_loaded_skills(self) -> list[dict]:
        return list(self._loaded_skills)

    def _estimate_tokens(self, messages: list = None) -> int:
        """粗略估算消息列表的 token 数（4 字符 ≈ 1 token）。"""
        msgs = messages or self.messages
        total = 0
        for m in msgs:
            total += len(m.get("content", ""))
            for tc in m.get("tool_calls", []):
                total += len(tc.get("function", {}).get("arguments", ""))
        return total // 4

    def _compress_history(self):
        """压缩历史对话：将早期消息替换为摘要。"""
        msgs = self.messages

        # 跳过系统消息
        non_system = [m for m in msgs if m["role"] != "system"]
        if len(non_system) <= self.COMPRESS_KEEP_LAST + 4:
            return  # 消息太少，不值得压缩

        # 分离：要压缩的部分 + 保留的部分
        to_compress = non_system[:-self.COMPRESS_KEEP_LAST]
        to_keep = non_system[-self.COMPRESS_KEEP_LAST:]

        # 构建摘要请求
        compress_lines = []
        for m in to_compress:
            role = m["role"]
            content = m.get("content", "")[:500]  # 截断每条消息
            compress_lines.append(f"[{role}]: {content}")

        compress_prompt = (
            "Summarize the following conversation history into a concise paragraph. "
            "Keep key information: file names, decisions, code changes, user preferences:\n\n"
            + "\n".join(compress_lines)
            + "\n\nSummary:"
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": compress_prompt}],
                max_tokens=300,
                stream=False,
            )
            summary = resp.choices[0].message.content.strip()
        except Exception:
            summary = f"(对话历史，共 {len(to_compress)} 条消息)"

        # 重建消息列表：保持系统消息 + 注入上下文摘要 + 保留最近对话
        system_msgs = [m for m in msgs if m["role"] == "system"]
        # 将摘要追加到系统消息中（复制避免修改原消息）
        if system_msgs:
            new_system = dict(system_msgs[0])
            new_system["content"] += f"\n\n[对话历史摘要] {summary}"
            system_msgs = [new_system]
        else:
            system_msgs = [{"role": "system", "content": f"[对话历史摘要] {summary}"}]
        self.messages = system_msgs + to_keep

    def chat(self, user_input: str) -> str:
        """同步聊天，返回完整回复文本。"""
        result = []
        for event in self.chat_stream(user_input):
            if event[0] == "text":
                result.append(event[1])
            elif event[0] == "done":
                return event[1]
            elif event[0] == "error":
                return event[1]
        return "".join(result)

    def _get_active_tools(self) -> list:
        """返回当前生效的工具列表（内置 + 插件）。"""
        return BASE_TOOLS + get_all_plugin_tools()

    def _execute_tool(self, name: str, arguments: dict) -> str:
        """执行工具，优先路由到插件（通过新 API）。"""
        result = execute_plugin_tool(name, arguments)
        if result is not None:
            return result
        return execute_base_tool(name, arguments)

    def chat_stream(self, user_input: str):
        """流式聊天，逐 token 产出。yield ("text", "token") / ("tool_name", "name") / ("done", full_text)。"""
        # 上下文压缩检查
        self.messages.append({"role": "user", "content": user_input})
        if self._estimate_tokens() > self.MAX_CONTEXT_TOKENS:
            self.messages.pop()
            self._compress_history()
            self.messages.append({"role": "user", "content": user_input})

        # 事件：对话前
        get_event_bus().emit("chat:before", self.messages)

        for _ in range(self.MAX_ITERATIONS):
            full_content = ""
            full_reasoning = ""      # DeepSeek reasoner 推理内容
            tool_calls_acc = {}
            finish_reason = None

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self._get_active_tools(),
                stream=True,
                max_tokens=4096,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason

                # DeepSeek reasoner 推理内容
                if getattr(delta, "reasoning_content", None):
                    full_reasoning += delta.reasoning_content
                    yield ("reasoning", delta.reasoning_content)

                # 文本内容
                if delta.content:
                    full_content += delta.content
                    yield ("text", delta.content)

                # 工具调用（流式累积）
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        acc = tool_calls_acc[idx]
                        if tc_delta.id:
                            acc["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            acc["function"]["name"] += tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            acc["function"]["arguments"] += tc_delta.function.arguments

            # 流结束后处理工具调用
            if tool_calls_acc:
                tc_sorted = [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())]

                # 确保每个 tool_call 有 id
                for i, tc in enumerate(tc_sorted):
                    if not tc["id"]:
                        tc["id"] = f"call_{i}_{id(tc)}"

                assistant_msg = {
                    "role": "assistant",
                    "content": full_content or None,
                    "tool_calls": tc_sorted,
                }
                if full_reasoning:
                    assistant_msg["reasoning_content"] = full_reasoning
                self.messages.append(assistant_msg)

                for tc in tc_sorted:
                    func_name = tc["function"]["name"]
                    yield ("tool_call", func_name)
                    try:
                        func_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError as je:
                        func_args = {}
                        yield ("text", f"\n[工具参数解析错误: {je}]")
                    result = self._execute_tool(func_name, func_args)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
                continue  # 继续循环，模型会基于工具结果回复

            # 纯文本回复
            assistant_msg = {"role": "assistant", "content": full_content}
            if full_reasoning:
                assistant_msg["reasoning_content"] = full_reasoning
            self.messages.append(assistant_msg)
            if finish_reason == "length":
                full_content += "\n\n[响应被截断，请继续或简化问题]"
                yield ("text", "\n\n[响应被截断，请继续或简化问题]")
            # 事件：对话后
            get_event_bus().emit("chat:after", full_content)
            yield ("done", full_content)
            return

        yield ("error", "(已达到最大工具调用次数)")

    def reset(self):
        self.messages = self._build_system_msg()
