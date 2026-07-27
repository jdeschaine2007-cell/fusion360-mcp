"""
Tests for the preview/plan renderer (adsk-free, runnable anywhere).
"""
import base64

from mcp_server.preview import (
    build_plan,
    make_preview,
    render_preview_png,
)


SAMPLE_JSON = {
    "actions": [
        {"action": "create_box", "params": {"width": 100, "height": 50, "depth": 5, "unit": "mm"},
         "explanation": "Base plate"},
        {"action": "create_hole", "params": {"diameter": 5.5, "position": {"x": 10, "y": 10}, "unit": "mm"},
         "explanation": "M5 clearance hole"},
        {"action": "create_cylinder", "params": {"radius": 8, "height": 40, "unit": "mm"},
         "explanation": "Post"},
    ]
}

SAMPLE_TEXT = (
    "Here is the plan:\n"
    + '{"actions":[{"action":"create_box","params":{"width":100,"height":50,"depth":5,"unit":"mm"}}]}'
)


def test_build_plan_lists_each_action():
    plan = build_plan(SAMPLE_JSON["actions"])
    assert "1." in plan and "2." in plan and "3." in plan
    assert "Box" in plan and "Hole" in plan and "Cylinder" in plan


def test_build_plan_empty():
    assert "No actions" in build_plan([])


def test_render_returns_b64_png():
    data_uri = render_preview_png(SAMPLE_JSON["actions"])
    assert data_uri.startswith("data:image/png;base64,")
    b64 = data_uri.split(",", 1)[1]
    raw = base64.b64decode(b64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic


def test_make_preview_from_json():
    out = make_preview(SAMPLE_TEXT, SAMPLE_JSON)
    # Both the embedded JSON in SAMPLE_TEXT and SAMPLE_JSON's first action
    # describe a 100x50x5 box, so we get >=1 box action.
    assert any(a.get("action") == "create_box" for a in out["actions"])
    assert out["plan_text"].strip()
    assert out["preview_png"].startswith("data:image/png;base64,")


def test_make_preview_empty():
    out = make_preview("sorry, I could not understand", None)
    assert out["actions"] == []
    assert "No actions" in out["plan_text"]
    assert out["preview_png"].startswith("data:image/png;base64,")
