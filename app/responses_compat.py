"""Compatibility adapters for serving Responses API over legacy model APIs.

OpenCode Go exposes some models through OpenAI Chat Completions and others
through Anthropic Messages.  This module implements the common, portable
subset of the Responses API on top of those two protocols.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


class UnsupportedResponsesFeature(ValueError):
    """A Responses feature cannot be represented by the selected upstream."""


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
            f"OpenCode Go compatibility mode cannot emulate: {names}"
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
    for source, target in (
        ("max_output_tokens", "max_tokens"),
        ("temperature", "temperature"),
        ("top_p", "top_p"),
        ("parallel_tool_calls", "parallel_tool_calls"),
    ):
        if source in body:
            out[target] = body[source]
    text = body.get("text") or {}
    if isinstance(text, dict) and text.get("format"):
        fmt = text["format"]
        if fmt.get("type") == "json_schema":
            out["response_format"] = {
                "type": "json_schema",
                "json_schema": {k: v for k, v in fmt.items() if k != "type"},
            }
        elif fmt.get("type") == "json_object":
            out["response_format"] = {"type": "json_object"}
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


def chat_response_to_response(payload: dict, model: str) -> dict:
    response = _base_response(model, str(payload.get("id") or "").replace("chatcmpl-", "resp_"))
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    if message.get("content") is not None:
        response["output"].append(_message_item(_text(message.get("content"))))
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
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


def messages_response_to_response(payload: dict, model: str) -> dict:
    response = _base_response(model, str(payload.get("id") or "").replace("msg_", "resp_"))
    for block in payload.get("content") or []:
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


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n".encode()


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


async def chat_sse_to_responses_sse(events: AsyncIterator[dict], model: str) -> AsyncIterator[bytes]:
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
                if text_item is None:
                    text_item = _message_item("")
                    text_item["status"] = "in_progress"
                    state.output.append(text_item)
                    idx = len(state.output) - 1
                    yield state.event("response.output_item.added", output_index=idx, item=dict(text_item))
                    yield state.event("response.content_part.added", item_id=text_item["id"], output_index=idx,
                                      content_index=0, part={"type": "output_text", "annotations": [], "text": ""})
                delta_text = str(delta.get("content") or "")
                text += delta_text
                yield state.event("response.output_text.delta", item_id=text_item["id"],
                                  output_index=state.output.index(text_item), content_index=0,
                                  delta=delta_text, logprobs=[])
            for tool_delta in delta.get("tool_calls") or []:
                index = int(tool_delta.get("index", 0))
                fn = tool_delta.get("function") or {}
                if index not in tools:
                    item = {
                        "id": _id("fc_"), "type": "function_call", "status": "in_progress",
                        "call_id": tool_delta.get("id") or _id("call_"),
                        "name": fn.get("name"), "arguments": "",
                    }
                    tools[index] = item
                    state.output.append(item)
                    yield state.event("response.output_item.added", output_index=len(state.output) - 1,
                                      item=dict(item))
                item = tools[index]
                item["call_id"] = tool_delta.get("id") or item["call_id"]
                item["name"] = fn.get("name") or item["name"]
                args = fn.get("arguments") or ""
                item["arguments"] += args
                if args:
                    yield state.event("response.function_call_arguments.delta", item_id=item["id"],
                                      output_index=state.output.index(item), delta=args)

    if text_item is not None:
        text_item["content"][0]["text"] = text
        text_item["status"] = "completed"
        idx = state.output.index(text_item)
        yield state.event("response.output_text.done", item_id=text_item["id"], output_index=idx,
                          content_index=0, text=text, logprobs=[])
        yield state.event("response.content_part.done", item_id=text_item["id"], output_index=idx,
                          content_index=0, part=text_item["content"][0])
        yield state.event("response.output_item.done", output_index=idx, item=text_item)
    for item in tools.values():
        item["status"] = "completed"
        idx = state.output.index(item)
        yield state.event("response.function_call_arguments.done", item_id=item["id"], output_index=idx,
                          arguments=item["arguments"])
        yield state.event("response.output_item.done", output_index=idx, item=item)
    reason = "max_output_tokens" if finish_reason == "length" else None
    yield state.complete(usage, reason)


async def messages_sse_to_responses_sse(events: AsyncIterator[dict], model: str) -> AsyncIterator[bytes]:
    state = _ResponseStream(model)
    for event in state.begin():
        yield event
    blocks: dict[int, dict] = {}
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
                state.output.append(item)
                out_idx = len(state.output) - 1
                yield state.event("response.output_item.added", output_index=out_idx, item=dict(item))
                yield state.event("response.content_part.added", item_id=item["id"], output_index=out_idx,
                                  content_index=0, part={"type": "output_text", "annotations": [], "text": ""})
            elif block.get("type") == "tool_use":
                item = {
                    "id": _id("fc_"), "type": "function_call", "status": "in_progress",
                    "call_id": block.get("id") or _id("call_"), "name": block.get("name"),
                    "arguments": "",
                }
                blocks[index] = item
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
                yield state.event("response.output_text.delta", item_id=item["id"],
                                  output_index=state.output.index(item), content_index=0,
                                  delta=value, logprobs=[])
            elif delta.get("type") == "input_json_delta":
                value = delta.get("partial_json", "")
                item["arguments"] += value
                yield state.event("response.function_call_arguments.delta", item_id=item["id"],
                                  output_index=state.output.index(item), delta=value)
        elif kind == "content_block_stop":
            item = blocks.get(int(event.get("index", 0)))
            if not item:
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

    usage = _usage(input_tokens, output_tokens, cached_tokens=cached_tokens)
    reason = "max_output_tokens" if stop_reason == "max_tokens" else None
    yield state.complete(usage, reason)
