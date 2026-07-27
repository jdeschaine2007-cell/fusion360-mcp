"""
Pytest conftest for FusionMCP's beta suite.

The dual-CAD beta lives in:
    test_fusion_mcp_addin.py   (headless adsk + vs stubs; both backends)
    test_e2e_mcp_server.py    (REAL MCP SSE protocol, both backends)
    test_ollama_autowire.py    (zero-config Ollama LLM wiring)

The OTHER test_*.py files in this dir (test_mcp_server, test_plan_action,
test_config_loader, test_context_cache, test_ollama_client) belong to the
ORIGINAL jaskirat1616/fusion360-mcp suite and require extra deps
(loguru, anthropic, openai, fastapi TestClient) that are NOT part of the
beta environment. They are intentionally NOT collected here so `pytest tests/`
and the CI workflow stay green on the beta subset. Run them separately in
the upstream venv if you maintain that suite.
"""
collect_ignore = [
    "test_mcp_server.py",
    "test_plan_action.py",
    "test_config_loader.py",
    "test_context_cache.py",
    "test_ollama_client.py",
]
