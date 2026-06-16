from __future__ import annotations

import json
import os
import subprocess
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

SYSTEM = f"You are a coding agent at {WORKDIR}. Use the task tool to delegate exploration or subtasks."
SUBAGENT_SYSTEM = f"You are a coding subagent at {WORKDIR}. Complete the given task, then summarize your findings."


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
    except (FileNotFoundError, OSError) as exc:
        return f"Error: {exc}"

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
        content = file_path.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        file_path.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


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


ToolHandler = Callable[..., str]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}

CHILD_TOOLS: list[ChatCompletionToolParam] = [
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
            "description": "Replace exact text in a file.",
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

PARENT_TOOLS: list[ChatCompletionToolParam] = CHILD_TOOLS + [
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": "Spawn a subagent with fresh context. It shares the filesystem but not conversation history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "Short description of the task",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]


def run_subagent(prompt: str) -> str:
    sub_messages: list[ChatCompletionMessageParam] = [
        cast(
            ChatCompletionMessageParam,
            {
                "role": "user",
                "content": prompt,
            },
        )
    ]

    last_response_content: Any = None

    for _ in range(30):
        response = client.chat.completions.create(
            model=MODEL,
            messages=sub_messages,
            tools=CHILD_TOOLS,
            max_tokens=8000,
        )
        message = response.choices[0].message
        last_response_content = message.content

        tool_calls = [
            call
            for call in (message.tool_calls or [])
            if isinstance(call, ChatCompletionMessageFunctionToolCall)
        ]

        if tool_calls:
            sub_messages.append(_assistant_tool_message(message.content, tool_calls))

            for call in tool_calls:
                handler = TOOL_HANDLERS.get(call.function.name)
                try:
                    args = _tool_call_arguments(call)
                    output = handler(**args) if handler else f"Unknown tool: {call.function.name}"
                except Exception as exc:
                    output = f"Error: {exc}"
                sub_messages.append(_tool_result_message(call, str(output)))
            continue

        content = extract_text(message.content)
        if not content:
            raise RuntimeError("Subagent returned an empty assistant message")
        return content

    summary = extract_text(last_response_content)
    return summary or "(no summary)"


def agent_loop(messages: list[ChatCompletionMessageParam]) -> None:
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=PARENT_TOOLS,
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
                try:
                    args = _tool_call_arguments(call)
                    if call.function.name == "task":
                        desc = str(args.get("description", "subtask"))
                        prompt = str(args.get("prompt", ""))
                        print(f"> task ({desc}): {prompt[:80]}")
                        output = run_subagent(prompt)
                    else:
                        handler = TOOL_HANDLERS.get(call.function.name)
                        output = handler(**args) if handler else f"Unknown tool: {call.function.name}"
                except Exception as exc:
                    output = f"Error: {exc}"

                print(f"  {str(output)[:200]}")
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
            query = input("\033[36ms04 >> \033[0m")
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
        last_message = history[-1]
        if last_message.get("role") == "assistant":
            content = last_message.get("content")
            if isinstance(content, str) and content:
                print(content)
        print()
