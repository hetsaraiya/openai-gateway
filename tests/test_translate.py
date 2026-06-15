import json

from app.translate import (
    aggregate_response,
    chat_to_responses,
    iter_sse,
    responses_sse_to_chat_sse,
    responses_to_chat,
)
from tests.conftest import sse_bytes


def test_chat_to_responses_basic():
    chat = {
        "model": "gpt-5.1-codex",
        "messages": [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hello"},
        ],
        "max_tokens": 100,
        "temperature": 0.5,
    }
    out = chat_to_responses(chat, "default")
    assert out["model"] == "gpt-5.1-codex"
    assert out["instructions"] == "be terse"
    assert out["stream"] is True and out["store"] is False
    assert out["max_output_tokens"] == 100
    assert out["temperature"] == 0.5
    assert out["input"] == [
        {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "hello"}]},
    ]


def test_chat_to_responses_default_model():
    out = chat_to_responses({"messages": []}, "fallback-model")
    assert out["model"] == "fallback-model"


def test_chat_to_responses_always_sets_instructions():
    # No system/developer message -> falls back to the default (backend requires it).
    out = chat_to_responses({"messages": [{"role": "user", "content": "hi"}]}, "m",
                            default_instructions="DEFAULT")
    assert out["instructions"] == "DEFAULT"


def test_chat_to_responses_honors_explicit_instructions():
    out = chat_to_responses(
        {"instructions": "be a pirate", "messages": [{"role": "user", "content": "hi"}]}, "m")
    assert out["instructions"] == "be a pirate"


def test_chat_to_responses_tool_calls_roundtrip():
    chat = {"messages": [
        {"role": "user", "content": "weather?"},
        {"role": "assistant", "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "get_weather", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
    ]}
    out = chat_to_responses(chat, "m")
    types = [i["type"] for i in out["input"]]
    assert types == ["message", "function_call", "function_call_output"]
    assert out["input"][1]["call_id"] == "call_1"
    assert out["input"][2]["output"] == "sunny"


def test_responses_to_chat_text():
    resp = {
        "id": "resp_1", "model": "gpt-5.1-codex", "status": "completed",
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": "hi there"}]}],
        "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
    }
    chat = responses_to_chat(resp, "gpt-5.1-codex")
    assert chat["object"] == "chat.completion"
    choice = chat["choices"][0]
    assert choice["message"]["content"] == "hi there"
    assert choice["finish_reason"] == "stop"
    assert chat["usage"] == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}


def test_responses_to_chat_tool_calls():
    resp = {"status": "completed", "output": [
        {"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{\"x\":1}"}]}
    chat = responses_to_chat(resp, "m")
    choice = chat["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "f"


def test_responses_to_chat_length_finish():
    resp = {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "x"}]}]}
    assert responses_to_chat(resp, "m")["choices"][0]["finish_reason"] == "length"


async def _aiter(data: bytes):
    # Feed in two pieces to exercise the SSE buffer across chunk boundaries.
    mid = len(data) // 2
    yield data[:mid]
    yield data[mid:]


async def test_streaming_translation_to_chat_chunks():
    upstream = sse_bytes([
        {"type": "response.output_text.delta", "delta": "Hel"},
        {"type": "response.output_text.delta", "delta": "lo"},
        {"type": "response.completed", "response": {
            "id": "r", "model": "m", "status": "completed", "output": [],
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}}},
    ])
    events = iter_sse(_aiter(upstream))
    chunks = []
    async for raw in responses_sse_to_chat_sse(events, "m", "chatcmpl-x"):
        chunks.append(raw)

    assert chunks[-1] == b"data: [DONE]\n\n"
    parsed = [json.loads(c[len(b"data: "):]) for c in chunks[:-1]]
    # First content chunk carries the assistant role.
    assert parsed[0]["choices"][0]["delta"]["role"] == "assistant"
    text = "".join(p["choices"][0]["delta"].get("content", "") for p in parsed)
    assert text == "Hello"
    # Final chunk carries finish_reason + usage.
    assert parsed[-1]["choices"][0]["finish_reason"] == "stop"
    assert parsed[-1]["usage"]["completion_tokens"] == 2


async def test_aggregate_recovers_text_from_deltas_when_completed_lacks_it():
    # Reasoning-model shape: text only arrives via deltas; completed output has
    # just a reasoning item (no message). Aggregation should still recover text.
    upstream = sse_bytes([
        {"type": "response.output_text.delta", "delta": "Hel"},
        {"type": "response.output_text.delta", "delta": "lo!"},
        {"type": "response.completed", "response": {
            "id": "r", "model": "gpt-5.4-mini", "status": "completed",
            "output": [{"type": "reasoning", "summary": []}],
            "usage": {"input_tokens": 28, "output_tokens": 19, "total_tokens": 47}}},
    ])
    final = await aggregate_response(iter_sse(_aiter(upstream)))
    chat = responses_to_chat(final, "gpt-5.4-mini")
    assert chat["choices"][0]["message"]["content"] == "Hello!"
    assert chat["choices"][0]["finish_reason"] == "stop"


async def test_aggregate_keeps_message_text_when_present():
    # When the completed object already carries the message, don't double up.
    upstream = sse_bytes([
        {"type": "response.output_text.delta", "delta": "Hi"},
        {"type": "response.completed", "response": {
            "id": "r", "status": "completed",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "Hi"}]}]}},
    ])
    final = await aggregate_response(iter_sse(_aiter(upstream)))
    assert responses_to_chat(final, "m")["choices"][0]["message"]["content"] == "Hi"


# The Codex backend streams function calls via output_item events and leaves the
# final response.completed output array EMPTY. These use the real captured shapes.

async def test_aggregate_assembles_function_call_from_stream_items():
    upstream = sse_bytes([
        {"type": "response.output_item.added", "item": {
            "id": "fc_1", "type": "function_call", "arguments": "",
            "call_id": "call_abc", "name": "get_weather"}},
        {"type": "response.function_call_arguments.delta", "delta": "{\"city\":", "item_id": "fc_1"},
        {"type": "response.function_call_arguments.done",
         "arguments": "{\"city\":\"Paris\"}", "item_id": "fc_1"},
        {"type": "response.output_item.done", "item": {
            "id": "fc_1", "type": "function_call", "status": "completed",
            "arguments": "{\"city\":\"Paris\"}", "call_id": "call_abc", "name": "get_weather"}},
        {"type": "response.completed", "response": {
            "id": "r", "model": "gpt-5.5", "status": "completed", "output": [],
            "usage": {"input_tokens": 151, "output_tokens": 18, "total_tokens": 169}}},
    ])
    final = await aggregate_response(iter_sse(_aiter(upstream)))
    choice = responses_to_chat(final, "gpt-5.5")["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    tc = choice["message"]["tool_calls"][0]
    assert tc["id"] == "call_abc"
    assert tc["function"]["name"] == "get_weather"
    assert tc["function"]["arguments"] == '{"city":"Paris"}'


async def test_streaming_emits_tool_call_chunks():
    upstream = sse_bytes([
        {"type": "response.output_item.added", "item": {
            "id": "fc_1", "type": "function_call", "call_id": "call_abc", "name": "get_weather"}},
        {"type": "response.function_call_arguments.delta", "delta": "{\"city\":", "item_id": "fc_1"},
        {"type": "response.function_call_arguments.delta", "delta": "\"Paris\"}", "item_id": "fc_1"},
        {"type": "response.output_item.done", "item": {
            "id": "fc_1", "type": "function_call", "call_id": "call_abc",
            "name": "get_weather", "arguments": "{\"city\":\"Paris\"}"}},
        {"type": "response.completed", "response": {
            "status": "completed", "output": [],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}},
    ])
    chunks = []
    async for raw in responses_sse_to_chat_sse(iter_sse(_aiter(upstream)), "gpt-5.5", "chatcmpl-x"):
        chunks.append(raw)
    assert chunks[-1] == b"data: [DONE]\n\n"
    parsed = [json.loads(c[len(b"data: "):]) for c in chunks[:-1]]
    opener = next(p for p in parsed if p["choices"][0]["delta"].get("tool_calls"))
    tc = opener["choices"][0]["delta"]["tool_calls"][0]
    assert tc["id"] == "call_abc" and tc["function"]["name"] == "get_weather"
    args = "".join(
        t.get("function", {}).get("arguments", "")
        for p in parsed for t in p["choices"][0]["delta"].get("tool_calls", []))
    assert args == '{"city":"Paris"}'
    assert parsed[-1]["choices"][0]["finish_reason"] == "tool_calls"
