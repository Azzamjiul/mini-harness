import json
import subprocess

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
import os
from pathlib import Path
from typing import Any, Callable, cast

load_dotenv(override=True)

WORKDIR = Path.cwd().resolve()
client = OpenAI(
    api_key=os.environ["API_KEY"],
    base_url=os.environ["BASE_URL"],
)
MODEL = os.environ["MODEL_ID"]

SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks. Act, don't explain."

def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes the workspace: {p}")
    return path

def run_bash(command: str) -> str:
    dangerous = ("rm -rf /", "sudo", "shutdown", "reboot", "> /dev/")
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"

    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR, capture_output=True, text=True, timeout=120)

        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as exc:
        return f"Error: {exc}"

def run_read(path: str, limit: int | None = None) -> str:
    try:
        text = safe_path(path).read_text()
        lines = text.splitlines()
        if limit is not None and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

# Concurrency safety classification
CONCURRENCY_SAFE = {"read_file"}
CONCURRENCY_UNSAFE = {"write_file", "edit_file"}

# Dispatch map
ToolHandler = Callable[..., str]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}

TOOLS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
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
            "description": "Write content to file.",
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
            "description": "Replace exact text in file.",
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
]

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


def _tool_call_result_message(
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


def _assistant_tool_message(
    content: str | None,
    tool_calls: list[ChatCompletionMessageFunctionToolCall],
) -> ChatCompletionAssistantMessageParam:
    return cast(
        ChatCompletionAssistantMessageParam,
        {
            "role": "assistant",
            "content": content,
            "tool_calls": [_tool_call_to_param(call) for call in tool_calls],
        },
    )


def _tool_call_arguments(call: ChatCompletionMessageFunctionToolCall) -> dict[str, Any]:
    raw = call.function.arguments or "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON arguments for tool call {call.id}: {exc}") from exc
    if not isinstance(args, dict):
        raise ValueError(f"Tool call {call.id} did not return an object")
    return args


def agent_loop(messages: list[ChatCompletionMessageParam]) -> None:
    while True:
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

            for call in tool_calls:
                handler = TOOL_HANDLERS.get(call.function.name)
                if not handler:
                    output = f"Unknown tool: {call.function.name}"
                else:
                    try:
                        output = handler(**_tool_call_arguments(call))
                    except Exception as exc:
                        output = f"Error: {exc}"
                print(f"> {call.function.name}:")
                print(output[:200])
                messages.append(_tool_call_result_message(call, output))
            continue

        content = message.content or ""
        if not content.strip():
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
    history: list[ChatCompletionMessageParam] = [
        cast(
            ChatCompletionMessageParam,
            {"role": "system", "content": SYSTEM},
        )
    ]
    while True:
        try:
            query = input("\033[36ms02 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append(
            cast(
                ChatCompletionMessageParam,
                {"role": "user", "content": query},
            )
        )
        agent_loop(history)
        print()
