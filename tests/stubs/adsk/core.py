"""adsk.core stub submodule."""

from .fusion import _Obj, Design  # noqa: F401


class Point3D:
    @staticmethod
    def create(x, y, z):
        return _Obj(x=x, y=y, z=z)


class ValueInput:
    @staticmethod
    def createByReal(v):
        return _Obj(value=v, kind="real")
    @staticmethod
    def createByString(s):
        return _Obj(value=s, kind="string")


class CommandCreatedEventHandler:
    @staticmethod
    def create(fn):
        return _Obj()


class Application:
    _app = None
    @staticmethod
    def get():
        if Application._app is None:
            Application._app = _Obj(
                activeProduct=Design(),
                activeDocument=_Obj(name="TestDoc", dataFile=None,
                                  documentType="FusionDesignDocumentType"),
                materialLibraries=[],
                userInterface=_Obj(messageBox=lambda m: None),
            )
        return Application._app
