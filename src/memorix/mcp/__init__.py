"""Minimal MCP (Model Context Protocol) stdio server for memorix (M4).

Zero runtime dependencies: JSON-RPC 2.0, newline-delimited, stdio transport.
"""
from .server import PROTOCOL_VERSIONS, Server, main, serve

__all__ = ["PROTOCOL_VERSIONS", "Server", "main", "serve"]
