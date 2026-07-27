"""
FusionMCP — FastMCP server add-in for Fusion 360 AND Vectorworks.

This is the CLEANED, merged successor to Joe-Spencer's fusion-mcp-server:
it is a genuine MCP server (FastMCP, SSE) so any MCP client (Claude Desktop,
Cursor, Cline) can connect — AND it exposes the working geometry tools that
Joe-Spencer's server lacked (box / cylinder / sphere / hole), ported from
jaskirat1616's Fusion action executor, PLUS a Vectorworks backend so the
same server drives either CAD app.

It ALSO exposes the plan-then-preview flow: `plan_design` asks an LLM
for proposed actions, renders a synthetic preview PNG (via mcp_server.preview),
and returns the plan WITHOUT building anything. Execution only happens when a
client calls one of the explicit geometry tools.

Backends are swappable: the server auto-detects whether it is running inside
Fusion (adsk present) or Vectorworks (vs present), or you can force one with
`set_backend("fusion" | "vectorworks")`. The action schema is identical, so
`preview.py` and `plan_design` are 100% backend-agnostic.

Run inside the host CAD app as an add-in (see fusion_addin/run.py). Hardcoded
paths are gone; no debug file spam.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# Shared preview renderer (CAD-agnostic). Imported lazily-tolerant so the
# server still loads in a pure-geometry deployment.
try:
    from mcp_server.preview import make_preview
except Exception:  # pragma: no cover - preview is optional for pure-geometry use
    make_preview = None

# Backend packages. Imported lazily so the server can start in either host.
from . import fusion_geometry as _fusion_geo

# Where this add-in lives (used only for the comm dir, no user home leakage).
ADDIN_DIR = Path(__file__).resolve().parent
COMM_DIR = ADDIN_DIR / "mcp_comm"
COMM_DIR.mkdir(exist_ok=True)

# An LLM call is injected here so the add-in stays free of any specific
# provider SDK. Signature: fn(prompt: str, system: str) -> str (raw JSON text)
LLM_CALLABLE = None
_OLLAMA_TRIED = False


def set_llm_callable(fn: Callable[[str, str], str]):
    """Register a callable the plan_design tool uses to talk to an LLM."""
    global LLM_CALLABLE
    LLM_CALLABLE = fn


def _maybe_autowire_llm():
    """Lazily try to wire an Ollama LLM (qwen3:8b) so plan_design
    is zero-config. No-ops silently if Ollama isn't running / has no
    model, leaving LLM_CALLABLE None until you set one yourself."""
    global LLM_CALLABLE, _OLLAMA_TRIED
    if LLM_CALLABLE is not None or _OLLAMA_TRIED:
        return
    _OLLAMA_TRIED = True
    try:
        from .ollama_llm import get_callable
        fn, model = get_callable()
        if fn is not None:
            LLM_CALLABLE = fn
            print(f"[FusionMCP] auto-wired LLM: {model}")
    except Exception:
        # Ollama not present / unreachable — fine, planning just stays off.
        pass


# --------------------------------------------------------------------------- #
# Backend registry — Fusion 360 (adsk) and Vectorworks (vs)
# --------------------------------------------------------------------------- #
class _Backend:
    def __init__(self, name: str, geo_module, app_handle, ui_handle=None):
        self.name = name
        self.geo = geo_module
        self.app = app_handle
        self.ui = ui_handle

    def execute_action(self, action: Dict[str, Any]) -> str:
        return self.geo.execute_action(self.app, action)


_BACKENDS: Dict[str, _Backend] = {}
_ACTIVE: Optional[_Backend] = None
_app = None
_ui = None


def _init_fusion_backend() -> Optional[_Backend]:
    try:
        import adsk.core
        import adsk.fusion
    except Exception:
        return None
    app = adsk.core.Application.get()
    return _Backend("fusion", _fusion_geo, app, getattr(app, "userInterface", None))


def _init_vectorworks_backend() -> Optional[_Backend]:
    try:
        import vs  # the Vectorworks Python module
    except Exception:
        return None
    try:
        import vectorworks.vectorworks_geometry as vw_geo
    except Exception:
        # Fall back to bundled path if imported as a top-level module.
        try:
            from vectorworks import vectorworks_geometry as vw_geo
        except Exception:
            return None
    # vs is module-level; pass None as the app handle (signature parity).
    return _Backend("vectorworks", vw_geo, None, None)


def _auto_detect_backend() -> _Backend:
    for init in (_init_fusion_backend, _init_vectorworks_backend):
        try:
            b = init()
        except Exception:
            b = None
        if b is not None:
            return b
    raise RuntimeError(
        "No CAD backend available. Run inside Fusion 360 or Vectorworks, "
        "or call set_backend() with a registered backend."
    )


def set_backend(name: str):
    """Force a specific backend ('fusion' or 'vectorworks')."""
    global _ACTIVE
    if name == "fusion":
        _ACTIVE = _init_fusion_backend()
    elif name == "vectorworks":
        _ACTIVE = _init_vectorworks_backend()
    else:
        raise ValueError(f"Unknown backend: {name}")
    if _ACTIVE is None:
        raise RuntimeError(f"Backend '{name}' could not be initialised.")


def get_backend() -> _Backend:
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = _auto_detect_backend()
    return _ACTIVE


# --------------------------------------------------------------------------- #
# Resources (read-only views of the active design)
# --------------------------------------------------------------------------- #
# Resources (read-only views of the active design)
# --------------------------------------------------------------------------- #
mcp = FastMCP("FusionMCP Server")


@mcp.resource("fusion://active-document-info")
def active_document_info() -> Dict[str, Any]:
    be = get_backend()
    if be.name == "fusion":
        import adsk
        doc = be.app.activeDocument
        if not doc:
            return {"error": "No active document"}
        try:
            path = doc.dataFile.name if doc.dataFile else "Unsaved"
        except Exception:
            path = "Unsaved"
        return {"name": doc.name, "path": path, "type": str(doc.documentType)}
    # Vectorworks: vs.GetActiveDocument / vs.GetDocName
    try:
        import vs
        return {"name": vs.GetDocName(), "path": "active", "type": "Vectorworks"}
    except Exception as e:
        return {"error": str(e)}


@mcp.resource("fusion://design-structure")
def design_structure() -> Dict[str, Any]:
    be = get_backend()
    if be.name == "fusion":
        import adsk
        doc = be.app.activeDocument
        if not doc:
            return {"error": "No active document"}
        design = adsk.fusion.Design.cast(
            doc.products.itemByProductType("DesignProductType"))
        if not design:
            return {"error": "No design in document"}
        root = design.rootComponent
        return {
            "design_name": design.name,
            "root_component": {
                "name": root.name,
                "bodies": [b.name for b in root.bodies],
                "sketches": [s.name for s in root.sketches],
                "occurrences": [
                    {"name": o.name, "component": o.component.name}
                    for o in root.occurrences
                ],
            },
        }
    # Vectorworks: summarise selected / top-level objects
    try:
        import vs
        return {
            "design_name": vs.GetDocName(),
            "root_component": {
                "name": "Vectorworks Document",
                "objects": vs.NumObjs(""),
            },
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.resource("fusion://parameters")
def parameters() -> Dict[str, Any]:
    be = get_backend()
    if be.name == "fusion":
        import adsk
        doc = be.app.activeDocument
        if not doc:
            return {"error": "No active document"}
        design = adsk.fusion.Design.cast(
            doc.products.itemByProductType("DesignProductType"))
        if not design:
            return {"error": "No design in document"}
        return {
            "parameters": [
                {"name": p.name, "value": p.value, "expression": p.expression,
                 "unit": p.unit, "comment": p.comment}
                for p in design.allParameters
            ]
        }
    return {"parameters": [], "note": "Vectorworks stores params as records/vars"}


# --------------------------------------------------------------------------- #
# Geometry tools — these BUILD real geometry on the active backend
# --------------------------------------------------------------------------- #
@mcp.tool()
def create_box(width: float, height: float, depth: float, unit: str = "mm") -> str:
    """Create a rectangular box (sketch + extrude)."""
    return get_backend().execute_action({
        "action": "create_box",
        "params": {"width": width, "height": height, "depth": depth, "unit": unit},
    })


@mcp.tool()
def create_cylinder(radius: float, height: float, unit: str = "mm") -> str:
    """Create a cylinder (sketch circle + extrude)."""
    return get_backend().execute_action({
        "action": "create_cylinder",
        "params": {"radius": radius, "height": height, "unit": unit},
    })


@mcp.tool()
def create_sphere(radius: float, unit: str = "mm") -> str:
    """Create a sphere (profile arc + revolve)."""
    return get_backend().execute_action({
        "action": "create_sphere",
        "params": {"radius": radius, "unit": unit},
    })


@mcp.tool()
def create_hole(diameter: float, unit: str = "mm",
                x: float = 0.0, y: float = 0.0, depth: Optional[float] = None) -> str:
    """Create a cut hole at (x, y) on the XY plane."""
    params: Dict[str, Any] = {
        "diameter": diameter, "unit": unit,
        "position": {"x": x, "y": y},
    }
    if depth is not None:
        params["depth"] = depth
    return get_backend().execute_action({"action": "create_hole", "params": params})


@mcp.tool()
def apply_material(material_name: str) -> str:
    """Apply a named material (substring match) to all bodies."""
    return get_backend().execute_action({
        "action": "apply_material", "params": {"material_name": material_name}
    })


@mcp.tool()
def create_new_sketch(plane_name: str = "XY", name: Optional[str] = None) -> str:
    """Create a new empty sketch on XY / YZ / XZ plane."""
    return get_backend().execute_action({
        "action": "create_new_sketch",
        "params": {"plane_name": plane_name, "name": name},
    })


@mcp.tool()
def create_parameter(name: str, expression: str, unit: str = "mm",
                    comment: str = "") -> str:
    """Create (or update) a user parameter."""
    return get_backend().execute_action({
        "action": "create_parameter",
        "params": {"name": name, "expression": expression, "unit": unit, "comment": comment},
    })


@mcp.tool()
def execute_design(actions: List[Dict[str, Any]]) -> str:
    """Execute a list of action dicts (each with 'action' + 'params')."""
    be = get_backend()
    results = []
    for i, action in enumerate(actions):
        try:
            results.append(be.execute_action(action))
        except Exception as e:
            results.append(f"[{i}] ERROR: {e}")
    return "\n".join(results)


@mcp.resource("fusion://backend")
def backend_info() -> Dict[str, Any]:
    """Report which CAD backend is active and its supported actions."""
    try:
        be = get_backend()
    except Exception as e:
        return {"backend": None, "error": str(e)}
    return {
        "backend": be.name,
        "actions": [
            "create_box", "create_cylinder", "create_sphere",
            "create_hole", "apply_material", "create_new_sketch",
            "create_parameter",
        ],
    }


# --------------------------------------------------------------------------- #
# Plan tool — PROPOSES, renders a preview, does NOT build
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = """You are FusionMCP, a parametric CAD planner. Given a user request
and the current design context, respond with ONLY a JSON object of this shape:
{"actions":[{"action":"create_box","params":{"width":100,"height":50,"depth":5,"unit":"mm"},
"explanation":"..."}]}
Supported actions: create_box, create_cylinder, create_sphere, create_hole,
apply_material. Use SI/mm. No prose outside the JSON.

When the request names a REAL standardized part or interface (e.g. NEMA 17
stepper mount, 608 bearing pocket, M5 clearance hole, DIN rail clip, GoPro
mount, 2020 aluminum extrusion), use the PUBLISHED specification dimensions
you know for it — e.g. NEMA 17: 42.3mm faceplate, 31.0mm bolt circle, 4x M3
holes, 22mm pilot bore; 608 bearing: 22mm OD, 8mm ID, 7mm wide; M5 clearance:
5.5mm. Put the source standard in each action's "explanation"
(e.g. "M3 clearance per NEMA 17 bolt pattern, 31mm BCD"). Do NOT invent
dimensions for standard parts."""


@mcp.tool()
def plan_design(prompt: str, units: str = "mm", ai_image: bool = False,
                material: str = "aluminum") -> Dict[str, Any]:
    """Propose a CAD plan from a natural-language request.

    Returns a step plan + a synthetic preview PNG (base64). Nothing is built
    in the host CAD app — call execute_design / the geometry tools to commit.
    Set ai_image=True to ALSO return a photorealistic AI rendering
    (requires a local ComfyUI server; silently skipped when absent).
    """
    if make_preview is None:
        return {"error": "preview renderer (mcp_server.preview) not available"}
    _maybe_autowire_llm()
    if LLM_CALLABLE is None:
        return {"error": "no LLM configured; set_llm_callable() or run Ollama before planning"}

    context = _design_context()
    full_prompt = (
        f"Design context: units={units}, state={context.get('design_state')}\n"
        f"Request: {prompt}"
    )
    raw = LLM_CALLABLE(full_prompt, _SYSTEM_PROMPT)
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        parsed = None
    preview = make_preview(raw if isinstance(raw, str) else json.dumps(raw or {}), parsed)
    result = {
        "status": "planned",
        "actions": preview["actions"],
        "plan_text": preview["plan_text"],
        "preview_png": preview["preview_png"],
    }
    if ai_image:
        try:
            import base64 as _b64
            import tempfile as _tmp
            from mcp_server.render_ai import ai_render
            with _tmp.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                out = ai_render(preview["actions"], description=prompt,
                                material=material, out_path=tf.name)
            if out:
                with open(out, "rb") as f:
                    result["ai_render_png"] = (
                        "data:image/png;base64," + _b64.b64encode(f.read()).decode())
            else:
                result["ai_render_note"] = "ComfyUI not reachable or no checkpoint; schematic only"
        except Exception as e:  # AI render is best-effort, never breaks planning
            result["ai_render_note"] = f"AI render skipped: {e}"
    return result


def _design_context() -> Dict[str, Any]:
    try:
        be = get_backend()
    except Exception:
        return {"design_state": "no_backend"}
    if be.name == "fusion":
        import adsk
        design = adsk.fusion.Design.cast(be.app.activeProduct)
        if not design:
            return {"design_state": "no_design"}
        comp = design.activeComponent
        return {
            "units": design.unitsManager.defaultLengthUnits,
            "design_state": "has_geometry" if comp.bRepBodies.count else "empty",
            "bodies": comp.bRepBodies.count,
        }
    # Vectorworks: report doc unit + object count.
    try:
        import vs
        return {
            "units": "document",
            "design_state": "has_geometry" if vs.NumObjs("") else "empty",
            "bodies": vs.NumObjs(""),
        }
    except Exception:
        return {"design_state": "error"}


# --------------------------------------------------------------------------- #
# Prompt templates (for LLM-driven clients)
# --------------------------------------------------------------------------- #
@mcp.prompt()
def create_sketch_prompt(description: str) -> Dict[str, Any]:
    return {"messages": [
        {"role": "system", "content": "You are an expert Fusion 360 sketch designer."},
        {"role": "user", "content": f"Sketch requirements: {description}"},
    ]}


@mcp.prompt()
def parameter_setup_prompt(description: str) -> Dict[str, Any]:
    return {"messages": [
        {"role": "system", "content": "You are an expert in Fusion 360 parametric design."},
        {"role": "user", "content": f"Set up parameters for: {description}"},
    ]}


# --------------------------------------------------------------------------- #
# Server bootstrap (runs in a background thread inside Fusion)
# --------------------------------------------------------------------------- #
def run_server(host: str = "127.0.0.1", port: int = 3000):
    """Start the FastMCP SSE server in a daemon thread."""
    import uvicorn

    def _serve():
        uvicorn.run(mcp.sse_app(), host=host, port=port, log_level="info")

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return t


if __name__ == "__main__":  # pragma: no cover
    run_server()
