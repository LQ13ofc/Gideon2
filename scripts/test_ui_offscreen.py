#!/usr/bin/env python3
"""This test executes only inside a private offscreen bwrap namespace."""
import argparse,json,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'app'))
from PySide6.QtGui import QGuiApplication,QAccessible
from PySide6.QtCore import QObject,Qt,QCoreApplication,QEvent,QPointF
from PySide6.QtTest import QTest
from main import create
parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--artifacts',required=True);parser.add_argument('--phase',choices=['voice','cancel','reconnect','timeout'],required=True);args=parser.parse_args()
app=QGuiApplication(sys.argv);QAccessible.setActive(True);bridge,engine=create(app,args.root);window=engine.rootObjects()[0];checks=[];trace=[];deltas=[]
bridge.changed.connect(lambda:deltas.append((bridge.state,bridge.subtitle,bridge.result)))
def check(name,value):
    if not value:raise AssertionError(name)
    checks.append(name)
def wait(condition,seconds=40):
    until=time.monotonic()+seconds
    while not condition():
        if time.monotonic()>until:raise TimeoutError((bridge.state,bridge.diagnostic))
        if not trace or trace[-1]!=bridge.state:trace.append(bridge.state)
        QTest.qWait(15)
wait(lambda:bridge.connected,5)
check('actual Core connection',bridge.connected)
button=window.findChild(QObject,'cancelButton');subtitle=window.findChild(QObject,'subtitle');inputbox=window.findChild(QObject,'textInput')
check('accessible cancel name',QAccessible.queryAccessibleInterface(button).text(QAccessible.Text.Name)=='Cancelar sessão')
window.setProperty('width',640);window.setProperty('height',520);QTest.qWait(100)
check('minimum layout size respected',window.property('width')>=480 and window.property('height')>=420)
if args.phase=='voice':
    wait(lambda:bridge.partial)
    check('partial is actual Core subtitle',subtitle.property('text')==bridge.subtitle and bridge.partial)
    check('cancel enabled during live voice',button.property('enabled'))
    button.forceActiveFocus();check('keyboard focus works',button.property('activeFocus'))
    wait(lambda:bridge.snapshot.get('speech_status')=='completed')
    check('final voice text and verified result rendered',not bridge.partial and 'brave' in bridge.subtitle.lower() and 'process verified' in bridge.result)
    check('UI observes actual virtual PCM',bridge.snapshot['speech']['samples']>0)
    check('cancel disabled after session',not button.property('enabled') and not bridge.sessionId)
    image=window.grabWindow();check('HiDPI offscreen rendering',image.width()==1280 and image.height()==1040);image.save(str(Path(args.artifacts)/'ui.png'))
    window.setProperty('width',window.property('minimumWidth'));window.setProperty('height',window.property('minimumHeight'));QTest.qWait(100)
    column=window.contentItem().childItems()[0];outside=[]
    for item in column.childItems():
        if not item.isVisible():continue
        point=item.mapToItem(window.contentItem(),QPointF(0,0))
        if point.x()<-0.5 or point.y()<-0.5 or point.x()+item.width()>window.width()+0.5 or point.y()+item.height()>window.height()+0.5:outside.append({'class':item.metaObject().className(),'y':point.y(),'height':item.height()})
    check('all visible rows fit minimum viewport '+json.dumps(outside),not outside)
    check('transcript viewport retains readable minimum height',window.findChild(QObject,'transcriptViewport').property('height')>=48)
    changes=len(deltas);QTest.qWait(1200);check('identical snapshots do not emit UI deltas',len(deltas)==changes)
    check('unsupported text control stays disabled',not inputbox.property('enabled'))
elif args.phase=='cancel':
    wait(lambda:bridge.partial);original=bridge.sessionId
    check('u64 session stays string',isinstance(original,str) and int(original)>0)
    button.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.state=='idle',5)
    check('keyboard cancel reaches actual Core',any(e['kind']=='cancelled' and str(e['session_id'])==original for e in bridge.snapshot['events']))
    check('cancel revokes subtitle and result',not bridge.subtitle and not bridge.result)
else:
    # Outer fixture controller kills/restarts Core. Observe offline, then one new server.
    Path(args.artifacts,'connected').touch();wait(lambda:not bridge.connected,10)
    check('offline clears stale session/subtitle and blocks cancel',not bridge.sessionId and not bridge.subtitle and not button.property('enabled'))
    Path(args.artifacts,'offline').touch();wait(lambda:bridge.connected,10)
    check('automatic reconnect to real restarted Core',bridge.state=='idle')
    wait(lambda:bridge.textAvailable,5)
    inputbox.forceActiveFocus();inputbox.setProperty('text','open brave');QTest.keyClick(window,Qt.Key.Key_Return)
    wait(lambda:bool(bridge.result),5)
    check('text uses actual shared sandbox executor',bridge.snapshot['transcript']['source']=='user_text' and 'process verified' in bridge.result)
    check('new server sequence resets safely',bridge.snapshot['sequence']>0)
print(json.dumps({'phase':args.phase,'passed':len(checks),'failed':0,'ignored':0,'checks':checks,'state_trace':trace}),flush=True)
bridge.poll.stop();bridge.retry.stop();bridge.timeout.stop();bridge.socket.close()

window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
del engine
del bridge
