import json

import pytest

from app.responses_compat import (
    STRUCTURED_OUTPUT_TOOL,
    UnsupportedResponsesFeature,
    chat_response_to_response,
    chat_sse_to_responses_sse,
    messages_response_to_response,
    messages_sse_to_responses_sse,
    native_structured_response_to_text,
    native_structured_sse_to_responses_sse,
    responses_to_chat_request,
    responses_to_messages_request,
    responses_to_native_structured_request,
)


async def _aiter(items):
    for item in items:
        yield item


def _event(raw: bytes) -> dict:
    return json.loads(raw.removeprefix(b"data: ").strip())


def test_responses_request_to_chat_preserves_tools_and_history():
    body = {
        "model": "opencode-go/glm-5.2",
        "instructions": "Be concise.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Weather?"}]},
            {"type": "function_call", "call_id": "call_1", "name": "weather",
             "arguments": '{"city":"Pune"}'},
            {"type": "function_call_output", "call_id": "call_1", "output": "Sunny"},
        ],
        "tools": [{"type": "function", "name": "weather", "description": "Get weather",
                   "parameters": {"type": "object"}, "strict": True}],
        "tool_choice": {"type": "function", "name": "weather"},
        "max_output_tokens": 200,
    }

    out = responses_to_chat_request(body, "glm-5.2")

    assert out["model"] == "glm-5.2"
    assert out["messages"][0] == {"role": "system", "content": "Be concise."}
    assert out["messages"][2]["tool_calls"][0]["id"] == "call_1"
    assert out["messages"][3]["tool_call_id"] == "call_1"
    assert out["tools"][0]["function"]["strict"] is True
    assert out["tool_choice"]["function"]["name"] == "weather"
    assert out["max_tokens"] == 200


def test_responses_request_to_messages_preserves_tool_round_trip():
    body = {
        "instructions": "Use tools.",
        "input": [
            {"role": "user", "content": "Weather?"},
            {"type": "function_call", "call_id": "call_1", "name": "weather",
             "arguments": '{"city":"Pune"}'},
            {"type": "function_call_output", "call_id": "call_1", "output": "Sunny"},
        ],
        "tools": [{"type": "function", "name": "weather", "parameters": {"type": "object"}}],
        "max_output_tokens": 100,
    }

    out = responses_to_messages_request(body, "qwen3.8-max")

    assert out["system"] == "Use tools."
    assert out["messages"][1]["content"][0]["type"] == "tool_use"
    assert out["messages"][2]["content"][0]["tool_use_id"] == "call_1"
    assert out["tools"][0]["input_schema"] == {"type": "object"}
    assert out["max_tokens"] == 100


def test_chat_structured_output_uses_forced_function_instead_of_response_format():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    out = responses_to_chat_request({
        "input": "Extract the name",
        "text": {"format": {
            "type": "json_schema", "name": "profile", "schema": schema, "strict": True,
        }},
    }, "glm-5.2")

    assert "response_format" not in out
    assert out["tools"] == [{
        "type": "function",
        "function": {
            "name": STRUCTURED_OUTPUT_TOOL,
            "description": "Return the final answer as an object matching the supplied schema.",
            "parameters": schema,
        },
    }]
    assert out["tool_choice"]["function"]["name"] == STRUCTURED_OUTPUT_TOOL


def test_messages_structured_output_uses_forced_tool():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    out = responses_to_messages_request({
        "input": "Extract the name",
        "text": {"format": {"type": "json_schema", "name": "profile", "schema": schema}},
    }, "qwen3.8-max")

    assert out["tools"][0]["name"] == STRUCTURED_OUTPUT_TOOL
    assert out["tools"][0]["input_schema"] == schema
    assert out["tool_choice"] == {"type": "tool", "name": STRUCTURED_OUTPUT_TOOL}


def test_native_responses_structured_output_uses_forced_function():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    out = responses_to_native_structured_request({
        "model": "opencode-go/gpt-5.6-luna",
        "input": "Extract the name",
        "text": {"verbosity": "low", "format": {
            "type": "json_schema", "name": "profile", "schema": schema,
        }},
    })

    assert out["text"] == {"verbosity": "low"}
    assert out["tools"][0]["name"] == STRUCTURED_OUTPUT_TOOL
    assert out["tools"][0]["parameters"] == schema
    assert out["tool_choice"] == {"type": "function", "name": STRUCTURED_OUTPUT_TOOL}


def test_rejects_stateful_and_hosted_tool_features():
    with pytest.raises(UnsupportedResponsesFeature, match="previous_response_id"):
        responses_to_chat_request({"previous_response_id": "resp_old"}, "glm-5.2")
    with pytest.raises(UnsupportedResponsesFeature, match="web_search_preview"):
        responses_to_chat_request({"tools": [{"type": "web_search_preview"}]}, "glm-5.2")
    with pytest.raises(UnsupportedResponsesFeature, match="cannot be combined"):
        responses_to_chat_request({
            "tools": [{"type": "function", "name": "lookup", "parameters": {}}],
            "text": {"format": {
                "type": "json_schema", "name": "answer", "schema": {"type": "object"},
            }},
        }, "glm-5.2")


def test_chat_response_to_responses_maps_text_tool_calls_and_usage():
    out = chat_response_to_response({
        "id": "chatcmpl_1",
        "choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": "Checking", "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "weather", "arguments": '{"city":"Pune"}'},
            }],
        }}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }, "opencode-go/glm-5.2")

    assert out["object"] == "response"
    assert out["output"][0]["content"][0]["text"] == "Checking"
    assert out["output"][1]["type"] == "function_call"
    assert out["output"][1]["call_id"] == "call_1"
    assert out["usage"]["total_tokens"] == 14


def test_chat_structured_function_becomes_output_text():
    out = chat_response_to_response({
        "id": "chatcmpl_1",
        "choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": STRUCTURED_OUTPUT_TOOL, "arguments": '{"name":"Ada"}'},
            }],
        }}],
    }, "opencode-go/glm-5.2", STRUCTURED_OUTPUT_TOOL)

    assert len(out["output"]) == 1
    assert out["output"][0]["type"] == "message"
    assert out["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


def test_messages_response_to_responses_maps_blocks():
    out = messages_response_to_response({
        "id": "msg_1", "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": "Checking"},
            {"type": "tool_use", "id": "toolu_1", "name": "weather",
             "input": {"city": "Pune"}},
        ],
        "usage": {"input_tokens": 8, "output_tokens": 3},
    }, "opencode-go/qwen3.8-max")

    assert [item["type"] for item in out["output"]] == ["message", "function_call"]
    assert out["output"][1]["arguments"] == '{"city":"Pune"}'
    assert out["usage"]["total_tokens"] == 11


def test_messages_structured_tool_becomes_output_text():
    out = messages_response_to_response({
        "id": "msg_1", "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "Here is the result"},
            {"type": "tool_use", "id": "toolu_1", "name": STRUCTURED_OUTPUT_TOOL,
             "input": {"name": "Ada"}},
        ],
        "usage": {"input_tokens": 8, "output_tokens": 3},
    }, "opencode-go/qwen3.8-max", STRUCTURED_OUTPUT_TOOL)

    assert len(out["output"]) == 1
    assert out["output"][0]["type"] == "message"
    assert out["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


def test_native_responses_structured_function_becomes_output_text():
    out = native_structured_response_to_text({
        "id": "resp_1", "object": "response", "status": "completed",
        "model": "gpt-5.6-luna",
        "output": [{
            "id": "fc_1", "type": "function_call", "name": STRUCTURED_OUTPUT_TOOL,
            "call_id": "call_1", "arguments": '{"name":"Ada"}', "status": "completed",
        }],
        "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
    })

    assert out["id"] == "resp_1"
    assert out["output"][0]["type"] == "message"
    assert out["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


@pytest.mark.asyncio
async def test_chat_stream_emits_responses_lifecycle_and_text():
    chunks = [
        {"choices": [{"delta": {"role": "assistant", "content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 1}},
        {"__done__": True},
    ]
    events = [_event(raw) async for raw in chat_sse_to_responses_sse(
        _aiter(chunks), "opencode-go/glm-5.2"
    )]

    assert events[0]["type"] == "response.created"
    assert [e["delta"] for e in events if e["type"] == "response.output_text.delta"] == ["Hel", "lo"]
    assert events[-1]["type"] == "response.completed"
    assert events[-1]["response"]["output"][0]["content"][0]["text"] == "Hello"
    assert events[-1]["response"]["usage"]["total_tokens"] == 3


@pytest.mark.asyncio
async def test_messages_stream_emits_function_call_events():
    chunks = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
        {"type": "content_block_start", "index": 0, "content_block": {
            "type": "tool_use", "id": "toolu_1", "name": "weather", "input": {},
        }},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "input_json_delta", "partial_json": '{"city":"Pune"}'}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
         "usage": {"output_tokens": 4}},
        {"type": "message_stop"},
    ]
    events = [_event(raw) async for raw in messages_sse_to_responses_sse(
        _aiter(chunks), "opencode-go/qwen3.8-max"
    )]

    deltas = [e for e in events if e["type"] == "response.function_call_arguments.delta"]
    assert deltas[0]["delta"] == '{"city":"Pune"}'
    assert events[-1]["response"]["output"][0]["call_id"] == "toolu_1"
    assert events[-1]["response"]["usage"]["total_tokens"] == 9


@pytest.mark.asyncio
async def test_chat_structured_stream_becomes_output_text_events():
    chunks = [
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_1", "type": "function",
            "function": {"name": STRUCTURED_OUTPUT_TOOL, "arguments": '{"name":'},
        }]}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": '"Ada"}'},
        }]}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 1}},
        {"__done__": True},
    ]
    events = [_event(raw) async for raw in chat_sse_to_responses_sse(
        _aiter(chunks), "opencode-go/glm-5.2", STRUCTURED_OUTPUT_TOOL
    )]

    assert not any(e["type"].startswith("response.function_call") for e in events)
    assert events[-1]["response"]["output"][0]["type"] == "message"
    assert events[-1]["response"]["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


@pytest.mark.asyncio
async def test_messages_structured_stream_becomes_output_text_events():
    chunks = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
        {"type": "content_block_start", "index": 0, "content_block": {
            "type": "tool_use", "id": "toolu_1", "name": STRUCTURED_OUTPUT_TOOL,
            "input": {},
        }},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "input_json_delta", "partial_json": '{"name":"Ada"}'}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
         "usage": {"output_tokens": 4}},
        {"type": "message_stop"},
    ]
    events = [_event(raw) async for raw in messages_sse_to_responses_sse(
        _aiter(chunks), "opencode-go/qwen3.8-max", STRUCTURED_OUTPUT_TOOL
    )]

    assert not any(e["type"].startswith("response.function_call") for e in events)
    assert events[-1]["response"]["output"][0]["type"] == "message"
    assert events[-1]["response"]["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


@pytest.mark.asyncio
async def test_native_responses_structured_stream_becomes_output_text_events():
    chunks = [
        {"type": "response.function_call_arguments.delta", "delta": '{"name":'},
        {"type": "response.function_call_arguments.delta", "delta": '"Ada"}'},
        {"type": "response.output_item.done", "item": {
            "type": "function_call", "name": STRUCTURED_OUTPUT_TOOL,
            "arguments": '{"name":"Ada"}',
        }},
        {"type": "response.completed", "response": {
            "status": "completed", "usage": {
                "input_tokens": 2, "output_tokens": 1, "total_tokens": 3,
            },
        }},
    ]
    events = [_event(raw) async for raw in native_structured_sse_to_responses_sse(
        _aiter(chunks), "opencode-go/gpt-5.6-luna"
    )]

    assert not any(e["type"].startswith("response.function_call") for e in events)
    assert events[-1]["response"]["output"][0]["type"] == "message"
    assert events[-1]["response"]["output"][0]["content"][0]["text"] == '{"name":"Ada"}'
    assert events[-1]["response"]["usage"]["total_tokens"] == 3
