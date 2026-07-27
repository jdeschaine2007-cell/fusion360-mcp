"""vs.py stub — headless stand-in for Vectorworks' Python module.

ONLY used by tests/test_fusion_mcp_addin.py (inserted onto sys.path).
Records calls so tests can assert the geometry path ran.
"""

# Call log so tests can verify which vs functions executed.
CALLS = []


def _log(name, *args):
    CALLS.append((name, args))


def ClosePath():
    _log("ClosePath")


def MoveTo(x, y):
    _log("MoveTo", x, y)


def LineTo(x, y):
    _log("LineTo", x, y)


def LNewObj():
    _log("LNewObj")
    return ("obj", len(CALLS))


def CreateCircleN(cx, cy, r):
    _log("CreateCircleN", cx, cy, r)
    return ("circle", len(CALLS))


def CreateExtrude(h, d, a, b):
    _log("CreateExtrude", h, d, a, b)
    return ("extrude", len(CALLS))


def CreateRevolve(h, a1, a2, a3):
    _log("CreateRevolve", h, a1, a2, a3)
    return ("revolve", len(CALLS))


def SetObjBoolType(h, t):
    _log("SetObjBoolType", h, t)


def SetRecord(h, name):
    _log("SetRecord", h, name)


def SetVar(name, val):
    _log("SetVar", name, val)


def Layer(name, kind):
    _log("Layer", name, kind)


def ForEachObject(fn, crit):
    _log("ForEachObject", crit)
    # No selection in the stub, so fn is never called.


def GetDocName():
    return "VW_TestDoc"


def NumObjs(crit):
    return 3


def GetUnits():
    return "mm"
