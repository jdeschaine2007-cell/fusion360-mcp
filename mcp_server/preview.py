"""
FusionMCP Preview Renderer
============================

Turns an LLM's proposed CAD action(s) into:
  1. a human-readable step-by-step PLAN (text)
  2. a synthetic matplotlib schematic (PNG, base64) shown in the
     Fusion palette BEFORE anything is committed to the design.

IMPORTANT: This module is 100% adsk-free (no Fusion imports) so it can
run/be tested anywhere — including CI and a headless WSL box with no
Fusion installed. That is what lets us verify the preview without Fusion.
"""

from __future__ import annotations

import base64
import io
import json
import re
import numpy as np
from typing import Any, Dict, List, Optional

# matplotlib is imported lazily inside render() so importing this module
# never hard-fails in a bare environment.


# ---------------------------------------------------------------------------
# Action model parsing
# ---------------------------------------------------------------------------

def _as_action_list(llm_output: str, parsed_json: Optional[dict]) -> List[dict]:
    """
    Normalise whatever the model gave us into a list of action dicts.

    Handles the shapes seen in this repo:
      - an already-parsed action dict (passed via parsed_json)
      - {"actions": [ {...}, {...} ]}      (action sequence)
      - {"action": "...", "params": {...}}   (single action)
      - raw text with an embedded JSON blob   (fallback regex miner)
    """
    # 1) An explicit parsed object wins.
    if isinstance(parsed_json, dict):
        if "actions" in parsed_json and isinstance(parsed_json["actions"], list):
            return [a for a in parsed_json["actions"] if isinstance(a, dict)]
        if "action" in parsed_json:
            return [parsed_json]

    # 2) Try strict JSON parse of the raw output (clients return a JSON string).
    raw = (llm_output or "").strip()
    if raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                if "actions" in obj and isinstance(obj["actions"], list):
                    return [a for a in obj["actions"] if isinstance(a, dict)]
                if "action" in obj:
                    return [obj]
        except Exception:
            pass

    # 3) Fallback: mine JSON objects containing an "action" key from prose.
    actions: List[dict] = []
    try:
        for m in re.finditer(r"\{[^{}]*\"action\"[^{}]*\}", raw, re.S):
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict) and "action" in obj:
                    actions.append(obj)
            except Exception:
                pass
    except Exception:
        pass
    return actions


# ---------------------------------------------------------------------------
# Unit + readability helpers
# ---------------------------------------------------------------------------

_UNIT_TO_CM = {"mm": 0.1, "cm": 1.0, "m": 100.0, "in": 2.54, "ft": 30.48}
_CM_TO_MM = 10.0


def _unit_to_cm(value: float, unit: str) -> float:
    return value * _UNIT_TO_CM.get((unit or "mm").lower(), 1.0)


def _fmt_dim(value_cm: float) -> str:
    """Render a cm value back to the most readable unit."""
    mm = value_cm * _CM_TO_MM
    if mm >= 1000:
        return f"{mm / 1000:.2f} m"
    if mm < 10:
        return f"{mm:.1f} mm"
    return f"{mm:.0f} mm"


# ---------------------------------------------------------------------------
# Plan text generation
# ---------------------------------------------------------------------------

def build_plan(actions: List[dict]) -> str:
    """Produce a numbered, human-readable plan from the action list."""
    if not actions:
        return "No actions were produced. The model returned no executable steps."

    lines = [f"PLAN — {len(actions)} step(s) before executing:", ""]
    for i, a in enumerate(actions, 1):
        act = a.get("action", "unknown")
        params = a.get("params", {}) or {}
        unit = params.get("unit", "mm")
        desc = _describe(act, params, unit)
        lines.append(f"{i}. {desc}")
        expl = a.get("explanation")
        if expl:
            lines.append(f"     ↳ {expl}")
        deps = a.get("dependencies")
        if deps:
            lines.append(f"     (depends on: {deps})")
    lines.append("")
    lines.append("Review the schematic, then press EXECUTE to build it in Fusion.")
    return "\n".join(lines)


def _describe(action: str, p: dict, unit: str) -> str:
    a = action.lower()
    if a == "create_box":
        return (f"Box  {_fmt_dim(_unit_to_cm(p.get('width', 0), unit))} × "
                f"{_fmt_dim(_unit_to_cm(p.get('height', 0), unit))} × "
                f"{_fmt_dim(_unit_to_cm(p.get('depth', 0), unit))}")
    if a == "create_cylinder":
        _cyl_r = p.get('radius') or (p.get('diameter', 0) / 2.0)
        return (f"Cylinder  ⌀ {_fmt_dim(2 * _unit_to_cm(_cyl_r, unit))} "
                f"× {_fmt_dim(_unit_to_cm(p.get('height', 0), unit))}")
    if a == "create_sphere":
        return f"Sphere  ⌀ {_fmt_dim(2 * _unit_to_cm(p.get('radius', 0), unit))}"
    if a == "create_hole":
        d = _fmt_dim(_unit_to_cm(p.get('diameter', 0), unit))
        pos = p.get("position", {})
        where = ""
        if isinstance(pos, dict):
            where = (f" at ({pos.get('x', 0)}, {pos.get('y', 0)}, "
                     f"{pos.get('z', 0)})")
        return f"Hole  ⌀ {d}{where}"
    if a == "fillet":
        return f"Fillet  r = {_fmt_dim(_unit_to_cm(p.get('radius', 0), unit))} on edges"
    if a == "extrude":
        return f"Extrude  {_fmt_dim(_unit_to_cm(p.get('distance', 0), unit))}"
    if a == "apply_material":
        return f"Material  → {p.get('material_name', '?')}"
    # Generic fallback
    return f"{action}  ({', '.join(f'{k}={v}' for k, v in p.items())})"


# ---------------------------------------------------------------------------
# Synthetic schematic renderer
# ---------------------------------------------------------------------------

def render_preview_png(actions: List[dict], unit_hint: str = "mm") -> str:
    """
    Render a schematic of the proposed geometry and return a base64 PNG
    data-URI string (data:image/png;base64,...).

    Strategy (honest & simple — this is a PLAN preview, not a CAD kernel):
      - Each primitive gets a labelled box in a 3D-ish isometric grid.
      - Boxes/cylinders/spheres show their dimensions; holes are flagged.
    This is intentionally a *sketch*, clearly distinct from real Fusion geometry.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (registers 3d proj)

    if not actions:
        fig = plt.figure(figsize=(6, 3))
        fig.text(0.5, 0.5, "No geometry to preview",
                 ha="center", va="center", fontsize=14, color="gray")
        return _fig_to_b64(fig)

    # Parse each primitive into a draw descriptor (cm), stacked along Z so they
    # don't overlap and you can read the sequence.
    shapes: List[dict] = []
    z_cursor = 0.0
    for a in actions:
        act = a.get("action", "").lower()
        p = a.get("params", {}) or {}
        u = p.get("unit", unit_hint)
        if act == "create_box":
            w = _unit_to_cm(p.get("width", 0), u)
            h = _unit_to_cm(p.get("height", 0), u)
            d = _unit_to_cm(p.get("depth", 0), u)
            shapes.append({"kind": "box", "label": "Box", "size": (w, h, d), "z0": z_cursor, "color": "#3498db"})
            z_cursor += d + 1.0
        elif act == "create_cylinder":
            r = _unit_to_cm(p.get("radius") or (p.get("diameter", 0) / 2.0), u)
            hgt = _unit_to_cm(p.get("height", 0), u)
            shapes.append({"kind": "cyl", "label": "Cyl", "size": (2 * r, 2 * r, hgt), "z0": z_cursor, "color": "#16a085"})
            z_cursor += hgt + 1.0
        elif act == "create_sphere":
            r = _unit_to_cm(p.get("radius", 0), u)
            shapes.append({"kind": "sph", "label": "Sph", "size": (2 * r, 2 * r, 2 * r), "z0": z_cursor, "color": "#8e44ad"})
            z_cursor += 2 * r + 1.0
        elif act == "create_hole":
            d = _unit_to_cm(p.get("diameter", 0), u)
            pos = p.get("position", {}) or {}
            shapes.append({"kind": "hole", "label": "Hole", "size": (d, d, 0.6), "z0": z_cursor,
                          "color": "#e67e22",
                          "xy": (_unit_to_cm(pos.get("x", 0), u), _unit_to_cm(pos.get("y", 0), u))})
            z_cursor += 1.0
        elif act == "fillet":
            shapes.append({"kind": "op", "label": "Fillet", "size": (1.0, 1.0, 1.0), "z0": z_cursor, "color": "#9b59b6"})
            z_cursor += 1.0
        else:
            shapes.append({"kind": "op", "label": act[:6], "size": (1.0, 1.0, 1.0), "z0": z_cursor, "color": "#9b59b6"})
            z_cursor += 1.0

    fig = plt.figure(figsize=(7, 5))
    ax = fig.add_subplot(111, projection="3d")
    ax.set_title("PREVIEW — proposed geometry (synthetic plan, not final)",
                 fontsize=11, color="#c0392b")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")

    for s in shapes:
        sx, sy, sz = s["size"]
        x0, y0 = 0.0, 0.0
        z0 = s["z0"]
        if s["kind"] == "box":
            _draw_box(ax, x0, y0, z0, sx * _CM_TO_MM, sy * _CM_TO_MM, sz * _CM_TO_MM, s["color"], s["label"])
        elif s["kind"] == "cyl":
            _draw_cylinder(ax, x0 + sx / 2 * _CM_TO_MM, y0 + sy / 2 * _CM_TO_MM,
                           z0 * _CM_TO_MM, (sx / 2) * _CM_TO_MM, sz * _CM_TO_MM, s["color"], s["label"])
        elif s["kind"] == "sph":
            _draw_sphere(ax, x0 + sx / 2 * _CM_TO_MM, y0 + sy / 2 * _CM_TO_MM,
                         z0 * _CM_TO_MM + sz / 2 * _CM_TO_MM, (sx / 2) * _CM_TO_MM, s["color"], s["label"])
        elif s["kind"] == "hole":
            hx, hy = s["xy"]
            _draw_hole(ax, hx * _CM_TO_MM, hy * _CM_TO_MM, z0 * _CM_TO_MM,
                       (sx / 2) * _CM_TO_MM, sz * _CM_TO_MM, s["color"], s["label"])
        else:
            _draw_box(ax, x0, y0, z0, sx * _CM_TO_MM, sy * _CM_TO_MM, sz * _CM_TO_MM, s["color"], s["label"])

    ax.set_box_aspect([1, 1, max(0.4, (z_cursor * _CM_TO_MM) / 40.0)])
    ax.view_init(elev=22, azim=-55)
    return _fig_to_b64(fig)


def _draw_box(ax, x0, y0, z0, sx, sy, sz, color, label):
    xs = [x0, x0 + sx, x0 + sx, x0, x0, x0 + sx, x0 + sx, x0]
    ys = [y0, y0, y0 + sy, y0 + sy, y0, y0, y0 + sy, y0 + sy]
    zs = [z0, z0, z0, z0, z0 + sz, z0 + sz, z0 + sz, z0 + sz]
    ax.scatter(xs, ys, zs, color=color, s=8, alpha=0.9)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    from mpl_toolkits.mplot3d.art3d import Line3D
    for i, j in edges:
        ax.add_line(Line3D([xs[i], xs[j]], [ys[i], ys[j]], [zs[i], zs[j]],
                           color=color, alpha=0.7, linewidth=1.2))
    ax.text(x0 + sx / 2, y0 + sy / 2, z0 + sz / 2, label, color=color, fontsize=8, ha="center", va="center")


def _draw_cylinder(ax, cx, cy, z0, r, h, color, label):
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    theta = np.linspace(0, 2 * np.pi, 32)
    # side surface
    x = cx + r * np.cos(theta)
    y = cy + r * np.sin(theta)
    z_bot = np.full_like(theta, z0)
    z_top = np.full_like(theta, z0 + h)
    ax.plot_surface(x.reshape(1, -1), y.reshape(1, -1),
                   np.vstack([z_bot, z_top]), color=color, alpha=0.25, linewidth=0)
    # rims
    ax.plot(x, y, z_bot, color=color, alpha=0.8, linewidth=1.4)
    ax.plot(x, y, z_top, color=color, alpha=0.8, linewidth=1.4)
    ax.text(cx, cy, z0 + h / 2, label, color=color, fontsize=8, ha="center", va="center")


def _draw_sphere(ax, cx, cy, cz, r, color, label):
    u = np.linspace(0, 2 * np.pi, 24)
    v = np.linspace(0, np.pi, 16)
    xs = cx + r * np.outer(np.cos(u), np.sin(v))
    ys = cy + r * np.outer(np.sin(u), np.sin(v))
    zs = cz + r * np.outer(np.ones_like(u), np.cos(v))
    ax.plot_wireframe(xs, ys, zs, color=color, alpha=0.5, linewidth=0.6)
    ax.text(cx, cy, cz, label, color=color, fontsize=8, ha="center", va="center")


def _draw_hole(ax, hx, hy, z0, r, h, color, label):
    """Draw a hole as a ring (annulus) on the base plane — clearly a void, not a block."""
    theta = np.linspace(0, 2 * np.pi, 32)
    x = hx + r * np.cos(theta)
    y = hy + r * np.sin(theta)
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    ax.plot(x, y, np.full_like(theta, z0), color=color, linewidth=2.0, linestyle="--")
    # dashed descent lines to show depth
    for ang in (0, np.pi / 2, np.pi, 3 * np.pi / 2):
        ax.plot([hx + r * np.cos(ang)], [hy + r * np.sin(ang)],
                [z0, z0 + h], color=color, alpha=0.6, linestyle=":", linewidth=1.0)
    ax.text(hx, hy, z0 + h + 1.0, label, color=color, fontsize=8, ha="center", va="bottom")


def _fig_to_b64(fig) -> str:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# High-level entry used by the server
# ---------------------------------------------------------------------------

def make_preview(llm_output: str, parsed_json: Optional[dict]) -> Dict[str, Any]:
    """
    Given the raw LLM text + any parsed JSON, return:
        {
          "actions": [...],          # normalised action list
          "plan_text": "...",        # human-readable plan
          "preview_png": "data:..."  # base64 PNG data-URI
        }
    The caller (server endpoint) returns this to the add-in, which shows it
    and ONLY executes `actions` after the user presses EXECUTE.
    """
    actions = _as_action_list(llm_output, parsed_json)
    return {
        "actions": actions,
        "plan_text": build_plan(actions),
        "preview_png": render_preview_png(actions),
    }
