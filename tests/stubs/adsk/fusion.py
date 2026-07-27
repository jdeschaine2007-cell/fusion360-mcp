"""adsk.fusion stub submodule."""

class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
    def __repr__(self):
        return f"<adsk-stub {type(self).__name__}>"


class Profile:
    def __init__(self, idx):
        self.idx = idx


class Sketch:
    def __init__(self):
        self.profiles = _Obj(item=lambda i: Profile(i))
        self.sketchCurves = _Obj(
            sketchLines=_Obj(addTwoPointRectangle=lambda a, b: "rect"),
            sketchCircles=_Obj(addByCenterRadius=lambda c, r: "circ"),
            sketchArcs=_Obj(addByCenterStartSweep=lambda *a: _Obj(
                endSketchPoint=_Obj(), startSketchPoint=_Obj())))


class ExtrudeFeatures:
    last = None
    def addSimple(self, profile, distance, op):
        ExtrudeFeatures.last = ("extrude", profile, distance.value, op)


class RevolveFeatures:
    last = None
    def createInput(self, profile, axis, op):
        return _Obj()
    def add(self, inp):
        RevolveFeatures.last = ("revolve",)


class Features:
    def __init__(self):
        self.extrudeFeatures = ExtrudeFeatures()
        self.revolveFeatures = RevolveFeatures()


class RootComponent:
    def __init__(self):
        self.xYConstructionPlane = "XY"
        self.yZConstructionPlane = "YZ"
        self.xZConstructionPlane = "XZ"
        self.sketches = _Obj(add=lambda p: Sketch())
        self.features = Features()
        self.userParameters = _Obj(
            itemByName=lambda n: None,
            add=lambda *a: _Obj(name=a[0], expression=a[1]))
        self.bRepBodies = _Obj(count=0)
        self.occurrences = _Obj(count=0)
        self.bodies = _Obj(count=0)
        self.name = "Root"


class Design:
    @staticmethod
    def cast(obj):
        return obj if isinstance(obj, Design) else Design()
    def __init__(self):
        self.rootComponent = RootComponent()
        self.activeComponent = RootComponent()
        self.allParameters = []
        self.unitsManager = _Obj(defaultLengthUnits="mm")
        self.name = "Design"


class FeatureOperations:
    NewBodyFeatureOperation = "new_body"
    CutFeatureOperation = "cut"
