from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam


def create_openai_adapter(api_key: str, base_url: str) -> _OpenAIAdapterClient:
    return _OpenAIAdapterClient(OpenAI(api_key=api_key, base_url=base_url))


class _OpenAIAdapterClient:
    def __init__(self, client: OpenAI):
        self.chat = _OpenAIAdapterChat(client)
        self.messages = _OpenAIAdapterMessages(client)


class _OpenAIAdapterChat:
    def __init__(self, client: OpenAI):
        self.completions = _OpenAIAdapterMessages(client)


class _OpenAIAdapterMessages:
    def __init__(self, client: OpenAI):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: list[Any],
        tools: list[Any] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Any:
        payload: list[ChatCompletionMessageParam] = []
        if system:
            payload.append(cast(ChatCompletionMessageParam, {"role": "system", "content": system}))
        payload.extend(_convert_messages(messages))
        openai_tools = _convert_tools(tools)
        kwargs.pop("extra_body", None)
        request: dict[str, Any] = {
            "model": model,
            "messages": cast(list[ChatCompletionMessageParam], payload),
        }
        if openai_tools is not None:
            request["tools"] = openai_tools
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        request.update(kwargs)
        completion_create = cast(Any, self._client.chat.completions.create)
        completion = completion_create(**request)
        return _OpenAIAdapterResponse(completion.choices[0].message)


class _OpenAIAdapterResponse:
    def __init__(self, message: Any):
        self.content = []
        text = _message_text(message)
        if text:
            self.content.append(SimpleNamespace(type="text", text=text))

        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            self.content.append(
                SimpleNamespace(
                    type="tool_use",
                    id=call.id,
                    name=call.function.name,
                    input=_parse_json(call.function.arguments),
                )
            )

        finish_reason = getattr(message, "finish_reason", None)
        self.stop_reason = "tool_use" if tool_calls else _finish_reason_to_stop_reason(finish_reason)


def _finish_reason_to_stop_reason(finish_reason: str | None) -> str | None:
    if finish_reason == "length":
        return "max_tokens"
    if finish_reason in {"tool_calls", "stop"}:
        return None
    return finish_reason


def _parse_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if _block_type(block) == "text":
                text = _block_text(block)
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _convert_tools(tools: list[Any] | None) -> list[ChatCompletionToolParam] | None:
    if not tools:
        return None
    converted: list[ChatCompletionToolParam] = []
    for tool in tools:
        if isinstance(tool, dict) and tool.get("type") == "function" and "function" in tool:
            converted.append(cast(ChatCompletionToolParam, tool))
            continue
        converted.append(
            cast(
                ChatCompletionToolParam,
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get(
                            "input_schema",
                            {"type": "object", "properties": {}, "required": []},
                        ),
                        "strict": tool.get("strict", True),
                    },
                },
            )
        )
    return converted


def _convert_messages(messages: list[Any]) -> list[ChatCompletionMessageParam]:
    converted: list[ChatCompletionMessageParam] = []
    for message in messages:
        role = _msg_get(message, "role")
        content = _msg_get(message, "content")

        if role == "assistant":
            assistant: dict[str, Any] = {"role": "assistant"}
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []

            if isinstance(content, list):
                for block in content:
                    block_type = _block_type(block)
                    if block_type == "text":
                        text = _block_text(block)
                        if text:
                            text_parts.append(text)
                    elif block_type == "tool_use":
                        tool_calls.append(
                            {
                                "id": _block_attr(block, "id"),
                                "type": "function",
                                "function": {
                                    "name": _block_attr(block, "name"),
                                    "arguments": json.dumps(_block_attr(block, "input") or {}),
                                },
                            }
                        )
            elif content is not None:
                assistant["content"] = content

            if text_parts:
                assistant["content"] = "\n".join(text_parts)
            elif "content" not in assistant and not tool_calls:
                assistant["content"] = None

            if tool_calls:
                assistant["tool_calls"] = tool_calls

            converted.append(cast(ChatCompletionMessageParam, assistant))
            continue

        if role == "user" and isinstance(content, list):
            tool_results = [block for block in content if _block_type(block) == "tool_result"]
            text_parts = [_block_text(block) for block in content if _block_type(block) == "text"]

            if tool_results and not text_parts:
                for block in tool_results:
                    converted.append(
                        cast(
                            ChatCompletionMessageParam,
                            {
                                "role": "tool",
                                "tool_call_id": str(
                                    _block_attr(block, "tool_use_id") or _block_attr(block, "tool_call_id")
                                ),
                                "content": str(_block_attr(block, "content") or ""),
                            },
                        )
                    )
                continue

            if text_parts:
                converted.append(
                    cast(
                        ChatCompletionMessageParam,
                        {"role": "user", "content": "\n".join(part for part in text_parts if part)},
                    )
                )
                continue

        if role == "tool":
            converted.append(
                cast(
                    ChatCompletionMessageParam,
                    {
                        "role": "tool",
                        "tool_call_id": str(_msg_get(message, "tool_call_id") or ""),
                        "content": str(content or ""),
                    },
                )
            )
            continue

        converted.append(cast(ChatCompletionMessageParam, {"role": role, "content": content}))
    return converted


def _msg_get(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


def _block_attr(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _block_type(block: Any) -> str | None:
    return _block_attr(block, "type")


def _block_text(block: Any) -> str:
    text = _block_attr(block, "text", "")
    return str(text) if text is not None else ""
