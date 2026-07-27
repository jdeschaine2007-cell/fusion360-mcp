"""adsk stub package — headless stand-in for Fusion's adsk API.

ONLY used by tests/test_fusion_mcp_addin.py (inserted onto sys.path).
NOT part of the shipped add-in.

The real adsk package exposes `adsk.core` and `adsk.fusion` as submodules;
we mirror that layout so `import adsk.core` / `import adsk.fusion` work.
"""

from .core import Point3D, ValueInput, CommandCreatedEventHandler, Application
from .fusion import Design, FeatureOperations
