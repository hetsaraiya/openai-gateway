"""Translation between OpenAI Chat Completions and the Responses API.

The ChatGPT Codex backend only speaks the Responses API and only streams
(SSE). This module converts:

  * a Chat Completions request  -> a Responses request   (``chat_to_responses``)
  * Responses SSE events        -> Chat Completions chunks (``responses_sse_to_chat_sse``)
  * a final Responses object    -> a Chat Completion       (``responses_to_chat``)

plus helpers to parse SSE and aggregate a non-streaming result.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator, Optional


class UpstreamError(Exception):
    def __init__(self, payload):
        super().__init__(str(payload)[:500])
        self.payload = payload


def new_chat_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex[:24]


# The Codex backend requires a non-empty ``instructions`` field. When a Chat
# Completions request carries no system/developer message (and no explicit
# ``instructions``), we fall back to this.
DEFAULT_INSTRUCTIONS = "You are a helpful assistant."


# --------------------------------------------------------------------------- #
# Request:  Chat Completions  ->  Responses
# --------------------------------------------------------------------------- #

def _flatten_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    out = []
    for it in content:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict) and "text" in it:
            out.append(it.get("text") or "")
    return "".join(out)


def _content_parts(content, kind: str) -> list[dict]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": kind, "text": content}]
    parts = []
    for it in content:
        if isinstance(it, str):
            parts.append({"type": kind, "text": it})
        elif isinstance(it, dict):
            t = it.get("type")
            if t in ("text", "input_text", "output_text"):
                parts.append({"type": kind, "text": it.get("text", "")})
            elif t == "image_url":
                url = (it.get("image_url") or {}).get("url")
                if url:
                    parts.append({"type": "input_image", "image_url": url})
    return parts


def _message_item(role: str, content) -> dict:
    kind = "output_text" if role == "assistant" else "input_text"
    return {"type": "message", "role": role, "content": _content_parts(content, kind)}


def _tools_to_responses(tools) -> list[dict]:
    out = []
    for t in tools or []:
        if isinstance(t, dict) and t.get("type") == "function":
            fn = t.get("function", {})
            out.append({
                "type": "function",
                "name": fn.get("name"),
                "description": fn.get("description"),
                "parameters": fn.get("parameters"),
            })
        else:
            out.append(t)
    return out


def chat_to_responses(
    chat: dict, default_model: str, default_instructions: str = DEFAULT_INSTRUCTIONS
) -> dict:
    instructions: list[str] = []
    input_items: list[dict] = []

    # Honor an explicit top-level `instructions` (non-standard for Chat
    # Completions, but the Responses API uses it and clients may pass it).
    explicit = chat.get("instructions")
    if isinstance(explicit, str) and explicit.strip():
        instructions.append(explicit)

    for m in chat.get("messages", []):
        role = m.get("role")
        content = m.get("content")

        if role in ("system", "developer"):
            instructions.append(_flatten_text(content))
        elif role == "tool":
            input_items.append({
                "type": "function_call_output",
                "call_id": m.get("tool_call_id", ""),
                "output": _flatten_text(content),
            })
        elif role == "assistant" and m.get("tool_calls"):
            if content:
                input_items.append(_message_item(role, content))
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                input_items.append({
                    "type": "function_call",
                    "call_id": tc.get("id", ""),
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments", ""),
                })
        else:
            input_items.append(_message_item(role, content))

    body: dict = {
        "model": chat.get("model") or default_model,
        "input": input_items,
        "stream": True,   # the Codex backend always streams; we adapt downstream
        "store": False,
    }
    # instructions is required by the backend — always send something non-empty.
    body["instructions"] = "\n\n".join(p for p in instructions if p) or default_instructions
    if "temperature" in chat:
        body["temperature"] = chat["temperature"]
    if "top_p" in chat:
        body["top_p"] = chat["top_p"]
    max_out = chat.get("max_completion_tokens") or chat.get("max_tokens")
    if max_out:
        body["max_output_tokens"] = max_out
    if chat.get("tools"):
        body["tools"] = _tools_to_responses(chat["tools"])
    if "tool_choice" in chat:
        body["tool_choice"] = chat["tool_choice"]
    if chat.get("reasoning_effort"):
        body["reasoning"] = {"effort": chat["reasoning_effort"]}
    if chat.get("metadata"):
        body["metadata"] = chat["metadata"]
    return body


# --------------------------------------------------------------------------- #
# SSE parsing
# --------------------------------------------------------------------------- #

def _extract_data(block: bytes) -> Optional[dict]:
    datas = [ln[5:].lstrip() for ln in block.split(b"\n") if ln.startswith(b"data:")]
    if not datas:
        return None
    raw = b"".join(datas).strip()
    if raw == b"[DONE]":
        return {"__done__": True}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


async def iter_sse(byte_iter: AsyncIterator[bytes]) -> AsyncIterator[dict]:
    """Yield parsed ``data:`` payloads from an SSE byte stream."""
    buffer = b""
    async for chunk in byte_iter:
        buffer += chunk
        while b"\n\n" in buffer:
            block, buffer = buffer.split(b"\n\n", 1)
            data = _extract_data(block)
            if data is not None:
                yield data
    if buffer.strip():
        data = _extract_data(buffer)
        if data is not None:
            yield data


# --------------------------------------------------------------------------- #
# Response:  Responses  ->  Chat Completions
# --------------------------------------------------------------------------- #

def _usage(usage: Optional[dict]) -> dict:
    usage = usage or {}
    prompt = usage.get("input_tokens", 0)
    completion = usage.get("output_tokens", 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": usage.get("total_tokens", prompt + completion),
    }


def _finish_reason(resp: dict, has_tools: bool) -> str:
    if has_tools:
        return "tool_calls"
    if resp.get("status") == "incomplete":
        reason = (resp.get("incomplete_details") or {}).get("reason")
        if reason == "max_output_tokens":
            return "length"
    return "stop"


def _extract_tool_calls(resp: dict) -> list[dict]:
    calls = []
    for item in resp.get("output", []):
        if item.get("type") == "function_call":
            calls.append({
                "id": item.get("call_id") or item.get("id"),
                "type": "function",
                "function": {
                    "name": item.get("name"),
                    "arguments": item.get("arguments", ""),
                },
            })
    return calls


def _extract_text(resp: dict) -> str:
    parts = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    parts.append(c.get("text", ""))
    return "".join(parts)


def responses_to_chat(resp: dict, model: str, chat_id: Optional[str] = None) -> dict:
    tool_calls = _extract_tool_calls(resp)
    message: dict = {"role": "assistant", "content": _extract_text(resp) or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": chat_id or resp.get("id") or new_chat_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": resp.get("model") or model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": _finish_reason(resp, bool(tool_calls)),
        }],
        "usage": _usage(resp.get("usage")),
    }


def _chunk(chat_id, created, model, delta, finish, usage=None) -> bytes:
    obj = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage is not None:
        obj["usage"] = usage
    return f"data: {json.dumps(obj)}\n\n".encode()


async def responses_sse_to_chat_sse(
    events: AsyncIterator[dict], model: str, chat_id: str
) -> AsyncIterator[bytes]:
    """Adapt Responses SSE events into Chat Completions chunk SSE.

    Function calls are streamed by the backend as ``output_item.added`` (the
    call's id/name) followed by ``function_call_arguments.delta`` events; we map
    those to OpenAI ``tool_calls`` deltas. Text comes via ``output_text.delta``.
    """
    created = int(time.time())
    sent_role = False
    saw_tool = False
    tool_index: dict[str, int] = {}   # backend item_id -> chat tool_calls index

    def _role_prefix() -> dict:
        nonlocal sent_role
        d: dict = {} if sent_role else {"role": "assistant"}
        sent_role = True
        return d

    async for data in events:
        if data.get("__done__"):
            break
        etype = data.get("type")

        if etype == "response.output_text.delta":
            delta = _role_prefix()
            delta["content"] = data.get("delta", "")
            yield _chunk(chat_id, created, model, delta, None)

        elif etype == "response.output_item.added":
            item = data.get("item", {})
            if item.get("type") == "function_call":
                idx = len(tool_index)
                tool_index[item.get("id")] = idx
                saw_tool = True
                delta = _role_prefix()
                delta["tool_calls"] = [{
                    "index": idx, "id": item.get("call_id"), "type": "function",
                    "function": {"name": item.get("name"), "arguments": ""},
                }]
                yield _chunk(chat_id, created, model, delta, None)

        elif etype == "response.function_call_arguments.delta":
            idx = tool_index.get(data.get("item_id"))
            if idx is not None:
                yield _chunk(chat_id, created, model, {"tool_calls": [{
                    "index": idx, "function": {"arguments": data.get("delta", "")},
                }]}, None)

        elif etype == "error":
            raise UpstreamError(data)

        elif etype in ("response.completed", "response.failed", "response.incomplete"):
            resp = data.get("response", {})
            yield _chunk(
                chat_id, created, model, {},
                _finish_reason(resp, saw_tool), _usage(resp.get("usage")),
            )

    yield b"data: [DONE]\n\n"


async def aggregate_response(events: AsyncIterator[dict]) -> dict:
    """Consume Responses SSE and return the final ``response`` object.

    The Codex backend delivers output (text *and* function calls) via streaming
    events and leaves the ``output`` array in the final ``response.completed``
    event **empty**. So we assemble ``output`` ourselves from the per-item
    ``response.output_item.done`` events (each carries the complete item — a
    function_call with its call_id/name/arguments, or a message), falling back to
    accumulated ``output_text`` deltas for plain text.
    """
    final: Optional[dict] = None
    done_items: list[dict] = []
    text_parts: list[str] = []
    async for data in events:
        if data.get("__done__"):
            break
        etype = data.get("type")
        if etype == "response.output_item.done":
            item = data.get("item")
            if isinstance(item, dict):
                done_items.append(item)
        elif etype == "response.output_text.delta":
            text_parts.append(data.get("delta", ""))
        elif etype in ("response.completed", "response.failed", "response.incomplete"):
            final = data.get("response", final)
        elif etype == "error":
            raise UpstreamError(data)
    if final is None:
        raise UpstreamError("upstream stream ended without a final response")

    # The completed object often has no usable output (empty, or reasoning-only),
    # because messages and function calls were delivered via streaming events.
    # Backfill from the streamed items / text deltas when that's the case.
    if not _has_usable_output(final):
        if done_items:
            final["output"] = done_items
        elif text_parts:
            final["output"] = [{
                "type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "".join(text_parts)}],
            }]
    return final


def _has_usable_output(resp: dict) -> bool:
    for item in resp.get("output", []):
        if item.get("type") == "function_call":
            return True
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text") and c.get("text"):
                    return True
    return False
