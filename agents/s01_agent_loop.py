from dataclasses import dataclass
import json
import os
import shlex
import subprocess
from typing import Any, cast

try:
    import readline
    # #143 UTF-8 backspace fix for macOS libedit
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
    readline.parse_and_bind('set enable-meta-keybindings on')
except ImportError:
    pass

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageToolCall,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
)

load_dotenv(override=True)

client = OpenAI(
    api_key=os.environ["API_KEY"],
    base_url=os.environ["BASE_URL"],
)
MODEL = os.environ["MODEL_ID"]

SYSTEM = (
    f"you are a helpful assistant and coding agent at {os.getcwd()}."
)

TOOLS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run a shell command in the current workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "the bash command to run",
                    }
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]

BLOCKED_SUBSTRINGS = ("rm -rf /", "sudo", "shutdown", "reboot", ":(){:|:&};:")


@dataclass
class LoopState:
    messages: list[ChatCompletionMessageParam]

def run_bash(command: str) -> str:
    command = command.strip()
    if not command:
        return "Error: empty command"

    if any(item in command for item in BLOCKED_SUBSTRINGS):
        return "Error: Dangerous command blocked"

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return f"Error: invalid command syntax: {exc}"

    if not args:
        return "Error: empty command"

    try:
        result = subprocess.run(
            args,
            shell=False,
            cwd=os.getcwd(),
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

def _to_output_string(result) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)

def _tool_call_to_param(call: ChatCompletionMessageToolCall) -> dict[str, Any]:
    return {
        "id": call.id,
        "type": "function",
        "function": {
            "name": call.function.name,
            "arguments": call.function.arguments,
        },
    }


def execute_tool_calls(
    tool_calls: list[ChatCompletionMessageFunctionToolCall],
) -> list[ChatCompletionToolMessageParam]:
    results: list[ChatCompletionToolMessageParam] = []
    for call in tool_calls:
        if call.function.name != "run_bash":
            raise ValueError(f"Unknown tool: {call.function.name}")

        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON arguments for tool call {call.id}: {exc}") from exc

        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(f"Tool call {call.id} is missing a command string")

        print(f"\033[33m$ {command}\033[0m")
        output = run_bash(command)
        display_output = output if len(output) <= 500 else f"{output[:500]}\n...[truncated]"
        print(display_output)

        results.append(
            cast(
                ChatCompletionToolMessageParam,
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _to_output_string(output),
                },
            )
        )

    return results


def run_one_turn(state: LoopState) -> bool:
    response = client.chat.completions.create(
        model=MODEL,
        messages=state.messages,
        tools=TOOLS,
        max_tokens=8000,
        extra_body={"thinking": {"type": "disabled"}},
    )

    message = response.choices[0].message
    tool_calls = [
        call
        for call in (message.tool_calls or [])
        if isinstance(call, ChatCompletionMessageToolCall) and call.type == "function"
    ]

    if tool_calls:
        assistant_message = cast(
            ChatCompletionAssistantMessageParam,
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [_tool_call_to_param(call) for call in tool_calls],
            },
        )
        state.messages.append(assistant_message)
        state.messages.extend(execute_tool_calls(tool_calls))
        return True

    content = message.content
    if not content:
        raise RuntimeError("DeepSeek returned an empty assistant message")

    state.messages.append(
        {
            "role": "assistant",
            "content": content,
        },
    )
    print(content)
    return False


def agent_loop(state: LoopState) -> None:
    while run_one_turn(state):
        pass


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
            query = input("\033[36ms01 >> \033[0m")
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
        state = LoopState(messages=history)
        agent_loop(state)
        print()
