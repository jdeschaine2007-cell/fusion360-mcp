"""
Tests for MCP Server
"""

import pytest
import urllib.request
from fastapi.testclient import TestClient
from mcp_server.server import app
from mcp_server.schema import MCPCommand, ModelParams


def _ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1):
            return True
    except Exception:
        return False


@pytest.fixture
def client():
    """Test client fixture. Use as a context manager so the FastAPI
    lifespan (which builds the MCP router) actually runs."""
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "providers" in data


@pytest.mark.skipif(not _ollama_reachable(), reason="requires a running Ollama at :11434")
def test_mcp_command_ask_model(client):
    """Test ask_model command (needs a live Ollama)."""
    command = {
        "command": "ask_model",
        "params": {
            "provider": "ollama",
            "model": "llama3",
            "prompt": "Create a 20mm cube",
            "temperature": 0.7
        },
        "context": {
            "active_component": "RootComponent",
            "units": "mm",
            "design_state": "empty"
        }
    }

    response = client.post("/mcp/command", json=command)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["success", "error", "clarification_needed"]


def _live_keys_configured() -> bool:
    """True if any cloud LLM key is present (live API call would be made)."""
    import os
    return any(os.getenv(k) for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "CLAUDE_API_KEY"))


@pytest.mark.skipif(_live_keys_configured(),
                    reason="lists live provider APIs; skip when keys are configured")
def test_list_models(client):
    """Test list models endpoint"""
    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data


def test_history_endpoint(client):
    """Test history endpoint"""
    response = client.get("/history?limit=5")
    # May return 503 if cache not enabled
    assert response.status_code in [200, 503]


def test_invalid_command(client):
    """An unknown command value is rejected by the schema (422), not 200."""
    command = {
        "command": "invalid_command",
        "params": None
    }

    response = client.post("/mcp/command", json=command)
    assert response.status_code == 422
