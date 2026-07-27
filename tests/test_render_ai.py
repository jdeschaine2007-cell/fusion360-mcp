"""Tests for the AI-render module (prompt composition + graceful degradation).

The actual diffusion render is exercised by _ai_mock_item.py when a local
ComfyUI server is up; these tests cover what must ALWAYS work.
"""
import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from mcp_server.render_ai import compose_prompt, comfy_alive, ai_render  # noqa: E402

ACTS = [
    {"action": "create_box", "params": {"width": 120, "height": 80, "depth": 8, "unit": "mm"},
     "explanation": "base plate"},
    {"action": "create_cylinder", "params": {"diameter": 30, "height": 25, "unit": "mm"},
     "explanation": "motor boss"},
    {"action": "create_hole", "params": {"diameter": 6.5, "position": {"x": 15, "y": 15}, "unit": "mm"},
     "explanation": "M6 clearance"},
]


def test_compose_prompt_contains_all_specs():
    p = compose_prompt(ACTS, "NEMA 17 motor mount", material="aluminum")
    assert "120x80x8mm" in p
    assert "diameter 30mm" in p and "height 25mm" in p
    assert "diameter 6.5mm" in p
    assert "NEMA 17 motor mount" in p
    assert "aluminum" in p


def test_compose_prompt_material_variants():
    assert "PETG" in compose_prompt(ACTS, "x", material="plastic")
    assert "steel" in compose_prompt(ACTS, "x", material="steel")
    # unknown material passes through verbatim
    assert "titanium" in compose_prompt(ACTS, "x", material="titanium")


def test_ai_render_degrades_gracefully_without_comfyui(monkeypatch):
    # Point at a dead port — must return None, never raise.
    monkeypatch.setenv("COMFY_HOST", "http://127.0.0.1:59999")
    import importlib
    import mcp_server.render_ai as ra
    importlib.reload(ra)
    assert ra.comfy_alive() is False
    assert ra.ai_render(ACTS, "x", out_path="/tmp/should_not_exist.png") is None
