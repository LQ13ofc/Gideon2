#!/usr/bin/env python3
"""Launch the thin QML client against an explicit private Core root."""
import argparse,os,sys
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtQml import QQmlApplicationEngine,qmlRegisterType
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bridge import Bridge
from uisettings import UiSettings
from visual import RoundedImage
qmlRegisterType(RoundedImage,"Gideon.Visual",1,0,"RoundedImage")

def create(app,root):
    bridge=Bridge(root);ui=UiSettings(bridge,root,parent=bridge);engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('core',bridge);engine.rootContext().setContextProperty('ui',ui);engine.load(str(Path(__file__).with_name('Main.qml')))
    if not engine.rootObjects():raise RuntimeError('QML load failed')
    if not isinstance(engine.rootObjects()[0],QQuickWindow):raise RuntimeError('Quick window required')
    return bridge,engine
if __name__=='__main__':
    # The client ships its own look: never inherit a desktop style (e.g. org.kde.desktop) that is not bundled.
    os.environ['QT_QUICK_CONTROLS_STYLE']='Basic'
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    if not args.root.is_absolute():parser.error('absolute private root required')
    app=QGuiApplication(sys.argv);bridge,engine=create(app,args.root);code=app.exec()
    for window in engine.rootObjects():window.close();window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    del engine
    del bridge
    sys.exit(code)
