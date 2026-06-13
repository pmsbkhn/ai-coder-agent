"""Adapter layer — concrete implementations of the outbound ports.

Populated from M1 onward:
    mcp_gateway.py   MCPGatewayClient (MCP JSON-RPC)         — M1
    maven_build.py   MavenBuildTool (BuildToolPort)          — M1
    memory_pg.py     PostgresMemory (MemoryPort, append-only)— M1
    planner_llm.py   ClaudePlanner (PlannerPort)             — M2

Code here MAY import SDKs (mcp, anthropic, psycopg). The domain/application
layers may NOT — that is the whole point of this layer.
"""
