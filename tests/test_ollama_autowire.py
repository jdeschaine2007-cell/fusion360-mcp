"""
Verify the Ollama zero-config auto-wire for real:

  1. start a FAKE Ollama HTTP server (stdlib http.server) that implements
     GET  /api/tags        -> returns models incl. qwen3:8b
     POST /api/generate   -> returns a JSON plan string
  2. point OLLAMA_HOST at it, call ollama_llm.get_callable()
  3. assert the callable returns a parseable plan and the model is qwen3:8b
  4. (integration) run plan_design through the real server with the auto-wired
     LLM and assert it produces status=planned + preview PNG with NO manual
     set_llm_callable() call.
"""
import json
import os
import sys
import threading
import importlib
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("mcp")

# headless stubs so the server imports without a live CAD app
_STUB = os.path.join(os.path.dirname(__file__), "stubs")
sys.path.insert(0, _STUB)
importlib.import_module("adsk")

_HERE = os.path.abspath(os.path.dirname(__file__))
_REPO = os.path.dirname(_HERE)
for p in (os.path.join(_REPO, "fusion_addin"), _REPO):
    if p not in sys.path:
        sys.path.insert(0, p)


_PLAN = json.dumps({"actions": [
    {"action": "create_box", "params": {"width": 80, "height": 40, "depth": 6, "unit": "mm"},
     "explanation": "plate"},
]})


class _FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            body = json.dumps({"models": [
                {"name": "qwen3:8b"}, {"name": "llama3:8b"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if self.path == "/api/generate":
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)  # discard prompt
            body = json.dumps({"response": _PLAN, "done": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)


@pytest.fixture(scope="module")
def fake_ollama():
    srv = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{port}"
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def test_ollama_autowire_picks_qwen(fake_ollama):
    from fusion_addin.ollama_llm import get_callable
    fn, model = get_callable()
    assert fn is not None
    assert model == "qwen3:8b"  # preferred model chosen
    out = fn("make a plate", "system prompt")
    data = json.loads(out)
    assert data["actions"][0]["action"] == "create_box"


def test_plan_design_zero_config_over_real_server(fake_ollama):
    import fusion_addin.fusion_mcp_server as srv
    srv._ACTIVE = None
    srv.set_backend("fusion")
    # NOTE: do NOT call set_llm_callable() — auto-wire must kick in.
    srv._OLLAMA_TRIED = False
    srv.LLM_CALLABLE = None

    import uvicorn
    cfg = uvicorn.Config(srv.mcp.sse_app(), host="127.0.0.1", port=0,
                        log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            port = server.servers[0].sockets[0].getsockname()[1]
            if port:
                break
        except Exception:
            threading.Event().wait(0.05)
    url = f"http://127.0.0.1:{port}/sse"
    try:
        from mcp.client.sse import sse_client
        from mcp import ClientSession
        import asyncio

        async def go():
            async with sse_client(url=url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool(
                        "plan_design",
                        {"prompt": "a plate 80x40x6", "units": "mm"})
                    text = "".join(c.text for c in res.content
                                     if getattr(c, "type", None) == "text")
                    pd = json.loads(text)
                    assert pd["status"] == "planned"
                    assert pd["preview_png"].startswith("data:image/png;base64,")
                    return True

        assert asyncio.run(go())
    finally:
        server.should_exit = True
