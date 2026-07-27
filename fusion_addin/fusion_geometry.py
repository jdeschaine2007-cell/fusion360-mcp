"""
Fusion 360 geometry actions — the REAL CAD calls.

This module is the single source of truth for turning a structured action dict
into actual Fusion 360 geometry. It is imported by the MCP add-in server
(when running inside Fusion) and is also unit-smoke-tested with a stubbed
`adsk` module so the wiring is verified without a live Fusion instance.

Design notes
-------------
- `adsk` is imported lazily inside each function (not at module top) so that
  tests can inject a stub `adsk` package before import time.
- All user-facing lengths are converted to Fusion's internal unit (cm).
- We only ever build on the root component for simplicity; advanced callers can
  extend this to target occurrences.
"""

from typing import Any, Dict, Optional

# Fusion's internal length unit is centimetres. Convert from common user units.
_UNIT_TO_CM = {
    "mm": 0.1,
    "cm": 1.0,
    "m": 100.0,
    "in": 2.54,
    "ft": 30.48,
}


def _to_cm(value: float, unit: str) -> float:
    return float(value) * _UNIT_TO_CM.get((unit or "mm").lower(), 1.0)


def _root_component(app):
    """Resolve the active Fusion design's root component, or raise a clear error."""
    import adsk  # lazy: lets tests stub adsk before import
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise RuntimeError("No active Fusion design. Open or create a design first.")
    return design.rootComponent


# --------------------------------------------------------------------------- #
# Primitive creators (the geometry Joe-Spencer's server was missing)
# --------------------------------------------------------------------------- #
def create_box(app, params: Dict[str, Any]) -> str:
    import adsk
    root = _root_component(app)
    w = _to_cm(params.get("width", 0), params.get("unit", "mm"))
    h = _to_cm(params.get("height", 0), params.get("unit", "mm"))
    d = _to_cm(params.get("depth", 0), params.get("unit", "mm"))

    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(0, 0, 0),
        adsk.core.Point3D.create(w, d, 0),
    )
    profile = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    distance = adsk.core.ValueInput.createByReal(h)
    extrudes.addSimple(profile, distance, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    return f"Box {w:.2f}x{d:.2f}x{h:.2f} cm created."


def create_cylinder(app, params: Dict[str, Any]) -> str:
    import adsk
    root = _root_component(app)
    r = _to_cm(params.get("radius", 0), params.get("unit", "mm"))
    h = _to_cm(params.get("height", 0), params.get("unit", "mm"))

    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0, 0, 0), r
    )
    profile = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    distance = adsk.core.ValueInput.createByReal(h)
    extrudes.addSimple(profile, distance, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    return f"Cylinder r={r:.2f}cm h={h:.2f}cm created."


def create_sphere(app, params: Dict[str, Any]) -> str:
    import adsk
    import math
    root = _root_component(app)
    r = _to_cm(params.get("radius", 0), params.get("unit", "mm"))

    sketch = root.sketches.add(root.xZConstructionPlane)
    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs
    axis_line = lines.addByTwoPoints(
        adsk.core.Point3D.create(0, -r - 1, 0),
        adsk.core.Point3D.create(0, r + 1, 0),
    )
    arc = arcs.addByCenterStartSweep(
        adsk.core.Point3D.create(0, 0, 0),
        adsk.core.Point3D.create(0, r, 0),
        math.pi,
    )
    lines.addByTwoPoints(arc.endSketchPoint, arc.startSketchPoint)
    profile = sketch.profiles.item(0)
    revolves = root.features.revolveFeatures
    revolve_input = revolves.createInput(
        profile, axis_line, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(2 * math.pi))
    revolves.add(revolve_input)
    return f"Sphere r={r:.2f}cm created."


def create_hole(app, params: Dict[str, Any]) -> str:
    import adsk
    root = _root_component(app)
    d = _to_cm(params.get("diameter", 0), params.get("unit", "mm"))
    pos = params.get("position", {}) or {}
    x = _to_cm(pos.get("x", 0), params.get("unit", "mm"))
    y = _to_cm(pos.get("y", 0), params.get("unit", "mm"))

    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(x, y, 0), d / 2
    )
    profile = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    depth = params.get("depth")
    if depth is not None:
        distance = adsk.core.ValueInput.createByReal(_to_cm(depth, params.get("unit", "mm")))
    else:
        distance = adsk.core.ValueInput.createByReal(10)  # through-ish default
    extrudes.addSimple(profile, distance, adsk.fusion.FeatureOperations.CutFeatureOperation)
    return f"Hole d={d:.2f}cm at ({x:.2f},{y:.2f}) created."


def apply_material(app, params: Dict[str, Any]) -> str:
    root = _root_component(app)
    name = (params.get("material_name") or "").lower()
    for lib in app.materialLibraries:
        for mat in lib.materials:
            if name in mat.name.lower():
                for body in root.bRepBodies:
                    body.material = mat
                return f"Applied material '{mat.name}'."
    raise RuntimeError(f"Material '{params.get('material_name')}' not found in any library.")


# --------------------------------------------------------------------------- #
# Helpers kept from Joe-Spencer (sketch + parameter authoring)
# --------------------------------------------------------------------------- #
_PLANE_MAP = {
    "XY": "xYConstructionPlane",
    "YZ": "yZConstructionPlane",
    "XZ": "xZConstructionPlane",
}


def create_new_sketch(app, params: Dict[str, Any]) -> str:
    root = _root_component(app)
    plane_name = (params.get("plane_name") or "XY").upper()
    plane = getattr(root, _PLANE_MAP.get(plane_name, "xYConstructionPlane"))
    sketch = root.sketches.add(plane)
    sketch.name = params.get("name") or f"Sketch_MCP_{id(sketch) % 10000}"
    return f"Sketch '{sketch.name}' created on {plane_name}."


def create_parameter(app, params: Dict[str, Any]) -> str:
    import adsk
    root = _root_component(app)
    name = params.get("name") or f"Param_{id(root) % 10000}"
    expression = params.get("expression", "10")
    unit = params.get("unit", "mm")
    comment = params.get("comment", "")
    existing = root.userParameters.itemByName(name)
    if existing is not None:
        existing.expression = expression
        existing.unit = unit
        if comment:
            existing.comment = comment
        return f"Parameter '{name}' updated = {expression}."
    p = root.userParameters.add(
        name, adsk.core.ValueInput.createByString(expression), unit, comment
    )
    return f"Parameter '{p.name}' = {p.expression} created."


# --------------------------------------------------------------------------- #
# Dispatcher used by the MCP tool layer
# --------------------------------------------------------------------------- #
def execute_action(app, action: Dict[str, Any]) -> str:
    """Route a single action dict to its implementation. Returns a human summary."""
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
