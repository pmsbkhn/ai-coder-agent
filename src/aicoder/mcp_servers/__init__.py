"""MCP servers (infrastructure executables) and their pure logic libs.

These run as separate processes behind the MCP Gateway (JSON-RPC over stdio).
They may import tree-sitter / mcp freely and deliberately do NOT depend on the
agent's domain/application layers — they only exchange JSON.
"""
