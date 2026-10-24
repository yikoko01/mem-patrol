"""M4 MCP stdio server: handshake, tools/list, tools/call, errors, serve loop."""
from __future__ import annotations

import io
import json

import pytest

from memorix import __version__
from memorix.mcp.server import LATEST_PROTOCOL, PROTOCOL_VERSIONS, Server, serve
from memorix.mcp.tools import TOOL_DEFS, call_tool

OWNER = "404BE32F7C9E448DB63AC9E0658A10EB"


def request(method, params=None, request_id=1):
    payload = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    return payload


def test_version():
    assert __version__ == "0.3.4"


def test_initialize_latest_and_legacy():
    server = Server()
    result = server.handle(request("initialize", {"protocolVersion": LATEST_PROTOCOL}))["result"]
    assert result["protocolVersion"] == LATEST_PROTOCOL
    assert result["serverInfo"] == {"name": "memorix", "version": __version__}
    assert result["capabilities"]["tools"] == {"listChanged": False}
    legacy = server.handle(request("initialize", {"protocolVersion": "2024-11-05"}))["result"]
    assert legacy["protocolVersion"] == "2024-11-05"
    unknown = server.handle(request("initialize", {"protocolVersion": "1999-01-01"}))["result"]
    assert unknown["protocolVersion"] == LATEST_PROTOCOL


def test_tools_list():
    result = Server().handle(request("tools/list"))["result"]
    names = {tool["name"] for tool in result["tools"]}
    assert names == {
        "memorix_diagnose",
        "memorix_orphan",
        "memorix_recall",
        "memorix_gate_check",
        "memorix_judge_replay",
        "memorix_eval",
    }
    assert len(result["tools"]) == 6
    for tool in result["tools"]:
        assert tool["inputSchema"]["type"] == "object"


def test_tools_call_diagnose(patrol_db, state_file, write_state):
    write_state()
    response = Server().handle(
        request(
            "tools/call",
            {"name": "memorix_diagnose", "arguments": {"db": str(patrol_db), "state": str(state_file)}},
        )
    )
    content = response["result"]["content"][0]["text"]
    assert response["result"]["isError"] is False
    assert "MEMORIX_DIAGNOSIS" in content and "total=8" in content


def test_tools_call_recall(make_patrol_db):
    db = make_patrol_db(
        memories=[(1, "auto_patrol", 8, 1_800_000_000_000, "石头门项目=破解打包，最困难阶段是盲改期", "g", "u")],
        raw=[],
        bot=[],
    )
    text = call_tool("memorix_recall", {"db": str(db), "query": "石头门最困难阶段"})
    assert "石头门" in text and "破解" in text


def test_tools_call_orphan_and_gate():
    assert "ORPHAN_SKIP" in call_tool("memorix_orphan", {"db": "/nonexistent.db", "state": "/nonexistent.json"})
    gate = call_tool("memorix_gate_check", {"text": "这个怎么弄？"})
    assert "ACTION=dropped" in gate and "未开启" in gate
    gate = call_tool(
        "memorix_gate_check",
        {"text": "这个怎么弄？", "config": {"enable_group_interjection": True, "group_interject_max_daily": 10}},
    )
    assert "ACTION=candidate" in gate


def test_tools_call_judge_replay_and_eval():
    assert "JUDGE_REPLAY 9/9" in call_tool("memorix_judge_replay", {})
    assert "EVAL 9/9" in call_tool("memorix_eval", {"suite": "policy"})


def test_unknown_tool_and_invalid_params():
    response = Server().handle(request("tools/call", {"name": "nope", "arguments": {}}))
    assert response["result"]["isError"] is True and "unknown tool" in response["result"]["content"][0]["text"]
    response = Server().handle(request("tools/call", {"name": "memorix_diagnose"}))
    assert response["result"]["isError"] is True


def test_protocol_errors():
    assert Server().handle_line("{bad json")["error"]["code"] == -32700
    assert Server().handle({"jsonrpc": "2.0", "id": 1, "method": "nope"})["error"]["code"] == -32601
    assert Server().handle({"jsonrpc": "2.0", "id": 2})["error"]["code"] == -32600
    assert Server().handle([1, 2])["error"]["code"] == -32600
    assert Server().handle(request("notifications/initialized", request_id=None)) is None


def test_ping_and_notification_no_response():
    assert Server().handle(request("ping"))["result"] == {}
    assert Server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_serve_loop_and_default_db(make_patrol_db):
    db = make_patrol_db(
        memories=[(1, "auto_patrol", 8, 1_800_000_000_000, "石头门项目=破解打包", "g", "u")],
        raw=[],
        bot=[],
    )
    stdin = io.StringIO(
        json.dumps(request("initialize", {"protocolVersion": LATEST_PROTOCOL})) + "\n"
        + json.dumps(request("tools/call", {"name": "memorix_recall", "arguments": {"query": "石头门"}})) + "\n"
    )
    stdout = io.StringIO()
    assert serve(stdin, stdout, Server(default_db=str(db))) == 0
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert len(lines) == 2
    assert lines[1]["result"]["isError"] is False
    assert "石头门" in lines[1]["result"]["content"][0]["text"]


def test_tool_defs_have_descriptions():
    assert all(tool.get("description") for tool in TOOL_DEFS)


def test_recall_clamps_schema_bounds(make_patrol_db):
    db = make_patrol_db(
        memories=[(1, "auto_patrol", 8, 1_800_000_000_000, "石头门项目=破解打包", "g", "u")],
        raw=[],
        bot=[],
    )
    text = call_tool(
        "memorix_recall",
        {"db": str(db), "query": "石头门", "top_k": 999, "max_chars": 99999},
    )
    assert "石头门" in text


def test_profile_filters_tools(make_patrol_db):
    chat = Server(profile="chat")
    chat_tools = chat.handle(request("tools/list"))["result"]["tools"]
    assert [tool["name"] for tool in chat_tools] == [
        "memorix_recall",
        "memorix_gate_check",
        "memorix_judge_replay",
    ]
    project = Server(profile="project")
    project_tools = project.handle(request("tools/list"))["result"]["tools"]
    assert [tool["name"] for tool in project_tools] == [
        "memorix_diagnose",
        "memorix_orphan",
        "memorix_recall",
        "memorix_eval",
    ]
    assert len(Server(profile="both").handle(request("tools/list"))["result"]["tools"]) == 6
    with pytest.raises(ValueError):
        Server(profile="nope")


def test_profile_rejects_disallowed_tool(make_patrol_db):
    db = make_patrol_db(
        memories=[(1, "auto_patrol", 8, 1_800_000_000_000, "石头门项目=破解打包", "g", "u")],
        raw=[],
        bot=[],
    )
    chat = Server(profile="chat")
    denied = chat.handle(
        request(
            "tools/call",
            {"name": "memorix_diagnose", "arguments": {"db": str(db)}},
        )
    )
    assert denied["result"]["isError"] is True
    assert "not enabled" in denied["result"]["content"][0]["text"]
    allowed = chat.handle(
        request("tools/call", {"name": "memorix_recall", "arguments": {"db": str(db), "query": "石头门"}})
    )
    assert allowed["result"]["isError"] is False
    assert "石头门" in allowed["result"]["content"][0]["text"]
