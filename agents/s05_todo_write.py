from __future__ import annotations

import ast
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast

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
client = OpenAI(
    api_key=os.environ["API_KEY"],
    base_url=os.environ["BASE_URL"],
)
MODEL = os.environ["MODEL_ID"]
PLAN_REMINDER_INTERVAL = 3
SYSTEM = """You are a coding agent.
Use the todo tool for multi-step work.
Keep exactly one step in_progress when a task has multiple steps.
Refresh the plan as work advances. Prefer tools over prose."""


@dataclass
class PlanItem:
    content: str
    status: str = "pending"
    active_form: str = ""


@dataclass
class PlanningState:
    items: list[PlanItem] = field(default_factory=list)
    rounds_since_update: int = 0


class TodoManager:
    def __init__(self) -> None:
        self.state = PlanningState()

    def update(self, items: list[dict[str, Any]]) -> str:
        if len(items) > 12:
            raise ValueError("Keep the session plan short (max 12 items)")

        normalized: list[PlanItem] = []
        in_progress_count = 0

        for index, raw_item in enumerate(items):
            content = str(raw_item.get("content", "")).strip()
            status = str(raw_item.get("status", "pending")).lower()
            active_form = str(raw_item.get("active_form", "")).strip()

            if not content:
                raise ValueError(f"Item {index}: content required")
            if status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Item {index}: invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1

            normalized.append(
                PlanItem(
                    content=content,
                    status=status,
                    active_form=active_form,
                )
            )

        if in_progress_count > 1:
            raise ValueError("Only one plan item can be in_progress")

        self.state.items = normalized
        self.state.rounds_since_update = 0
        return self.render()

    def note_round_without_update(self) -> None:
        self.state.rounds_since_update += 1

    def reminder(self) -> str | None:
        if not self.state.items:
            return None
        if self.state.rounds_since_update < PLAN_REMINDER_INTERVAL:
            return None
        return "<reminder>Refresh your current plan before continuing.</reminder>"

    def render(self) -> str:
        if not self.state.items:
            return "No session plan yet."

        lines: list[str] = []
        for item in self.state.items:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }[item.status]
            line = f"{marker} {item.content}"
            if item.status == "in_progress" and item.active_form:
                line += f" ({item.active_form})"
            lines.append(line)

        completed = sum(1 for item in self.state.items if item.status == "completed")
        lines.append(f"\n({completed}/{len(self.state.items)} completed)")
        return "\n".join(lines)


TODO = TodoManager()


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
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
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


def _normalize_todos(todos: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "Error: todos must be a list or JSON array string"
    if not isinstance(todos, list):
        return None, "Error: todos must be a list"
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            return None, f"Error: todos[{i}] must be an object"
        if "content" not in t or "status" not in t:
            return None, f"Error: todos[{i}] missing 'content' or 'status'"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return None, f"Error: todos[{i}] has invalid status '{t['status']}'"
    return todos, None


def run_todo_write(todos: Any) -> str:
    normalized_todos, error = _normalize_todos(todos)
    if error:
        return error
    if normalized_todos is None:
        return "Error: todos must be a list"
    return TODO.update(normalized_todos)


def _tool_call_arguments(call: ChatCompletionMessageFunctionToolCall) -> dict[str, Any]:
    raw = call.function.arguments or "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON arguments for tool call {call.id}: {exc}") from exc
    if not isinstance(args, dict):
        raise ValueError(f"Tool call {call.id} did not return an object")
    return args


def _tool_call_to_param(
    call: ChatCompletionMessageFunctionToolCall,
) -> ChatCompletionMessageFunctionToolCallParam:
    return cast(
        ChatCompletionMessageFunctionToolCallParam,
        {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.function.name,
                "arguments": call.function.arguments,
            },
        },
    )


def _assistant_tool_message(
    content: str | None,
    tool_calls: list[ChatCompletionMessageFunctionToolCall],
) -> ChatCompletionAssistantMessageParam:
    message: dict[str, Any] = {
        "role": "assistant",
        "tool_calls": [_tool_call_to_param(call) for call in tool_calls],
    }
    if content is not None:
        message["content"] = content
    return cast(ChatCompletionAssistantMessageParam, message)


def _tool_result_message(
    call: ChatCompletionMessageFunctionToolCall,
    output: str,
) -> ChatCompletionToolMessageParam:
    return cast(
        ChatCompletionToolMessageParam,
        {
            "role": "tool",
            "tool_call_id": call.id,
            "content": output,
        },
    )


ToolHandler = Callable[..., str]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "glob": lambda **kw: run_glob(kw["pattern"]),
    "todo_write": lambda **kw: run_todo_write(kw["todos"]),
}

TOOLS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exact text in a file once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
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
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                                "active_form": {"type": "string"},
                            },
                            "required": ["content", "status"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["todos"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]


PLAN_REMINDER_INTERVAL = 3


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def agent_loop(messages: list[ChatCompletionMessageParam]) -> None:
    rounds_since_todo = 0
    while True:
        if rounds_since_todo >= PLAN_REMINDER_INTERVAL and messages:
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    {
                        "role": "user",
                        "content": "<reminder>Update your todos.</reminder>",
                    },
                )
            )
            rounds_since_todo = 0

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            max_tokens=8000,
        )
        message = response.choices[0].message
        tool_calls = [
            call
            for call in (message.tool_calls or [])
            if isinstance(call, ChatCompletionMessageFunctionToolCall)
        ]

        if tool_calls:
            messages.append(_assistant_tool_message(message.content, tool_calls))
            rounds_since_todo += 1

            for call in tool_calls:
                handler = TOOL_HANDLERS.get(call.function.name)
                try:
                    args = _tool_call_arguments(call)
                    output = handler(**args) if handler else f"Unknown: {call.function.name}"
                except Exception as exc:
                    output = f"Error: {exc}"
                if call.function.name == "todo_write":
                    rounds_since_todo = 0
                print(f"> {call.function.name}:")
                print(str(output)[:200])
                messages.append(_tool_result_message(call, str(output)))
            continue

        content = extract_text(message.content)
        if not content:
            raise RuntimeError("Model returned an empty assistant message")
        messages.append(
            cast(
                ChatCompletionMessageParam,
                {
                    "role": "assistant",
                    "content": content,
                },
            )
        )
        print(content)
        return


if __name__ == "__main__":
    print("s05: TodoWrite - plan before execute, nag if you forget")
    print("Type a question, press Enter. Type q to quit.\n")
    history: list[ChatCompletionMessageParam] = [
        cast(
            ChatCompletionMessageParam,
            {
                "role": "system",
                "content": SYSTEM,
            },
        )
    ]

    while True:
        try:
            query = input("\033[36ms05 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append(
            cast(
                ChatCompletionMessageParam,
                {
                    "role": "user",
                    "content": query,
                },
            )
        )
        agent_loop(history)
        print()
