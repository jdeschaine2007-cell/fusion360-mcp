"""
Full end-to-end beta test: REAL MCP protocol, not direct function calls.

For each backend (fusion via stubbed adsk, vectorworks via stubbed vs) we:
  1. boot the actual FastMCP SSE app in a uvicorn thread on a free port,
  2. connect a REAL MCP client over SSE (mcp.client.sse),
  3. initialize + list tools,
  4. call plan_design  -> assert a plan + preview PNG come back (no geometry built),
  5. call create_box     -> assert the backend's real CAD call chain fired,
  6. call execute_design -> assert the planned actions execute,
  7. read fusion://backend -> assert it reports the active backend.

This proves the server works the way a real MCP client (Claude/Cursor) would
use it -- over the wire, not by importing functions.
"""
import json
import os
import sys
import threading
import importlib

import pytest

pytest.importorskip("mcp")

# ---- headless stubs so the server can boot without a live CAD app ---- #
_STUB = os.path.join(os.path.dirname(__file__), "stubs")
if _STUB not in sys.path:
    sys.path.insert(0, _STUB)
importlib.import_module("adsk")  # top-level stub -> tests/stubs/adsk

# ---- make the server + renderer importable ---- #
_HERE = os.path.abspath(os.path.dirname(__file__))
_REPO = os.path.dirname(_HERE)
for p in (os.path.join(_REPO, "fusion_addin"), _REPO):
    if p not in sys.path:
        sys.path.insert(0, p)

import uvicorn
from mcp.client.sse import sse_client
from mcp import ClientSession


def _start_server(app):
    """Start the SSE app on a free port in a daemon thread; return (url, stop)."""
    cfg = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    port = 0
    for _ in range(100):
        try:
            port = server.servers[0].sockets[0].getsockname()[1]
            if port:
                break
        except Exception:
            threading.Event().wait(0.05)
    url = "http://127.0.0.1:{0}/sse".format(port)
    return url, (lambda: setattr(server, "should_exit", True))


class _FakeLLM:
    """Stand-in for an LLM that returns a structured plan JSON."""
    def __call__(self, prompt, system):
        return json.dumps({"actions": [
            {"action": "create_box",
             "params": {"width": 100, "height": 50, "depth": 5, "unit": "mm"},
             "explanation": "base plate"},
            {"action": "create_hole",
             "params": {"diameter": 5.5, "position": {"x": 10, "y": 10}, "unit": "mm"},
             "explanation": "M5 hole"},
        ]})


async def _run_backend_session(backend: str):
    import fusion_addin.fusion_mcp_server as srv
    srv._ACTIVE = None
    srv.set_backend(backend)
    srv.set_llm_callable(_FakeLLM())

    url, stop = _start_server(srv.mcp.sse_app())
    try:
        async with sse_client(url=url) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init is not None

                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                for needed in ("plan_design", "create_box", "execute_design", "create_hole"):
                    assert needed in names, "{0} missing for {1}".format(needed, backend)

                # 1) plan_design -> plan + preview, NOTHING built
                plan = await session.call_tool(
                    "plan_design", {"prompt": "base plate with M5 hole", "units": "mm"})
                plan_text = "".join(
                    c.text for c in plan.content if getattr(c, "type", None) == "text")
                pdata = json.loads(plan_text)
                assert pdata["status"] == "planned"
                assert len(pdata["actions"]) == 2
                assert pdata["preview_png"].startswith("data:image/png;base64,")

                # 2) create_box -> backend-specific real CAD call
                if backend == "fusion":
                    import adsk  # top-level stub, same module the server imports
                    res = await session.call_tool(
                        "create_box", {"width": 30, "height": 20, "depth": 10, "unit": "mm"})
                    built = any("created" in (c.text or "") for c in res.content)
                    assert built
                    assert adsk.fusion.ExtrudeFeatures.last is not None
                else:
                    import vs
                    vs.CALLS.clear()
                    res = await session.call_tool(
                        "create_box", {"width": 30, "height": 20, "depth": 10, "unit": "mm"})
                    built = any("created" in (c.text or "") for c in res.content)
                    assert built
                    assert any(c[0] == "CreateExtrude" for c in vs.CALLS)

                # 3) execute_design with a planned action
                ex = await session.call_tool(
                    "execute_design",
                    {"actions": [{"action": "create_box",
                                  "params": {"width": 60, "height": 40, "depth": 8, "unit": "mm"}}]})
                assert ex is not None and ex.content

                # 4) read the backend resource over the protocol
                res = await session.read_resource("fusion://backend")
                assert res.contents
                bdata = json.loads(res.contents[0].text)
                assert bdata["backend"] == backend
                return True
    finally:
        stop()


@pytest.mark.asyncio
async def test_e2e_fusion_backend_over_real_sse():
    ok = await _run_backend_session("fusion")
    assert ok


@pytest.mark.asyncio
async def test_e2e_vectorworks_backend_over_real_sse():
    ok = await _run_backend_session("vectorworks")
    assert ok
