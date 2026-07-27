"""
AI photorealistic rendering for FusionMCP plans (ComfyUI / SDXL backend).

Turns a plan's action list (the dimensional truth) into a detailed
text-to-image prompt and renders it with a local ComfyUI server.
The synthetic matplotlib schematic remains the AUTHORITATIVE dimensional
preview; this module adds a photorealistic "what will it look like"
image next to it.

Zero hard dependency: if ComfyUI isn't running, ai_render() returns None
and callers fall back to schematic-only. Stdlib urllib only.
"""

import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Any, Dict, List, Optional

COMFY_HOST = os.getenv("COMFY_HOST", "http://127.0.0.1:8188")

_MATERIAL_WORDS = {
    "aluminum": "machined 6061 aluminum, fine milling marks",
    "steel": "machined steel, brushed finish",
    "plastic": "3D printed PETG plastic, visible layer lines",
    "brass": "machined brass, polished",
}


def comfy_alive(host: Optional[str] = None) -> bool:
    try:
        with urllib.request.urlopen(f"{(host or COMFY_HOST).rstrip('/')}/system_stats", timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        return False


def compose_prompt(actions: List[Dict[str, Any]], description: str = "",
                   material: str = "aluminum") -> str:
    """Build a detailed diffusion prompt from plan actions (the spec truth)."""
    feats = []
    for a in actions or []:
        act = (a.get("action") or "").lower()
        p = a.get("params", {}) or {}
        u = p.get("unit", "mm")
        why = a.get("explanation", "")
        if act == "create_box":
            feats.append(f"rectangular plate {p.get('width',0)}x{p.get('height',0)}x{p.get('depth',0)}{u}"
                         + (f" ({why})" if why else ""))
        elif act == "create_cylinder":
            d = p.get("diameter") or 2 * p.get("radius", 0)
            feats.append(f"cylindrical boss diameter {d}{u} height {p.get('height',0)}{u}"
                         + (f" ({why})" if why else ""))
        elif act == "create_hole":
            pos = p.get("position", {}) or {}
            feats.append(f"drilled hole diameter {p.get('diameter',0)}{u} at ({pos.get('x',0)},{pos.get('y',0)})"
                         + (f" ({why})" if why else ""))
        elif act == "create_sphere":
            feats.append(f"spherical knob radius {p.get('radius',0)}{u}"
                         + (f" ({why})" if why else ""))
    mat = _MATERIAL_WORDS.get(material, material)
    return (
        f"professional product photograph of a precision-machined {description or 'mechanical part'}, "
        f"{mat}, consisting of: " + "; ".join(feats) + ". "
        "Studio lighting, neutral gray background, engineering prototype on a workbench, "
        "extremely detailed, sharp focus, 85mm lens, high resolution"
    )


_NEGATIVE = ("blurry, cartoon, painting, illustration, drawing, text, watermark, "
             "low quality, deformed, extra parts, people, hands")


def _sdxl_workflow(prompt: str, negative: str, ckpt: str, seed: int,
                   width: int = 1024, height: int = 1024, steps: int = 25) -> Dict[str, Any]:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
            "latent_image": ["4", 0], "seed": seed, "steps": steps, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0],
                                                     "filename_prefix": "fusionmcp_ai"}},
    }


def _first_checkpoint(host: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(f"{host}/models/checkpoints", timeout=5) as r:
            names = json.loads(r.read().decode())
        return names[0] if names else None
    except Exception:
        return None


def ai_render(actions: List[Dict[str, Any]], description: str = "",
              material: str = "aluminum", out_path: str = "ai_render.png",
              host: Optional[str] = None, timeout_s: int = 300) -> Optional[str]:
    """Render the plan photorealistically. Returns out_path or None."""
    host = (host or COMFY_HOST).rstrip("/")
    if not comfy_alive(host):
        return None
    ckpt = _first_checkpoint(host)
    if not ckpt:
        return None

    prompt = compose_prompt(actions, description, material)
    wf = _sdxl_workflow(prompt, _NEGATIVE, ckpt, seed=int(time.time()) % 2**31)

    req = urllib.request.Request(
        f"{host}/prompt", data=json.dumps({"prompt": wf}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        pid = json.loads(r.read().decode())["prompt_id"]

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(2)
        try:
            with urllib.request.urlopen(f"{host}/history/{pid}", timeout=10) as r:
                hist = json.loads(r.read().decode())
        except Exception:
            continue
        entry = hist.get(pid)
        if not entry:
            continue
        outputs = entry.get("outputs", {})
        for node_out in outputs.values():
            for img in node_out.get("images", []):
                q = urllib.parse.urlencode({
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output")})
                with urllib.request.urlopen(f"{host}/view?{q}", timeout=60) as r:
                    data = r.read()
                with open(out_path, "wb") as f:
                    f.write(data)
                return out_path
        if entry.get("status", {}).get("completed") and not outputs:
            return None
    return None



