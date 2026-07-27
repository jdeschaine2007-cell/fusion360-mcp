"""
LIVE LAUNCH / beta demo for FusionMCP.

Boots the REAL FastMCP SSE server (the exact code path the Fusion /
Vectorworks add-ins use) on a free port, then connects a REAL MCP client
over SSE and drives the plan -> preview -> execute flow on BOTH backends.
This is what "launch and test it" means: the same wire an MCP client
(Claude, Cursor) would use.

Run:  /tmp/fmcpenv/bin/python launch_demo.py
"""
import asyncio
import json
import os
import sys
import threading
import importlib

# --- headless stubs so the server boots without a live CAD app ---
_STUB = os.path.join(os.path.dirname(__file__), "tests", "stubs")
sys.path.insert(0, _STUB)
importlib.import_module("adsk")

# --- make server + renderer importable ---
_HERE = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(_HERE, "fusion_addin"))
sys.path.insert(0, _HERE)

import uvicorn
from mcp.client.sse import sse_client
from mcp import ClientSession


def _start(app):
    cfg = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        try:
            port = srv.servers[0].sockets[0].getsockname()[1]
            if port:
                return f"http://127.0.0.1:{port}/sse", (lambda: setattr(srv, "should_exit", True))
        except Exception:
            threading.Event().wait(0.05)
    raise RuntimeError("server did not bind")


class FakeLLM:
    def __call__(self, prompt, system):
        return json.dumps({"actions": [
            {"action": "create_box",
             "params": {"width": 100, "height": 50, "depth": 5, "unit": "mm"},
             "explanation": "base plate"},
            {"action": "create_hole",
             "params": {"diameter": 5.5, "position": {"x": 10, "y": 10}, "unit": "mm"},
             "explanation": "M5 clearance hole"},
        ]})


async def _demo_backend(backend):
    import fusion_addin.fusion_mcp_server as srv
    srv._ACTIVE = None
    srv.set_backend(backend)
    srv.set_llm_callable(FakeLLM())

    url, stop = _start(srv.mcp.sse_app())
    print(f"\n{'='*70}\n  LIVE LAUNCH — backend: {backend.upper()}\n  MCP SSE endpoint: {url}\n{'='*70}")
    try:
        async with sse_client(url=url) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                print(f"[init]  server={init.serverInfo.name}")

                tools = await session.list_tools()
                print(f"[tools]  {', '.join(t.name for t in tools.tools)}")

                # 1) PLAN — proposal + preview, nothing built
                plan = await session.call_tool(
                    "plan_design", {"prompt": "base plate 100x50 with an M5 hole", "units": "mm"})
                ptext = "".join(c.text for c in plan.content if getattr(c, "type", None) == "text")
                pd = json.loads(ptext)
                print(f"[plan]  status={pd['status']}  steps={len(pd['actions'])}  "
                      f"preview={'yes' if pd['preview_png'].startswith('data:image/png;base64,') else 'NO'}")
                print("        plan_text ↓")
                for line in pd["plan_text"].splitlines():
                    print("          " + line)

                # 2) EXECUTE — build for real (via stubbed cad call chain)
                ex = await session.call_tool(
                    "execute_design", {"actions": pd["actions"]})
                extext = "".join(c.text for c in ex.content if getattr(c, "type", None) == "text")
                print(f"[execute] results ↓\n          " + extext.replace("\n", "\n          "))

                # 3) RESOURCE — which app are we driving?
                res = await session.read_resource("fusion://backend")
                bdata = json.loads(res.contents[0].text)
                print(f"[resource fusion://backend]  active_backend={bdata['backend']}")
                return True
    finally:
        stop()


async def main():
    print("\nFusionMCP — LIVE LAUNCH / BETA DEMO")
    print("Booting the real FastMCP SSE server and connecting a real MCP client.")
    await _demo_backend("fusion")
    await _demo_backend("vectorworks")
    print(f"\n{'='*70}\n  DONE. Both backends drove the real MCP wire successfully.\n{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
