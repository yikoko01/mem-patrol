"""Minimal MCP stdio server (JSON-RPC 2.0, newline-delimited).

Implements the handshake, ``tools/list``, ``tools/call`` and ``ping``. No SDK and
no runtime dependencies; the transport is intentionally simple so it can be
embedded in any Python process or run as ``memorix-mcp``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, TextIO

from .. import __version__
from ..profiles import PROFILES, get_profile, tools_for
from .tools import TOOL_DEFS, ToolError, call_tool

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL = PROTOCOL_VERSIONS[0]


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class Server:
    """Protocol handler; transport-agnostic for tests and embedding."""

    def __init__(
        self,
        *,
        default_db: str | None = None,
        version: str = __version__,
        profile: str = "both",
    ) -> None:
        if profile not in PROFILES:
            raise ValueError("unknown profile %r (choose chat/project/both)" % profile)
        self.default_db = default_db
        self.version = version
        self.profile = profile
        self._allowed_tools = frozenset(tools_for(profile))

    # ── dispatch ─────────────────────────────────────────────────────
    def handle_line(self, line: str) -> dict | None:
        line = line.strip()
        if not line:
            return None
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            return _error(None, -32700, "parse error: %s" % exc)
        return self.handle(request)

    def handle(self, request: Any) -> dict | None:
        if not isinstance(request, dict):
            return _error(None, -32600, "invalid request")
        request_id = request.get("id")
        method = request.get("method")
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return _error(request_id, -32600, "invalid request")
        if method.startswith("notifications/"):
            return None  # notifications never get a response
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        try:
            if method == "initialize":
                return self._result(request_id, self._initialize(params))
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                tools = [tool for tool in TOOL_DEFS if tool["name"] in self._allowed_tools]
                return self._result(request_id, {"tools": tools})
            if method == "tools/call":
                return self._result(request_id, self._tools_call(params))
            return _error(request_id, -32601, "method not found: %s" % method)
        except Exception as exc:  # noqa: BLE001 - protocol must never crash
            return _error(request_id, -32603, "internal error: %s" % exc)

    def _initialize(self, params: dict) -> dict:
        requested = str(params.get("protocolVersion") or "")
        negotiated = requested if requested in PROTOCOL_VERSIONS else LATEST_PROTOCOL
        return {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "memorix", "version": self.version},
            "instructions": (
                "Read-only memory-patrol, recall and gatekeep tools. "
                "No tool writes to a database; use the CLI with --apply for repairs."
            ),
        }

    def _tools_call(self, params: dict) -> dict:
        name = str(params.get("name") or "")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict) or not name:
            return {
                "content": [{"type": "text", "text": "invalid tools/call params"}],
                "isError": True,
            }
        known_tools = {tool["name"] for tool in TOOL_DEFS}
        if name not in known_tools:
            return {
                "content": [{"type": "text", "text": "unknown tool: %s" % name}],
                "isError": True,
            }
        if name not in self._allowed_tools:
            return {
                "content": [{"type": "text", "text": "tool %r is not enabled by profile %r" % (name, self.profile)}],
                "isError": True,
            }
        try:
            text = call_tool(name, arguments, default_db=self.default_db)
        except ToolError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except Exception as exc:  # noqa: BLE001 - tool failure becomes a tool error
            return {"content": [{"type": "text", "text": "%s: %s" % (type(exc).__name__, exc)}], "isError": True}
        return {"content": [{"type": "text", "text": text}], "isError": False}

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(stdin: TextIO, stdout: TextIO, server: Server) -> int:
    """Run the newline-delimited JSON-RPC loop until EOF."""
    for line in stdin:
        response = server.handle_line(line)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memorix-mcp", description="memorix MCP stdio server")
    parser.add_argument("--db", help="default patrol database for tools that take db")
    parser.add_argument("--profile", default="both", choices=["chat", "project", "both"], help="tool allow-list preset")
    parser.add_argument("--version", action="version", version="memorix-mcp " + __version__)
    args = parser.parse_args(argv)
    return serve(
        sys.stdin,
        sys.stdout,
        Server(default_db=args.db or os.environ.get("MEMORIX_DB"), profile=args.profile),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
