"""Protocol strategies for serving Responses over native and legacy APIs.

The adapters implement the common, portable Responses subset on top of native
Responses, OpenAI-compatible Chat Completions, and Anthropic-compatible
Messages transports.
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Optional


class UnsupportedResponsesFeature(ValueError):
    """A Responses feature cannot be represented by the selected upstream."""


STRUCTURED_OUTPUT_TOOL = "__gateway_structured_output"
STRUCTURED_OUTPUT_INSTRUCTION = (
    f"Return the final answer by calling the {STRUCTURED_OUTPUT_TOOL} tool exactly once "
    "with arguments that match its JSON schema. Do not include prose outside the tool call."
)


def _id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:24]


def _text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") in {
            "text", "input_text", "output_text",
        }:
            parts.append(str(part.get("text") or ""))
    return "".join(parts)


def _validate_portable(body: dict) -> None:
    unsupported = []
    for key in ("previous_response_id", "conversation", "background"):
        if body.get(key) not in (None, False):
            unsupported.append(key)
    if body.get("store") is True:
        unsupported.append("store=true")
    for tool in body.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            unsupported.append(f"tools.{tool.get('type', 'unknown') if isinstance(tool, dict) else 'unknown'}")
    if unsupported:
        names = ", ".join(sorted(set(unsupported)))
        raise UnsupportedResponsesFeature(
            f"Responses compatibility mode cannot emulate: {names}"
        )


def _response_items(body: dict) -> list:
    value = body.get("input")
    if value is None:
        return []
    if isinstance(value, str):
        return [{"type": "message", "role": "user", "content": value}]
    if not isinstance(value, list):
        raise UnsupportedResponsesFeature("input must be a string or an array of items")
    return value


def _chat_content(content) -> str | list[dict]:
    if isinstance(content, str):
        return content
    result: list[dict] = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, str):
            result.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind in {"text", "input_text", "output_text"}:
            result.append({"type": "text", "text": part.get("text", "")})
        elif kind in {"input_image", "image_url"}:
            image = part.get("image_url")
            if isinstance(image, str):
                value = {"url": image}
                if part.get("detail"):
                    value["detail"] = part["detail"]
                result.append({"type": "image_url", "image_url": value})
            elif isinstance(image, dict) and image.get("url"):
                result.append({"type": "image_url", "image_url": image})
            else:
                raise UnsupportedResponsesFeature(
                    "input_image requires image_url in compatibility mode"
                )
        else:
            raise UnsupportedResponsesFeature(f"unsupported content part type: {kind}")
    return result


def _chat_tool_choice(choice):
    if isinstance(choice, dict) and choice.get("type") == "function":
        return {"type": "function", "function": {"name": choice.get("name")}}
    return choice


def structured_output_format(body: dict) -> Optional[dict]:
    """Return a Responses JSON output format that needs legacy emulation."""
    text = body.get("text") or {}
    fmt = text.get("format") if isinstance(text, dict) else None
    if isinstance(fmt, dict) and fmt.get("type") in {"json_schema", "json_object"}:
        return fmt
    return None


def _structured_schema(fmt: dict) -> dict:
    if fmt.get("type") == "json_schema":
        schema = fmt.get("schema")
        if not isinstance(schema, dict):
            raise UnsupportedResponsesFeature("text.format.schema must be a JSON Schema object")
        return schema
    return {"type": "object", "additionalProperties": True}


def _chat_structured_tool(fmt: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": STRUCTURED_OUTPUT_TOOL,
            "description": "Return the final answer as an object matching the supplied schema.",
            "parameters": _structured_schema(fmt),
        },
    }


def _messages_structured_tool(fmt: dict) -> dict:
    return {
        "name": STRUCTURED_OUTPUT_TOOL,
        "description": "Return the final answer as an object matching the supplied schema.",
        "input_schema": _structured_schema(fmt),
    }


def _append_instruction(current: object, instruction: str) -> str:
    value = str(current).strip() if current else ""
    return f"{value}\n\n{instruction}" if value else instruction


def _add_chat_instruction(messages: list[dict], instruction: str) -> None:
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] = _append_instruction(
            messages[0].get("content"), instruction
        )
        return
    messages.insert(0, {"role": "system", "content": instruction})


def responses_to_native_structured_request(body: dict) -> dict:
    """Emulate unavailable native JSON formatting with an automatic function tool."""
    _validate_portable(body)
    fmt = structured_output_format(body)
    if fmt is None:
        return dict(body)
    if body.get("tools"):
        raise UnsupportedResponsesFeature(
            "structured-output emulation cannot be combined with client function tools"
        )
    out = dict(body)
    text = dict(out.get("text") or {})
    text.pop("format", None)
    if text:
        out["text"] = text
    else:
        out.pop("text", None)
    out["tools"] = [{
        "type": "function",
        "name": STRUCTURED_OUTPUT_TOOL,
        "description": "Return the final answer as an object matching the supplied schema.",
        "parameters": _structured_schema(fmt),
    }]
    # Omitting tool_choice is equivalent to automatic selection and remains
    # compatible with providers that prohibit forced tools while thinking.
    out.pop("tool_choice", None)
    out["instructions"] = _append_instruction(
        out.get("instructions"), STRUCTURED_OUTPUT_INSTRUCTION
    )
    return out


def responses_to_chat_request(body: dict, upstream_model: str) -> dict:
    """Translate the portable Responses request subset to Chat Completions."""
    _validate_portable(body)
    messages: list[dict] = []
    if body.get("instructions"):
        messages.append({"role": "system", "content": str(body["instructions"])})

    for item in _response_items(body):
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        kind = item.get("type", "message")
        if kind == "message":
            messages.append({
                "role": item.get("role", "user"),
                "content": _chat_content(item.get("content")),
            })
        elif kind == "function_call":
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": item.get("call_id") or item.get("id") or _id("call_"),
                    "type": "function",
                    "function": {
                        "name": item.get("name"),
                        "arguments": item.get("arguments", ""),
                    },
                }],
            })
        elif kind == "function_call_output":
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            })
        elif kind == "reasoning":
            continue
        else:
            raise UnsupportedResponsesFeature(f"unsupported input item type: {kind}")

    out: dict = {"model": upstream_model, "messages": messages, "stream": bool(body.get("stream"))}
    structured = structured_output_format(body)
    if structured and body.get("tools"):
        raise UnsupportedResponsesFeature(
            "legacy structured-output emulation cannot be combined with client function tools"
        )
    if body.get("tools"):
        out["tools"] = [{
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "parameters": tool.get("parameters") or {},
                **({"strict": tool["strict"]} if "strict" in tool else {}),
            },
        } for tool in body["tools"]]
    if "tool_choice" in body:
        out["tool_choice"] = _chat_tool_choice(body["tool_choice"])
    if structured:
        out["tools"] = [_chat_structured_tool(structured)]
        out.pop("tool_choice", None)
        _add_chat_instruction(messages, STRUCTURED_OUTPUT_INSTRUCTION)
    for source, target in (
        ("max_output_tokens", "max_tokens"),
        ("temperature", "temperature"),
        ("top_p", "top_p"),
        ("parallel_tool_calls", "parallel_tool_calls"),
    ):
        if source in body:
            out[target] = body[source]
    if out["stream"]:
        out["stream_options"] = {"include_usage": True}
    return out


def _anthropic_content(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    result: list[dict] = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, str):
            result.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind in {"text", "input_text", "output_text"}:
            result.append({"type": "text", "text": part.get("text", "")})
        elif kind == "input_image":
            url = part.get("image_url")
            if isinstance(url, str) and url.startswith("data:") and ";base64," in url:
                header, data = url.split(",", 1)
                result.append({"type": "image", "source": {
                    "type": "base64", "media_type": header[5:].split(";", 1)[0], "data": data,
                }})
            elif isinstance(url, str) and url.startswith(("https://", "http://")):
                result.append({"type": "image", "source": {"type": "url", "url": url}})
            else:
                raise UnsupportedResponsesFeature(
                    "input_image requires an HTTP(S) or base64 data URL in compatibility mode"
                )
        else:
            raise UnsupportedResponsesFeature(f"unsupported content part type: {kind}")
    return result


def _anthropic_tool_choice(choice):
    if choice == "auto":
        return {"type": "auto"}
    if choice == "required":
        return {"type": "any"}
    if choice == "none":
        return None
    if isinstance(choice, dict) and choice.get("type") == "function":
        return {"type": "tool", "name": choice.get("name")}
    return choice


def responses_to_messages_request(body: dict, upstream_model: str) -> dict:
    """Translate the portable Responses request subset to Anthropic Messages."""
    _validate_portable(body)
    messages: list[dict] = []
    system_parts = [str(body["instructions"])] if body.get("instructions") else []

    def append(role: str, content: list[dict]) -> None:
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(content)
        else:
            messages.append({"role": role, "content": content})

    for item in _response_items(body):
        if isinstance(item, str):
            append("user", [{"type": "text", "text": item}])
            continue
        if not isinstance(item, dict):
            continue
        kind = item.get("type", "message")
        if kind == "message":
            if item.get("role") in {"system", "developer"}:
                system_parts.append(_text(item.get("content")))
                continue
            role = "assistant" if item.get("role") == "assistant" else "user"
            append(role, _anthropic_content(item.get("content")))
        elif kind == "function_call":
            try:
                tool_input = json.loads(item.get("arguments") or "{}")
            except json.JSONDecodeError:
                tool_input = {"arguments": item.get("arguments", "")}
            append("assistant", [{
                "type": "tool_use",
                "id": item.get("call_id") or item.get("id") or _id("call_"),
                "name": item.get("name"),
                "input": tool_input,
            }])
        elif kind == "function_call_output":
            append("user", [{
                "type": "tool_result",
                "tool_use_id": item.get("call_id", ""),
                "content": str(item.get("output", "")),
            }])
        elif kind == "reasoning":
            continue
        else:
            raise UnsupportedResponsesFeature(f"unsupported input item type: {kind}")

    out: dict = {
        "model": upstream_model,
        "messages": messages,
        "max_tokens": body.get("max_output_tokens") or 4096,
        "stream": bool(body.get("stream")),
    }
    if system_parts:
        out["system"] = "\n\n".join(part for part in system_parts if part)
    structured = structured_output_format(body)
    if structured and body.get("tools"):
        raise UnsupportedResponsesFeature(
            "legacy structured-output emulation cannot be combined with client function tools"
        )
    if body.get("tools") and body.get("tool_choice") != "none":
        out["tools"] = [{
            "name": tool.get("name"),
            "description": tool.get("description"),
            "input_schema": tool.get("parameters") or {},
        } for tool in body["tools"]]
    if "tool_choice" in body:
        choice = _anthropic_tool_choice(body["tool_choice"])
        if choice is not None:
            out["tool_choice"] = choice
    if structured:
        out["tools"] = [_messages_structured_tool(structured)]
        out.pop("tool_choice", None)
        out["system"] = _append_instruction(
            out.get("system"), STRUCTURED_OUTPUT_INSTRUCTION
        )
    for key in ("temperature", "top_p"):
        if key in body:
            out[key] = body[key]
    return out


def _usage(input_tokens=0, output_tokens=0, **extra) -> dict:
    return {
        "input_tokens": input_tokens or 0,
        "input_tokens_details": {"cached_tokens": extra.get("cached_tokens", 0)},
        "output_tokens": output_tokens or 0,
        "output_tokens_details": {"reasoning_tokens": extra.get("reasoning_tokens", 0)},
        "total_tokens": (input_tokens or 0) + (output_tokens or 0),
    }


def _base_response(model: str, response_id: Optional[str] = None) -> dict:
    return {
        "id": response_id or _id("resp_"),
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": None,
        "model": model,
        "output": [],
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "temperature": None,
        "text": {"format": {"type": "text"}, "verbosity": "medium"},
        "tool_choice": "auto",
        "tools": [],
        "top_p": None,
        "truncation": "disabled",
        "usage": _usage(),
        "user": None,
        "metadata": {},
    }


def _message_item(text: str, item_id: Optional[str] = None) -> dict:
    return {
        "id": item_id or _id("msg_"),
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "annotations": [], "text": text}],
    }


def chat_response_to_response(
    payload: dict, model: str, structured_tool_name: Optional[str] = None
) -> dict:
    response = _base_response(model, str(payload.get("id") or "").replace("chatcmpl-", "resp_"))
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    structured_call = next((
        call for call in message.get("tool_calls") or []
        if (call.get("function") or {}).get("name") == structured_tool_name
    ), None) if structured_tool_name else None
    if structured_call is not None:
        arguments = (structured_call.get("function") or {}).get("arguments", "{}")
        response["output"].append(_message_item(arguments))
    elif message.get("content") is not None:
        response["output"].append(_message_item(_text(message.get("content"))))
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        if structured_tool_name and fn.get("name") == structured_tool_name:
            continue
        response["output"].append({
            "id": _id("fc_"),
            "type": "function_call",
            "status": "completed",
            "call_id": call.get("id") or _id("call_"),
            "name": fn.get("name"),
            "arguments": fn.get("arguments", ""),
        })
    finish = choice.get("finish_reason")
    if finish in {"length", "content_filter"}:
        response["status"] = "incomplete"
        response["incomplete_details"] = {
            "reason": "max_output_tokens" if finish == "length" else "content_filter"
        }
    usage = payload.get("usage") or {}
    response["usage"] = _usage(
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
        cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
    )
    return response


def messages_response_to_response(
    payload: dict, model: str, structured_tool_name: Optional[str] = None
) -> dict:
    response = _base_response(model, str(payload.get("id") or "").replace("msg_", "resp_"))
    structured_block = next((
        block for block in payload.get("content") or []
        if block.get("type") == "tool_use" and block.get("name") == structured_tool_name
    ), None) if structured_tool_name else None
    if structured_block is not None:
        response["output"].append(_message_item(json.dumps(
            structured_block.get("input") or {}, separators=(",", ":")
        )))
    for block in payload.get("content") or []:
        if structured_block is not None:
            continue
        if block.get("type") == "text":
            response["output"].append(_message_item(block.get("text", "")))
        elif block.get("type") == "tool_use":
            response["output"].append({
                "id": _id("fc_"), "type": "function_call", "status": "completed",
                "call_id": block.get("id") or _id("call_"), "name": block.get("name"),
                "arguments": json.dumps(block.get("input") or {}, separators=(",", ":")),
            })
    if payload.get("stop_reason") == "max_tokens":
        response["status"] = "incomplete"
        response["incomplete_details"] = {"reason": "max_output_tokens"}
    usage = payload.get("usage") or {}
    input_tokens = usage.get("input_tokens", 0)
    cached = usage.get("cache_read_input_tokens", 0)
    response["usage"] = _usage(input_tokens, usage.get("output_tokens", 0), cached_tokens=cached)
    return response


def native_structured_response_to_text(payload: dict) -> dict:
    """Hide the private native Responses function call as structured output text."""
    call = next((
        item for item in payload.get("output") or []
        if item.get("type") == "function_call" and item.get("name") == STRUCTURED_OUTPUT_TOOL
    ), None)
    if call is None:
        return payload
    response = dict(payload)
    response["output"] = [_message_item(call.get("arguments", "{}"))]
    return response


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n".encode()


def _complete_text_events(state: "_ResponseStream", text: str) -> list[bytes]:
    """Append one completed assistant message and return its SSE lifecycle."""
    item = _message_item(text)
    state.output.append(item)
    index = len(state.output) - 1
    part = item["content"][0]
    return [
        state.event("response.output_item.added", output_index=index,
                    item={**item, "status": "in_progress"}),
        state.event("response.content_part.added", item_id=item["id"], output_index=index,
                    content_index=0, part={**part, "text": ""}),
        state.event("response.output_text.delta", item_id=item["id"], output_index=index,
                    content_index=0, delta=text, logprobs=[]),
        state.event("response.output_text.done", item_id=item["id"], output_index=index,
                    content_index=0, text=text, logprobs=[]),
        state.event("response.content_part.done", item_id=item["id"], output_index=index,
                    content_index=0, part=part),
        state.event("response.output_item.done", output_index=index, item=item),
    ]


@dataclass
class _ResponseStream:
    model: str
    response: dict = field(init=False)
    sequence: int = 0
    output: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.response = _base_response(self.model)
        self.response["status"] = "in_progress"

    def event(self, kind: str, **fields) -> bytes:
        event = {"type": kind, "sequence_number": self.sequence, **fields}
        self.sequence += 1
        return _sse(event)

    def begin(self) -> list[bytes]:
        return [
            self.event("response.created", response=dict(self.response)),
            self.event("response.in_progress", response=dict(self.response)),
        ]

    def complete(self, usage: dict, incomplete_reason: Optional[str] = None) -> bytes:
        self.response["output"] = self.output
        self.response["usage"] = usage
        self.response["status"] = "incomplete" if incomplete_reason else "completed"
        self.response["incomplete_details"] = (
            {"reason": incomplete_reason} if incomplete_reason else None
        )
        kind = "response.incomplete" if incomplete_reason else "response.completed"
        return self.event(kind, response=self.response)


async def chat_sse_to_responses_sse(
    events: AsyncIterator[dict],
    model: str,
    structured_tool_name: Optional[str] = None,
) -> AsyncIterator[bytes]:
    state = _ResponseStream(model)
    for event in state.begin():
        yield event
    text_item: Optional[dict] = None
    text = ""
    tools: dict[int, dict] = {}
    usage = _usage()
    finish_reason = None

    async for chunk in events:
        if chunk.get("__done__"):
            break
        if chunk.get("error"):
            error = chunk["error"]
            yield state.event("error", **(error if isinstance(error, dict) else {"message": str(error)}))
            return
        raw_usage = chunk.get("usage") or {}
        if raw_usage:
            usage = _usage(raw_usage.get("prompt_tokens"), raw_usage.get("completion_tokens"))
        for choice in chunk.get("choices") or []:
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            if delta.get("content") is not None:
                delta_text = str(delta.get("content") or "")
                text += delta_text
                if not structured_tool_name:
                    if text_item is None:
                        text_item = _message_item("")
                        text_item["status"] = "in_progress"
                        state.output.append(text_item)
                        idx = len(state.output) - 1
                        yield state.event("response.output_item.added", output_index=idx,
                                          item=dict(text_item))
                        yield state.event(
                            "response.content_part.added", item_id=text_item["id"],
                            output_index=idx, content_index=0,
                            part={"type": "output_text", "annotations": [], "text": ""},
                        )
                    yield state.event("response.output_text.delta", item_id=text_item["id"],
                                      output_index=state.output.index(text_item), content_index=0,
                                      delta=delta_text, logprobs=[])
            for tool_delta in delta.get("tool_calls") or []:
                index = int(tool_delta.get("index", 0))
                fn = tool_delta.get("function") or {}
                if index not in tools:
                    tools[index] = {
                        "item": {
                            "id": _id("fc_"), "type": "function_call",
                            "status": "in_progress",
                            "call_id": tool_delta.get("id") or _id("call_"),
                            "name": fn.get("name"), "arguments": "",
                        },
                        "emitted": False,
                        "forwarded": 0,
                    }
                tracked = tools[index]
                item = tracked["item"]
                item["call_id"] = tool_delta.get("id") or item["call_id"]
                item["name"] = fn.get("name") or item["name"]
                args = fn.get("arguments") or ""
                item["arguments"] += args
                is_structured = bool(
                    structured_tool_name and item["name"] == structured_tool_name
                )
                if item["name"] and not is_structured and not tracked["emitted"]:
                    tracked["emitted"] = True
                    state.output.append(item)
                    yield state.event("response.output_item.added",
                                      output_index=len(state.output) - 1, item=dict(item))
                pending = item["arguments"][tracked["forwarded"]:]
                if tracked["emitted"] and pending:
                    yield state.event("response.function_call_arguments.delta", item_id=item["id"],
                                      output_index=state.output.index(item), delta=pending)
                    tracked["forwarded"] = len(item["arguments"])

    structured_item = next((
        tracked["item"] for tracked in tools.values()
        if structured_tool_name and tracked["item"].get("name") == structured_tool_name
    ), None)
    if structured_tool_name:
        structured_text = structured_item.get("arguments", "{}") if structured_item else text
        for event in _complete_text_events(state, structured_text):
            yield event
    elif text_item is not None:
        text_item["content"][0]["text"] = text
        text_item["status"] = "completed"
        idx = state.output.index(text_item)
        yield state.event("response.output_text.done", item_id=text_item["id"], output_index=idx,
                          content_index=0, text=text, logprobs=[])
        yield state.event("response.content_part.done", item_id=text_item["id"], output_index=idx,
                          content_index=0, part=text_item["content"][0])
        yield state.event("response.output_item.done", output_index=idx, item=text_item)
    for tracked in tools.values():
        item = tracked["item"]
        if structured_tool_name and item.get("name") == structured_tool_name:
            continue
        if not tracked["emitted"]:
            tracked["emitted"] = True
            state.output.append(item)
            yield state.event("response.output_item.added", output_index=len(state.output) - 1,
                              item=dict(item))
            if item["arguments"]:
                yield state.event("response.function_call_arguments.delta", item_id=item["id"],
                                  output_index=state.output.index(item), delta=item["arguments"])
        item["status"] = "completed"
        idx = state.output.index(item)
        yield state.event("response.function_call_arguments.done", item_id=item["id"], output_index=idx,
                          arguments=item["arguments"])
        yield state.event("response.output_item.done", output_index=idx, item=item)
    reason = "max_output_tokens" if finish_reason == "length" else None
    yield state.complete(usage, reason)


async def messages_sse_to_responses_sse(
    events: AsyncIterator[dict],
    model: str,
    structured_tool_name: Optional[str] = None,
) -> AsyncIterator[bytes]:
    state = _ResponseStream(model)
    for event in state.begin():
        yield event
    blocks: dict[int, dict] = {}
    structured_blocks: set[int] = set()
    deferred_text_blocks: set[int] = set()
    input_tokens = output_tokens = cached_tokens = 0
    stop_reason = None

    async for event in events:
        if event.get("__done__"):
            break
        kind = event.get("type")
        if kind == "message_start":
            raw = (event.get("message") or {}).get("usage") or {}
            input_tokens = raw.get("input_tokens", 0)
            cached_tokens = raw.get("cache_read_input_tokens", 0)
        elif kind == "content_block_start":
            index = int(event.get("index", 0))
            block = event.get("content_block") or {}
            if block.get("type") == "text":
                item = _message_item(block.get("text", ""))
                item["status"] = "in_progress"
                blocks[index] = item
                if structured_tool_name:
                    deferred_text_blocks.add(index)
                    continue
                state.output.append(item)
                out_idx = len(state.output) - 1
                yield state.event("response.output_item.added", output_index=out_idx, item=dict(item))
                yield state.event("response.content_part.added", item_id=item["id"], output_index=out_idx,
                                  content_index=0, part={"type": "output_text", "annotations": [], "text": ""})
            elif block.get("type") == "tool_use":
                initial_input = block.get("input") or {}
                item = {
                    "id": _id("fc_"), "type": "function_call", "status": "in_progress",
                    "call_id": block.get("id") or _id("call_"), "name": block.get("name"),
                    "arguments": (
                        json.dumps(initial_input, separators=(",", ":")) if initial_input else ""
                    ),
                }
                blocks[index] = item
                if structured_tool_name and item["name"] == structured_tool_name:
                    structured_blocks.add(index)
                    continue
                state.output.append(item)
                yield state.event("response.output_item.added", output_index=len(state.output) - 1,
                                  item=dict(item))
        elif kind == "content_block_delta":
            index = int(event.get("index", 0))
            item = blocks.get(index)
            delta = event.get("delta") or {}
            if not item:
                continue
            if delta.get("type") == "text_delta":
                value = delta.get("text", "")
                item["content"][0]["text"] += value
                if index in deferred_text_blocks:
                    continue
                yield state.event("response.output_text.delta", item_id=item["id"],
                                  output_index=state.output.index(item), content_index=0,
                                  delta=value, logprobs=[])
            elif delta.get("type") == "input_json_delta":
                value = delta.get("partial_json", "")
                item["arguments"] += value
                if index in structured_blocks:
                    continue
                yield state.event("response.function_call_arguments.delta", item_id=item["id"],
                                  output_index=state.output.index(item), delta=value)
        elif kind == "content_block_stop":
            item = blocks.get(int(event.get("index", 0)))
            if not item:
                continue
            block_index = int(event.get("index", 0))
            if block_index in structured_blocks or block_index in deferred_text_blocks:
                continue
            item["status"] = "completed"
            idx = state.output.index(item)
            if item["type"] == "message":
                value = item["content"][0]["text"]
                yield state.event("response.output_text.done", item_id=item["id"], output_index=idx,
                                  content_index=0, text=value, logprobs=[])
                yield state.event("response.content_part.done", item_id=item["id"], output_index=idx,
                                  content_index=0, part=item["content"][0])
            else:
                yield state.event("response.function_call_arguments.done", item_id=item["id"],
                                  output_index=idx, arguments=item["arguments"])
            yield state.event("response.output_item.done", output_index=idx, item=item)
        elif kind == "message_delta":
            stop_reason = (event.get("delta") or {}).get("stop_reason") or stop_reason
            raw = event.get("usage") or {}
            output_tokens = raw.get("output_tokens", output_tokens)
        elif kind == "error":
            error = event.get("error") or event
            yield state.event("error", **error)
            return

    if structured_tool_name:
        structured_text = next((
            blocks[index].get("arguments", "{}") for index in structured_blocks
        ), None)
        if structured_text is None:
            structured_text = "".join(
                blocks[index]["content"][0]["text"] for index in sorted(deferred_text_blocks)
            )
        for event in _complete_text_events(state, structured_text):
            yield event
    usage = _usage(input_tokens, output_tokens, cached_tokens=cached_tokens)
    reason = "max_output_tokens" if stop_reason == "max_tokens" else None
    yield state.complete(usage, reason)


async def native_structured_sse_to_responses_sse(
    events: AsyncIterator[dict], model: str
) -> AsyncIterator[bytes]:
    """Convert a private native Responses function stream into output text."""
    state = _ResponseStream(model)
    for event in state.begin():
        yield event
    arguments = ""
    fallback_text: list[str] = []
    usage = _usage()
    incomplete_reason = None

    async for event in events:
        if event.get("__done__"):
            break
        kind = event.get("type")
        if kind == "response.function_call_arguments.delta":
            arguments += event.get("delta", "")
        elif kind == "response.output_item.done":
            item = event.get("item") or {}
            if item.get("type") == "function_call" and item.get("name") == STRUCTURED_OUTPUT_TOOL:
                arguments = item.get("arguments", arguments)
        elif kind == "response.output_text.delta":
            fallback_text.append(event.get("delta", ""))
        elif kind in {"response.completed", "response.incomplete", "response.failed"}:
            final = event.get("response") or {}
            usage = final.get("usage") or usage
            incomplete_reason = (final.get("incomplete_details") or {}).get("reason")
            for item in final.get("output") or []:
                if item.get("type") == "function_call" and item.get("name") == STRUCTURED_OUTPUT_TOOL:
                    arguments = item.get("arguments", arguments)
        elif kind == "error":
            error = event.get("error") or event
            yield state.event("error", **error)
            return

    text = arguments or "".join(fallback_text)
    for event in _complete_text_events(state, text):
        yield event
    yield state.complete(usage, incomplete_reason)


class ResponsesUpstreamProtocol(str, Enum):
    """Upstream inference protocols understood by the compatibility layer."""

    NATIVE = "responses"
    CHAT_COMPLETIONS = "chat_completions"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    TEXT_GENERATION = "text_generation"


@dataclass(frozen=True)
class PreparedResponsesRequest:
    """Translated request plus the state needed to translate its response."""

    body: dict
    structured_tool_name: Optional[str] = None

    @property
    def uses_structured_output_emulation(self) -> bool:
        return self.structured_tool_name is not None


class ResponsesProtocolAdapter(ABC):
    """Strategy interface for exposing Responses over an upstream protocol."""

    protocol: ResponsesUpstreamProtocol
    native = False

    @abstractmethod
    def prepare_request(
        self, body: dict, upstream_model: str
    ) -> PreparedResponsesRequest:
        """Translate a gateway Responses request into the upstream request."""

    @abstractmethod
    def translate_response(
        self, payload: dict, gateway_model: str, prepared: PreparedResponsesRequest
    ) -> dict:
        """Translate one non-streaming upstream response into Responses format."""

    @abstractmethod
    async def translate_stream(
        self,
        events: AsyncIterator[dict],
        gateway_model: str,
        prepared: PreparedResponsesRequest,
    ) -> AsyncIterator[bytes]:
        """Translate parsed upstream events into typed Responses SSE events."""

    def requires_response_translation(self, prepared: PreparedResponsesRequest) -> bool:
        return not self.native or prepared.uses_structured_output_emulation


class NativeResponsesAdapter(ResponsesProtocolAdapter):
    """Native Responses strategy with structured-output fallback when required."""

    protocol = ResponsesUpstreamProtocol.NATIVE
    native = True

    def prepare_request(
        self, body: dict, upstream_model: str
    ) -> PreparedResponsesRequest:
        structured = structured_output_format(body)
        translated = responses_to_native_structured_request(body) if structured else dict(body)
        return PreparedResponsesRequest(
            translated, STRUCTURED_OUTPUT_TOOL if structured else None
        )

    def translate_response(
        self, payload: dict, gateway_model: str, prepared: PreparedResponsesRequest
    ) -> dict:
        if prepared.uses_structured_output_emulation:
            return native_structured_response_to_text(payload)
        return payload

    async def translate_stream(
        self,
        events: AsyncIterator[dict],
        gateway_model: str,
        prepared: PreparedResponsesRequest,
    ) -> AsyncIterator[bytes]:
        if not prepared.uses_structured_output_emulation:
            raise RuntimeError("native Responses streams should be passed through directly")
        async for event in native_structured_sse_to_responses_sse(events, gateway_model):
            yield event


class ChatCompletionsResponsesAdapter(ResponsesProtocolAdapter):
    """Responses strategy backed by OpenAI-compatible Chat Completions."""

    protocol = ResponsesUpstreamProtocol.CHAT_COMPLETIONS

    def prepare_request(
        self, body: dict, upstream_model: str
    ) -> PreparedResponsesRequest:
        structured = structured_output_format(body)
        return PreparedResponsesRequest(
            responses_to_chat_request(body, upstream_model),
            STRUCTURED_OUTPUT_TOOL if structured else None,
        )

    def translate_response(
        self, payload: dict, gateway_model: str, prepared: PreparedResponsesRequest
    ) -> dict:
        return chat_response_to_response(
            payload, gateway_model, prepared.structured_tool_name
        )

    async def translate_stream(
        self,
        events: AsyncIterator[dict],
        gateway_model: str,
        prepared: PreparedResponsesRequest,
    ) -> AsyncIterator[bytes]:
        async for event in chat_sse_to_responses_sse(
            events, gateway_model, prepared.structured_tool_name
        ):
            yield event


class AnthropicMessagesResponsesAdapter(ResponsesProtocolAdapter):
    """Responses strategy backed by Anthropic-compatible Messages."""

    protocol = ResponsesUpstreamProtocol.ANTHROPIC_MESSAGES

    def prepare_request(
        self, body: dict, upstream_model: str
    ) -> PreparedResponsesRequest:
        structured = structured_output_format(body)
        return PreparedResponsesRequest(
            responses_to_messages_request(body, upstream_model),
            STRUCTURED_OUTPUT_TOOL if structured else None,
        )

    def translate_response(
        self, payload: dict, gateway_model: str, prepared: PreparedResponsesRequest
    ) -> dict:
        return messages_response_to_response(
            payload, gateway_model, prepared.structured_tool_name
        )

    async def translate_stream(
        self,
        events: AsyncIterator[dict],
        gateway_model: str,
        prepared: PreparedResponsesRequest,
    ) -> AsyncIterator[bytes]:
        async for event in messages_sse_to_responses_sse(
            events, gateway_model, prepared.structured_tool_name
        ):
            yield event


class TextGenerationResponsesAdapter(ResponsesProtocolAdapter):
    """Limited Responses strategy for plain-text CLI or generation backends."""

    protocol = ResponsesUpstreamProtocol.TEXT_GENERATION

    def prepare_request(
        self, body: dict, upstream_model: str
    ) -> PreparedResponsesRequest:
        _validate_portable(body)
        if body.get("tools"):
            raise UnsupportedResponsesFeature(
                "plain-text backends cannot emulate function tools"
            )
        if structured_output_format(body):
            raise UnsupportedResponsesFeature(
                "plain-text backends cannot enforce structured output"
            )
        for item in _response_items(body):
            if not isinstance(item, dict):
                continue
            kind = item.get("type", "message")
            if kind == "reasoning":
                continue
            if kind != "message":
                raise UnsupportedResponsesFeature(
                    f"plain-text backends cannot emulate input item type: {kind}"
                )
            content = item.get("content")
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") not in {
                    "text", "input_text", "output_text",
                }:
                    raise UnsupportedResponsesFeature(
                        f"plain-text backends cannot emulate content part: {part.get('type')}"
                    )
        return PreparedResponsesRequest(dict(body))

    def translate_response(
        self, payload: dict, gateway_model: str, prepared: PreparedResponsesRequest
    ) -> dict:
        response = _base_response(gateway_model)
        response["output"] = [_message_item(str(payload.get("result") or ""))]
        raw_usage = payload.get("usage") or {}
        response["usage"] = _usage(
            raw_usage.get("input_tokens"), raw_usage.get("output_tokens")
        )
        return response

    async def translate_stream(
        self,
        events: AsyncIterator[dict],
        gateway_model: str,
        prepared: PreparedResponsesRequest,
    ) -> AsyncIterator[bytes]:
        async def chat_events() -> AsyncIterator[dict]:
            async for event in events:
                if event.get("type") == "error":
                    yield {"error": event.get("error") or event}
                    return
                if event.get("type") == "text_delta":
                    yield {"choices": [{"delta": {"content": event.get("delta", "")}}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
            yield {"__done__": True}

        async for event in chat_sse_to_responses_sse(chat_events(), gateway_model):
            yield event


class ResponsesAdapterFactory:
    """Registry-backed factory for protocol strategies.

    New transports can be added without changing the route orchestration: add
    an adapter implementation and register it here (or at application startup).
    """

    _registry: dict[ResponsesUpstreamProtocol, ResponsesProtocolAdapter] = {
        adapter.protocol: adapter
        for adapter in (
            NativeResponsesAdapter(),
            ChatCompletionsResponsesAdapter(),
            AnthropicMessagesResponsesAdapter(),
            TextGenerationResponsesAdapter(),
        )
    }

    @classmethod
    def register(cls, adapter: ResponsesProtocolAdapter) -> None:
        cls._registry[adapter.protocol] = adapter

    @classmethod
    def create(
        cls, protocol: ResponsesUpstreamProtocol | str
    ) -> ResponsesProtocolAdapter:
        try:
            key = ResponsesUpstreamProtocol(protocol)
            return cls._registry[key]
        except (KeyError, ValueError) as exc:
            raise UnsupportedResponsesFeature(
                f"no Responses adapter is registered for upstream protocol: {protocol}"
            ) from exc
