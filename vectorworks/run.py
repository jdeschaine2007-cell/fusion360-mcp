"""
Vectorworks add-in entry point for the FusionMCP (dual-CAD) server.

Load this as a Vectorworks Python script / plug-in. It starts the same
FastMCP server used by the Fusion add-in, but with the Vectorworks (`vs`)
backend forced. Any MCP client pointed at http://127.0.0.1:3000/sse can
then drive Vectorworks with the same plan-then-preview-then-execute flow.

Deploy: in Vectorworks, Scripts menu → Run Script → select this file, or
install it as a plug-in. Requires `mcp` (and matplotlib/numpy for previews)
installed into Vectorworks' Python — use the repo's install_for_fusion.py
adapted, or `pip install mcp matplotlib numpy` in the VW Python.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for p in (_HERE, _REPO, os.path.join(_REPO, "fusion_addin")):
    if p not in sys.path:
        sys.path.insert(0, p)

import vs  # Vectorworks Python module (present inside VW)

import fusion_addin.fusion_mcp_server as srv

# Force the Vectorworks backend (vs.py).
srv.set_backend("vectorworks")

if __name__ == "__main__":
    srv.run_server()
    print("FusionMCP (Vectorworks backend) running at http://127.0.0.1:3000/sse")
