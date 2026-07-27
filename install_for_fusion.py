"""
Installer: put the FusionMCP add-in deps into Fusion 360's own Python.

Fusion 360 ships its own Python, separate from your system Python (and from
this repo's venv). The `mcp` server must run inside that interpreter, so
the `mcp` (+ matplotlib/numpy) packages have to be installed there.

Usage:
    python install_for_fusion.py
    # or be explicit:
    python install_for_fusion.py "C:/Users/You/AppData/.../Python/python.exe"

It auto-discovers common Fusion Python locations on Windows/macOS.
"""

import json
import os
import subprocess
import sys


# Candidate Fusion 360 Python executables (searched in order).
_CANDIDATES = [
    # Windows (per-user Autodesk webdeploy)
    os.path.expandvars(r"%LOCALAPPDATA%\Autodesk\webdeploy\production"),
    os.path.expandvars(r"%APPDATA%\Autodesk\webdeploy\production"),
    # macOS Fusion Python
    "/Library/Application Support/Autodesk/Autodesk Fusion 360/Fusion360 Mac Python",
    "/Applications/Autodesk Fusion 360/Fusion360 Mac Python",
]


def _find_fusion_python() -> "list[str]":
    found = []
    for base in _CANDIDATES:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.lower() == "python.exe" or f.lower() == "python":
                    found.append(os.path.join(root, f))
    return found


def _install(py_exe: str):
    print(f"Installing into: {py_exe}")
    # Use Fusion's own pip.
    cmd = [py_exe, "-m", "pip", "install", "--upgrade",
            "mcp[cli]", "matplotlib", "numpy", "uvicorn[standard]"]
    try:
        subprocess.check_call(cmd)
        print("  -> OK")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  -> FAILED ({e})")
        return False


def main():
    explicit = sys.argv[1] if len(sys.argv) > 1 else None
    if explicit:
        targets = [explicit]
    else:
        targets = _find_fusion_python()

    if not targets:
        print("Could not auto-discover Fusion 360's Python.")
        print("Re-run with the explicit path, e.g.:")
        print('  python install_for_fusion.py "C:/path/to/Fusion/Python/python.exe"')
        sys.exit(1)

    ok = False
    for t in targets:
        if _install(t):
            ok = True
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
