from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, cast

import yaml
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
)

load_dotenv(override=True)

WORKDIR = Path.cwd().resolve()
SKILLS_DIR = WORKDIR / "skills"
client = OpenAI(api_key=os.environ["API_KEY"], base_url=os.environ["BASE_URL"])
MODEL = os.environ["MODEL_ID"]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, parts[2].strip()


SKILL_REGISTRY: dict[str, dict[str, str]] = {}


def _scan_skills() -> None:
    if not SKILLS_DIR.exists():
        return
    for directory in sorted(SKILLS_DIR.iterdir()):
        if not directory.is_dir():
            continue
        manifest = directory / "SKILL.md"
        if not manifest.exists():
            continue
        raw = manifest.read_text()
        meta, _ = _parse_frontmatter(raw)
        name = str(meta.get("name", directory.name))
        description = str(meta.get("description", raw.splitlines()[0].lstrip("#").strip()))
        SKILL_REGISTRY[name] = {"name": name, "description": description, "content": raw}


_scan_skills()


def list_skills() -> str:
    if not SKILL_REGISTRY:
        return "(no skills found)"
    return "\n".join(f"- **{skill['name']}**: {skill['description']}" for skill in SKILL_REGISTRY.values())


def build_system() -> str:
    return (
        f"You are a coding agent at {WORKDIR}. "
        f"Skills available:\n{list_skills()}\n"
        "Use load_skill to get full details when needed."
    )


SYSTEM = build_system()
SUB_SYSTEM = f"You are a coding agent at {WORKDIR}. Complete the given task, then return a concise summary. Do not delegate further."


def safe_path(path_str: str) -> Path:
    path = (WORKDIR / path_str).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {path_str}")
    return path


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(command, shell=True, cwd=WORKDIR, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    output = (result.stdout + result.stderr).strip()
    return output[:50000] if output else "(no output)"


def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit is not None and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text()
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_glob(pattern: str) -> str:
    import glob as g

    try:
        results: list[str] = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as exc:
        return f"Error: {exc}"


def load_skill(name: str) -> str:
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        return f"Skill not found: {name}"
    return skill["content"]


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "\n".join(getattr(block, "text", "") for block in content if getattr(block, "type", None) == "text").strip()


def _tool_call_arguments(call: ChatCompletionMessageFunctionToolCall) -> dict[str, Any]:
    raw = call.function.arguments or "{}"
    args = json.loads(raw)
    if not isinstance(args, dict):
        raise ValueError(f"Tool call {call.id} did not return an object")
    return args


def _tool_call_to_param(call: ChatCompletionMessageFunctionToolCall) -> ChatCompletionMessageFunctionToolCallParam:
    return cast(ChatCompletionMessageFunctionToolCallParam, {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}})


def _assistant_tool_message(content: str | None, tool_calls: list[ChatCompletionMessageFunctionToolCall]) -> ChatCompletionAssistantMessageParam:
    message: dict[str, Any] = {"role": "assistant", "tool_calls": [_tool_call_to_param(call) for call in tool_calls]}
    if content is not None:
        message["content"] = content
    return cast(ChatCompletionAssistantMessageParam, message)


def _tool_result_message(call: ChatCompletionMessageFunctionToolCall, output: str) -> ChatCompletionToolMessageParam:
    return cast(ChatCompletionToolMessageParam, {"role": "tool", "tool_call_id": call.id, "content": output})


ToolHandler = Callable[..., str]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "glob": lambda **kw: run_glob(kw["pattern"]),
    "todo_write": lambda **kw: run_todo_write(kw["todos"]),
    "load_skill": lambda **kw: load_skill(kw["name"]),
}


def run_todo_write(todos: list[dict[str, Any]]) -> str:
    return f"Updated {len(todos)} tasks"


SUB_TOOLS: list[ChatCompletionToolParam] = [
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}, "strict": True}},
    {"type": "function", "function": {"name": "read_file", "description": "Read file contents.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}, "strict": True}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to a file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}, "strict": True}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace exact text in a file once.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"], "additionalProperties": False}, "strict": True}},
    {"type": "function", "function": {"name": "glob", "description": "Find files matching a glob pattern.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"], "additionalProperties": False}, "strict": True}},
]


def spawn_subagent(task: str) -> str:
    messages: list[ChatCompletionMessageParam] = [cast(ChatCompletionMessageParam, {"role": "user", "content": task})]
    for _ in range(30):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=SUB_TOOLS, max_tokens=8000)
        message = response.choices[0].message
        tool_calls = [call for call in (message.tool_calls or []) if isinstance(call, ChatCompletionMessageFunctionToolCall)]
        if tool_calls:
            messages.append(_assistant_tool_message(message.content, tool_calls))
            for call in tool_calls:
                handler = TOOL_HANDLERS.get(call.function.name)
                try:
                    output = handler(**_tool_call_arguments(call)) if handler else f"Unknown: {call.function.name}"
                except Exception as exc:
                    output = f"Error: {exc}"
                messages.append(_tool_result_message(call, str(output)))
            continue
        summary = extract_text(message.content)
        if not summary:
            raise RuntimeError("Subagent returned an empty assistant message")
        return summary
    return "(no summary)"


TOOLS: list[ChatCompletionToolParam] = [
    *SUB_TOOLS,
    {
        "type": "function",
        "function": {
            "name": "todo_write",
            "description": "Create and manage a task list for your current coding session.",
            "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                    "content": {
                        "type": "string"
                    },
                    "status": {
                        "type": "string",
                        "enum": [
                        "pending",
                        "in_progress",
                        "completed"
                        ]
                    },
                    "active_form": {
                        "type": "string"
                    }
                    },
                    "required": [
                    "content",
                    "status"
                    ],
                    "additionalProperties": False
                }
                }
            },
            "required": [
                "todos"
            ],
            "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": "Launch a subagent to handle a complex subtask. Returns only the final conclusion.",
            "parameters": {
            "type": "object",
            "properties": {
                "description": {
                "type": "string"
                }
            },
            "required": [
                "description"
            ],
            "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "Load the full content of a skill by name.",
            "parameters": {
            "type": "object",
            "properties": {
                "name": {
                "type": "string"
                }
            },
            "required": [
                "name"
            ],
            "additionalProperties": False
            },
            "strict": True
        }
    },
]


def agent_loop(messages: list[ChatCompletionMessageParam]) -> None:
    while True:
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS, max_tokens=8000)
        message = response.choices[0].message
        tool_calls = [call for call in (message.tool_calls or []) if isinstance(call, ChatCompletionMessageFunctionToolCall)]
        if tool_calls:
            messages.append(_assistant_tool_message(message.content, tool_calls))
            for call in tool_calls:
                handler = TOOL_HANDLERS.get(call.function.name)
                try:
                    args = _tool_call_arguments(call)
                    output = spawn_subagent(args["description"]) if call.function.name == "task" else handler(**args) if handler else f"Unknown: {call.function.name}"
                except Exception as exc:
                    output = f"Error: {exc}"
                messages.append(_tool_result_message(call, str(output)))
            continue
        content = extract_text(message.content)
        if not content:
            raise RuntimeError("Model returned an empty assistant message")
        messages.append(cast(ChatCompletionMessageParam, {"role": "assistant", "content": content}))
        print(content)
        return


if __name__ == "__main__":
    print("s07: Skill Loading - English runtime")
    print("Type a question, press Enter. Type q to quit.\n")
    history: list[ChatCompletionMessageParam] = [cast(ChatCompletionMessageParam, {"role": "system", "content": SYSTEM})]
    while True:
        try:
            query = input("\033[36ms07 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append(cast(ChatCompletionMessageParam, {"role": "user", "content": query}))
        agent_loop(history)
        print()
