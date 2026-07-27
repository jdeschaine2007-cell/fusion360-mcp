"""
Smoke test for the FastMCP add-in (fusion_mcp_server.py).

Runs headless with a stubbed `adsk` so we verify, for real, that:
  - the MCP server module imports and registers its tools,
  - a geometry tool (create_box) drives the real adsk call chain
    (sketch -> rectangle -> extrude) WITHOUT a live Fusion,
  - plan_design returns a plan + preview PNG using the shared preview renderer.

This is how we prove the Joe-Spencer -> jaskirat1616 merge is wired,
not just that it looks right.
"""
import os
import sys
import json
import importlib
import pytest

pytest.importorskip("mcp")  # this test needs the MCP SDK (separate venv)

# Inject the adsk stub package (tests/stubs/adsk) onto the path so the
# server's `import adsk.core` resolves to the stub instead of real Fusion.
_STUB_DIR = os.path.join(os.path.dirname(__file__), "stubs")
if _STUB_DIR not in sys.path:
    sys.path.insert(0, _STUB_DIR)
importlib.import_module("adsk")  # ensures adsk + adsk.core/fusion load

ADDIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fusion_addin"))
if ADDIN_DIR not in sys.path:
    sys.path.insert(0, ADDIN_DIR)
# make mcp_server.preview importable for the plan tool
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)


@pytest.fixture(scope="module")
def server():
    import fusion_addin.fusion_mcp_server as srv
    # Provide a fake LLM for plan_design.
    def fake_llm(prompt, system):
        return json.dumps({"actions": [
            {"action": "create_box",
             "params": {"width": 20, "height": 20, "depth": 20, "unit": "mm"},
             "explanation": "cube"},
        ]})
    srv.set_llm_callable(fake_llm)
    return srv


def test_module_registers_geometry_tool(server):
    # The FastMCP instance exposes a tool named create_box.
    tool_names = list(server.mcp._tool_manager._tools.keys())  # type: ignore[attr]
    assert "create_box" in tool_names
    assert "plan_design" in tool_names
    assert "execute_design" in tool_names


def test_create_box_drives_real_adsk_chain(server):
    # The MCP tool wrapper should execute the geometry function end-to-end
    # (sketch -> rectangle -> extrude) and return a human summary.
    result = server.create_box(width=20, height=20, depth=20, unit="mm")
    assert isinstance(result, str) and "created" in result.lower()

    # Drive the geometry path directly to assert the real adsk call chain +
    # unit conversion (20mm -> 2.0cm in Fusion's internal unit).
    import adsk
    from fusion_addin import fusion_geometry as geo
    app = adsk.core.Application.get()
    geo.create_box(app, {"width": 20, "height": 20, "depth": 20, "unit": "mm"})
    last = adsk.fusion.ExtrudeFeatures.last
    assert last is not None, "extrude was never called"
    assert last[0] == "extrude"
    assert abs(last[2] - 2.0) < 1e-6  # 20mm == 2.0cm


def test_plan_design_returns_plan_and_preview(server):
    out = server.plan_design(prompt="a 20mm cube", units="mm")
    assert out["status"] == "planned"
    assert out["actions"], "expected a proposed action"
    assert out["plan_text"].strip()
    assert out["preview_png"].startswith("data:image/png;base64,")


# --------------------------------------------------------------------------- #
# Vectorworks backend (dual-CAD) — verified headless with the vs.py stub
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def vw_server():
    # Force the Vectorworks backend; stub `vs` must already be on sys.path.
    import fusion_addin.fusion_mcp_server as srv
    srv._ACTIVE = None  # reset in case the fusion fixture ran first
    srv.set_backend("vectorworks")

    def fake_llm(prompt, system):
        return json.dumps({"actions": [
            {"action": "create_box",
             "params": {"width": 100, "height": 50, "depth": 5, "unit": "mm"},
             "explanation": "base"},
        ]})
    srv.set_llm_callable(fake_llm)
    return srv


def test_vectorworks_create_box_drives_vs(vw_server):
    import vs  # top-level stub (same module the backend imports)
    vs.CALLS.clear()
    result = vw_server.create_box(width=100, height=50, depth=5, unit="mm")
    assert isinstance(result, str) and "created" in result.lower()
    names = [c[0] for c in vs.CALLS]
    assert "CreateExtrude" in names, "Vectorworks extrude was never called"
    assert "MoveTo" in names and "LineTo" in names  # rectangle path built


def test_vectorworks_plan_design_uses_same_preview(vw_server):
    out = vw_server.plan_design(prompt="a 100x50 base plate", units="mm")
    assert out["status"] == "planned"
    assert out["actions"]
    assert out["preview_png"].startswith("data:image/png;base64,")
    # The backend resource should report vectorworks now.
    assert vw_server.backend_info()["backend"] == "vectorworks"
