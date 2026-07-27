"""
End-to-end test of the plan_action flow WITHOUT a live LLM.

We inject a stub client into MCPRouter so _handle_plan_action runs for real
(generates plan + preview PNG) and asserts nothing is executed and the
preview payload is returned.
"""
import asyncio

import pytest

from mcp_server.router import MCPRouter
from mcp_server.schema import (
    DesignContext,
    LLMResponse,
    LLMResponseMetadata,
    MCPCommand,
    ModelParams,
)
from mcp_server.utils import Config


class _StubClient:
    """Returns a canned multi-action plan; records whether it was called."""
    def __init__(self):
        self.called = False

    async def generate(self, model, prompt, system_prompt, temperature, max_tokens):
        self.called = True
        json_obj = {
            "actions": [
                {"action": "create_box",
                 "params": {"width": 20, "height": 20, "depth": 20, "unit": "mm"},
                 "explanation": "cube"},
            ]
        }
        import json as _json
        return {
            "provider": "ollama",
            "model": model,
            "output": _json.dumps(json_obj),
            "json": json_obj,
            "tokens_used": 10,
        }


def _router():
    cfg = Config()
    cfg.ollama_url = "http://localhost:11434"
    r = MCPRouter(cfg)
    r.clients["ollama"] = _StubClient()
    return r


def test_plan_action_returns_preview_and_no_execute():
    r = _router()
    cmd = MCPCommand(
        command="plan_action",
        params=ModelParams(provider="ollama", model="llama3", prompt="Make a 20mm cube"),
        context=DesignContext(units="mm", design_state="empty"),
    )
    resp = asyncio.run(r._handle_plan_action(cmd, "system"))

    assert resp.status == "planned"
    assert resp.actions_to_execute, "expected at least one proposed action"
    assert resp.actions_to_execute[0].action == "create_box"
    # Preview payload must be attached and contain a PNG + plan text.
    md = resp.metadata_dict
    assert md["preview_png"].startswith("data:image/png;base64,")
    assert "1." in md["plan_text"]
    # The stub proves the LLM was queried (but Fusion was NOT — no geometry built).
    assert r.clients["ollama"].called is True
