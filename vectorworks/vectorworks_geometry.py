"""
Vectorworks geometry actions — the REAL CAD calls (vs.py backend).

This mirrors fusion_addin/fusion_geometry.py but targets Vectorworks' `vs`
Python module (a flat wrapper over VectorScript functions). Same action-dict
schema, same `execute_action(app, action)` dispatch signature, so the MCP
server can swap backends without changing call sites.

Design notes
-------------
- `vs` is imported lazily inside each function so tests can inject a stub
  `vs` package before import time (no live Vectorworks needed to verify).
- Lengths are passed in the active document's units; Vectorworks works in
  document units (we convert from the user's requested unit to the doc unit
  via vs.GetPrefLong / vs.GetUnits). For the headless test we assume mm.
- Vectorworks builds solids from 2D paths + a profile (extrude/revolve),
  which is conceptually identical to Fusion's sketch + feature approach.
"""

from typing import Any, Dict, Optional

# Vectorworks document-unit -> multiplier to millimetres (for preview sizing).
_UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
    "pt": 0.352778,
}


def _to_doc(value: float, unit: str, doc_unit: str = "mm") -> float:
    """Convert `value` from `unit` to the active doc unit (mm assumed if unknown)."""
    mm = float(value) * _UNIT_TO_MM.get((unit or "mm").lower(), 1.0)
    return mm / _UNIT_TO_MM.get((doc_unit or "mm").lower(), 1.0)


def _doc(app):
    """Resolve the active Vectorworks document handle (stub-friendly)."""
    import vs
    return vs


# --------------------------------------------------------------------------- #
# Primitive creators
# --------------------------------------------------------------------------- #
def create_box(app, params: Dict[str, Any]) -> str:
    import vs
    w = _to_doc(params.get("width", 0), params.get("unit", "mm"))
    h = _to_doc(params.get("height", 0), params.get("unit", "mm"))
    d = _to_doc(params.get("depth", 0), params.get("unit", "mm"))

    # 2D rectangle path on the layer plane.
    vs.ClosePath()
    vs.MoveTo(0, 0)
    vs.LineTo(w, 0)
    vs.LineTo(w, d)
    vs.LineTo(0, d)
    vs.LineTo(0, 0)
    vs.ClosePath()
    h_path = vs.LNewObj()
    vs.CreateExtrude(h_path, d, 0, 0)  # extrude along Z by depth
    return f"Box {w:.2f}x{d:.2f}x{d:.2f} created."


def create_cylinder(app, params: Dict[str, Any]) -> str:
    import vs
    r = _to_doc(params.get("radius", 0), params.get("unit", "mm"))
    h = _to_doc(params.get("height", 0), params.get("unit", "mm"))

    vs.CreateCircleN(0, 0, r)
    h_circle = vs.LNewObj()
    vs.CreateExtrude(h_circle, h, 0, 0)
    return f"Cylinder r={r:.2f} h={h:.2f} created."


def create_sphere(app, params: Dict[str, Any]) -> str:
    import vs
    r = _to_doc(params.get("radius", 0), params.get("unit", "mm"))

    vs.CreateCircleN(0, 0, r)
    h_circle = vs.LNewObj()
    # Revolve the profile 360 degrees about the X axis to form a sphere.
    vs.CreateRevolve(h_circle, 0, 360, 0)
    return f"Sphere r={r:.2f} created."


def create_hole(app, params: Dict[str, Any]) -> str:
    import vs
    d = _to_doc(params.get("diameter", 0), params.get("unit", "mm"))
    pos = params.get("position", {}) or {}
    x = _to_doc(pos.get("x", 0), params.get("unit", "mm"))
    y = _to_doc(pos.get("y", 0), params.get("unit", "mm"))
    depth = params.get("depth")
    if depth is None:
        depth = _to_doc(10, params.get("unit", "mm"))

    vs.CreateCircleN(x, y, d / 2)
    h_hole = vs.LNewObj()
    vs.CreateExtrude(h_hole, depth, 0, 0)
    # Mark as a subtractive solid so it reads as a hole in a Boolean op.
    vs.SetObjBoolType(h_hole, 2)  # 2 == subtract
    return f"Hole d={d:.2f} at ({x:.2f},{y:.2f}) created."


def apply_material(app, params: Dict[str, Any]) -> str:
    import vs
    name = (params.get("material_name") or "").lower()
    vs.ForEachObject(
        lambda h: vs.SetRecord(h, name) if name else None,
        "(SEL=TRUE)",
    )
    return f"Applied material '{params.get('material_name')}' to selection."


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def create_new_sketch(app, params: Dict[str, Any]) -> str:
    import vs
    name = params.get("name") or "Sketch_MCP"
    vs.Layer(name, 1)  # 1 == design layer
    return f"Sketch layer '{name}' created."


def create_parameter(app, params: Dict[str, Any]) -> str:
    import vs
    name = params.get("name") or "Param"
    vs.SetVar(name, float(params.get("expression", 0)))
    return f"Parameter '{name}' = {params.get('expression')} set."


# --------------------------------------------------------------------------- #
# Dispatcher (identical signature to the Fusion backend)
# --------------------------------------------------------------------------- #
def execute_action(app, action: Dict[str, Any]) -> str:
    """Route a single action dict to its Vectorworks implementation."""
    kind = (action.get("action") or "").lower()
    params = action.get("params", {}) or {}
    handlers = {
        "create_box": create_box,
        "create_cylinder": create_cylinder,
        "create_sphere": create_sphere,
        "create_hole": create_hole,
        "apply_material": apply_material,
        "create_new_sketch": create_new_sketch,
        "create_parameter": create_parameter,
    }
    fn = handlers.get(kind)
    if fn is None:
        raise ValueError(f"Unknown action type: {kind}")
    return fn(app, params)
