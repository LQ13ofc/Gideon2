#!/usr/bin/env python3
"""This test executes only inside a private offscreen bwrap namespace.

Phase protocol (each phase writes one empty marker file per checkpoint into --artifacts, in order; the gate waits for them):
  models phase (C2, needs a real Core with llm_engine installed, approved and enabled, and a gate-written fake-ports.json):
    fake-ports.json  {"ok": port, "fail": port, "text": port}: loopback fake llama.cpp-style servers the gate starts;
                     "ok" answers healthy selftests, "fail" answers 503, "text" answers without tool calls.
    models-ready         Modelos LLM offered, tabs named, badges only certified as Certificado, Local filter works
    custom-added         fake-ok saved through the custom form and listed as Personalizado
    model-active         Usar este modelo ran configure -> selftest -> mark good; status Disponível
    selftest-rolled-back fake-fail failed the selftest; the Core restored the last good model and the UI says so
    status-unavailable   fake-text (declared without tool use) reported INDISPONÍVEL, or its failed test rolled back
    custom-removed       fake-fail removed after confirmation (Cancel is the default and keeps it)
  agent phase (C3 UI, needs a real Core with llm_engine running, started with --home and --agent-synthetic, and the
    scripted fake LLM in the plugin settings (agent_script, written by verify_c3_agent.py): step 1 proposes
    synth_counter_inc with epoch 1 (the app's first epoch), step 2 answers in text):
    agent-ready     Agente offered while the engine runs; Iniciar disabled with a blank goal, enabled with a goal
    agent-awaiting  the run reached awaiting_approval; Autorizar is on screen with the run's proposal and Abortar is enabled
    agent-done      after Autorizar the run reached done; the final answer is shown as PlainText and Iniciar is enabled again
  perception phase (C4 UI, needs a real Core with the six C4 plugins installed, approved and enabled, started with
    --agent-synthetic; screen_observe, computer_control, audio_advanced, mic_advanced, camera_gesture and display_manipulate).
    Expected setup: each plugin runs its synthetic backend and display_manipulate answers its UNSUPPORTED status. scripts/verify_c4.py
    starts this phase on a Core with the six plugins installed, approved and enabled.
    perception-ready        Percepção offered; every synthetic card reads SINTÉTICO — sem hardware real, display reads UNSUPPORTED,
                            the microphone and camera indicators are on the page
    perception-captured     Capturar went through the Core and its result is shown as PlainText from the checked output
    perception-unsupported  Estado of display_manipulate shows UNSUPPORTED; the page ends with ui.png
  skills phase (S4 UI, needs a real Core with the skill engine and a fixture skill that is tested, approved and enabled, with its
    dependency plugin running; the gate also installs one file under <home>/skill-imports/fixture-note.gskill, and writes the
    scripted run so the Core asks for approval on one state-changing step). The phase clicks only the user's own decisions.
    skills-ready       Skills offered; the enabled fixture row reads 'Estado: habilitada'
    skills-validated   Validar of the manifest typed in the editor shows the Core answer as PlainText; the skill list does not change
    skills-draft       --llm yes: Gerar com LLM turns the typed description into a draft the Core created (state draft, never enabled);
                       --llm no: the button is disabled and the page says llm_engine is not running
    skills-awaiting    Executar started a run; the awaiting step shows Autorizar and Negar
    skills-run         after Autorizar the run state is done and shown as PlainText
    skills-import      the import preview of fixture-note shows publisher 'não verificado'; Instalar como rascunho is enabled only
                       with no findings, and clicking it installs a draft (it never enables anything); the page ends with ui.png
  connections phase (S5 UI, needs a real Core with the connection manager running and the fake servers of the gate (--connections-fake):
    at least one connected account with a granted read operation, and one account waiting for consent (pending_scopes).
    The phase clicks only Testar leitura and the user's own consent; it never adds an account, never revokes or removes one.
    connections-ready      Conexões offered; every account served by the fake shows 'SERVIDOR FALSO — sem credenciais reais'
    connections-read       Testar leitura of a connected account went through the Core; Última chamada is shown as PlainText
    connections-consented  the ticked pending scope was sent with Consentir escopos marcados; the Core lists it as granted
    The page ends with ui.png
  registry phase (S5 E3 UI, needs a real Core started with the github fake and one connected github account, with the visual fallback off; scripts/verify_e3_registry.py).
    The card 'Rotas' is on the Conexões page. The phase clicks Planejar and the visual switch (on, then off again: the user's own revocable choice);
    it never connects an account and never starts an agent run.
    registry-ready    Rotas offered; every purpose shows its chosen route (or none) and its candidates with reasons as PlainText; the fallback is off with a warning
    registry-plan     Planejar went through the Core (nothing executed) and its answer is shown; the bridge refuses an unknown purpose and a purpose with no visual route without a request
    registry-allowed  the switch turned the fallback on in the Core (visual_allowed lists create_issue); the card says ligado por você
    registry-revoked  the same switch turned it off again; the card says desligado; the page ends with ui.png
"""
import argparse,json,os,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'app'))
from PySide6.QtGui import QGuiApplication,QAccessible
from PySide6.QtCore import QObject,Qt,QCoreApplication,QEvent,QPointF
from PySide6.QtTest import QTest
# The first-run guide (B1) would cover the pages these phases drive: they run with it suppressed (read by uisettings.py).
os.environ['GIDEON_UI_NO_ONBOARDING']='1'
from main import create
parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--artifacts',required=True);parser.add_argument('--llm',choices=['yes','no'],default='no',help='skills phase: yes = llm_engine runs (Gerar com LLM is used), no = plugin absent (the button must say so)');parser.add_argument('--phase',choices=['voice','cancel','reconnect','timeout','preferences','safe_mode','pack','feedback','hub','hub_quarantine','design','permissions','staging','lifecycle','plugins','chat','models','agent','perception','skills','connections','registry'],required=True);args=parser.parse_args()
app=QGuiApplication(sys.argv);QAccessible.setActive(True);bridge,engine=create(app,args.root);window=engine.rootObjects()[0];checks=[];trace=[];deltas=[];metrics={}
bridge.changed.connect(lambda:deltas.append((bridge.state,bridge.subtitle,bridge.result)))
def check(name,value):
    if not value:raise AssertionError(name)
    checks.append(name)
def wait(condition,seconds=40):
    until=time.monotonic()+seconds
    while not condition():
        if time.monotonic()>until:raise TimeoutError((bridge.state,bridge.diagnostic,bridge.results.get('connections'),bridge.pending,bridge.error))
        if not trace or trace[-1]!=bridge.state:trace.append(bridge.state)
        QTest.qWait(15)
wait(lambda:bridge.connected,5)
check('actual Core connection',bridge.connected)
button=window.findChild(QObject,'cancelButton');subtitle=window.findChild(QObject,'subtitle');inputbox=window.findChild(QObject,'textInput')
check('accessible cancel name',QAccessible.queryAccessibleInterface(button).text(QAccessible.Text.Name)=='Cancelar sessão')
window.setProperty('width',640);window.setProperty('height',520);QTest.qWait(100)
minimum=(window.property('minimumWidth'),window.property('minimumHeight'));check('QML minimum is 480x520',minimum==(480,520))
check('minimum layout size respected',window.property('width')>=minimum[0] and window.property('height')>=minimum[1])
def visual_item(name):
    stack=[window.contentItem()]
    while stack:
        current=stack.pop()
        if current.objectName()==name:return current
        stack.extend(current.childItems())
    raise AssertionError('missing visual item '+name)
def open_page(page_id,tab):
    # Opens a page as a user does: the tab (tab_<tab>) when its sub-tab is not in the bar, then the sub-tab (subtab_<page>).
    sub=next((i for i in visual_items() if i.objectName()=='subtab_'+page_id),None)
    if sub is None or not sub.isVisible():
        tab_item=visual_item('tab_'+tab);tab_item.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space);QTest.qWait(60)
        sub=visual_item('subtab_'+page_id)
    sub.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:window.property('pageId')==page_id,3)
def mouse_click(item):
    # A real click at the centre of the item (the item must be in the visible part of its page; list rows scroll into view on focus).
    point=item.mapToItem(window.contentItem(),QPointF(item.width()/2,item.height()/2))
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point.toPoint())
    QTest.qWait(30)
def texts_of(item):
    # Every item under item that carries a text property (a layout has none of its own).
    out=[];stack=[item]
    while stack:
        current=stack.pop()
        if current.property('text') is not None:out.append(current)
        stack.extend(current.childItems())
    return out
def choose_segment(label):
    # A segment of a Segmented control (keyboard focusable, Space picks it): found by its exact label text.
    label_item=next(i for i in visual_items() if i.property('text')==label and i.property('visible') is True)
    segment=label_item
    while segment is not None and segment.property('activeFocusOnTab') is not True:segment=segment.parentItem()
    if segment is None:raise AssertionError('no segment '+label)
    segment.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space);QTest.qWait(60)
def visual_items():
    stack=[window.contentItem()];found=[]
    while stack:
        current=stack.pop();found.append(current);stack.extend(current.childItems())
    return found
if args.phase=='staging':
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('native S1 before payload staging',bridge.resultVerified and bridge.snapshot['speech']['samples']>0)
    open_page('plugins','extensoes')
    wait(lambda:window.property('pageId')=='plugins',3)
    Path(args.artifacts,'ready').touch();wait(lambda:bridge.hubImportActive,10)
    check('Core import progress reaches real Qt',bridge.hubImportDescription.startswith('Preparando benign_fixture:'))
    abort=visual_item('abortHubImportButton');abort.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:not bridge.hubImportActive,5)
    check('actual Qt cancel clears Core import',bridge.hubApprovalResult=='Importação cancelada')
    Path(args.artifacts,'cancelled').touch();wait(lambda:bridge.hubEntries[0].get('payload_staged'),10)
    check('verified staging is never installed',bridge.hubEntries[0]['status']=='not_installed' and not bridge.snapshot['hub']['publisher_verified'])
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'));Path(args.artifacts,'staged').touch()
    wait(lambda:not bridge.connected,10);Path(args.artifacts,'offline').touch()
    wait(lambda:bridge.connected,10);wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('restart rechecks persisted payload and approval',bridge.hubEntries[0]['payload_staged'] and bridge.hubEntries[0]['permissions_approved'])
    check('native S1 after staging restart',bridge.resultVerified and bridge.snapshot['transcript']['source']=='voice' and bridge.snapshot['speech']['samples']>0)
elif args.phase=='lifecycle':
    open_page('plugins','extensoes')
    wait(lambda:window.property('pageId')=='plugins',3)
    Path(args.artifacts,'ready').touch()
    def fixture_record():return next((p for p in bridge.hubInstalled if p.get('plugin_id')=='benign_fixture'),None)
    wait(lambda:fixture_record() is not None,50)
    record=fixture_record()
    check('Core ledger shows fixture installed with runtime disabled',record['state']=='installed' and record['runtime']=='disabled' and record['previous'] is None)
    check('status label shows installed and disabled',visual_item('status_benign_fixture').property('text').startswith('Instalado · desativado (sem execução)'))
    check('install control unavailable once installed',not visual_item('install_benign_fixture').property('enabled'))
    check('rollback unavailable without previous version',not visual_item('rollback_benign_fixture').property('enabled'))
    check('remove control available for installed plugin',visual_item('remove_benign_fixture').property('enabled'))
    Path(args.artifacts,'installed').touch()
    wait(lambda:not bridge.connected,15);Path(args.artifacts,'offline').touch()
    wait(lambda:bridge.connected,15);wait(lambda:fixture_record() is not None,15)
    record=fixture_record()
    check('restart preserves installed disabled record',record['state']=='installed' and record['runtime']=='disabled')
    check('restarted UI keeps disabled status',visual_item('status_benign_fixture').property('text').startswith('Instalado · desativado (sem execução)'))
    remove=visual_item('remove_benign_fixture');remove.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    confirm=window.findChild(QObject,'removeConfirm');wait(lambda:confirm.property('visible'),3)
    check('remove requires confirmation and does not act yet',fixture_record() is not None)
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'));confirm.close();QTest.qWait(50)
    check('cancelled removal keeps installed record',fixture_record() is not None)
    remove=visual_item('remove_benign_fixture');remove.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:confirm.property('visible'),3);confirm.accept()
    wait(lambda:fixture_record() is None and visual_item('hubLifecycleResult').property('text')!='Removendo no Core',15)
    check('Qt removal confirmed reaches Core ledger',fixture_record() is None)
    check('hub result label shows Plugin removido',visual_item('hubLifecycleResult').property('text')=='Plugin removido')
elif args.phase=='models':
    # Gate protocol (C2 UI): markers and fake-ports.json are documented in the module docstring.
    ports=json.loads(Path(args.artifacts,'fake-ports.json').read_text(encoding='utf-8'))
    wait(lambda:bridge.modelsAvailable,50)
    check('Modelos LLM offered only because llm_engine.models runs',bridge.modelsAvailable)
    open_page('modelos','extensoes');wait(lambda:window.property('pageId')=='modelos',3)
    check('models panel visible on its page',visual_item('modelsPanel').property('visible'))
    check('recommended tab has its accessible name',QAccessible.queryAccessibleInterface(visual_item('modelsTabRecommended')).text(QAccessible.Text.Name)=='Aba Recomendados')
    check('only certified models read Certificado',all((m['certification']['state']=='certified')==(bridge.certificationBadge(m['certification']['state'])=='Certificado') for m in bridge.modelsRecommended))
    def has_item(name):
        stack=[window.contentItem()]
        while stack:
            current=stack.pop()
            if current.objectName()==name:return True
            stack.extend(current.childItems())
        return False
    visual_item('modelsFilter').setProperty('currentIndex',1);QTest.qWait(50)
    check('Local filter hides cloud recommendations',all(not has_item('model_'+m['id']) for m in bridge.modelsRecommended if m['kind']=='cloud'))
    visual_item('modelsFilter').setProperty('currentIndex',0)
    Path(args.artifacts,'models-ready').touch()
    # The user opens the Personalizados part first (the form and the custom list are that part's); the page starts on Modelo atual.
    choose_segment('Personalizados')
    visual_item('modelsTabs').setProperty('currentIndex',1);QTest.qWait(50)
    def save_custom(label,port,tool='unknown'):
        visual_item('customProvider').setProperty('currentIndex',0);visual_item('customModelId').setProperty('text',label)
        visual_item('customPort').setProperty('value',port);visual_item('customToolUse').setProperty('currentIndex',{'unknown':0,'supported':1,'unsupported':2}[tool])
        wait(lambda:not bridge.modelsBusy,40)  # the save button is disabled while a model request runs
        save=visual_item('saveCustomButton');save.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
        wait(lambda:any(m['label']==label for m in bridge.modelsCustom),30);QTest.qWait(80)  # the new row is scrolled into view after the list updates
    def custom_id(label):return next(m['id'] for m in bridge.modelsCustom if m['label']==label)
    def select_row(item):
        # A list row takes keyboard focus first (Reveal.js scrolls it into view of the page), then the user's click lands on it.
        item.forceActiveFocus();QTest.qWait(30);mouse_click(item)
    def use(label):
        select_row(visual_item('model_'+custom_id(label)))
        before=bridge.modelsResult;button=visual_item('useModelButton');button.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
        wait(lambda:not bridge.modelsBusy and bridge.modelsResult!=before,90)
    save_custom('fake-ok',ports['ok'])
    check('custom model saved through the Core and listed as Personalizado',any(m['label']=='fake-ok' for m in bridge.modelsCustom))
    Path(args.artifacts,'custom-added').touch()
    use('fake-ok')
    check('use runs configure, selftest and mark good',bridge.modelsResult.startswith('Modelo ativo: fake-ok'))
    check('status line reads Disponível for the tested model',bridge.modelsStatus=='Disponível' and bridge.llmConfig.get('model')=='fake-ok')
    Path(args.artifacts,'model-active').touch()
    save_custom('fake-fail',ports['fail'])
    use('fake-fail')
    check('failed selftest is reported and the last good model is restored',"configuração anterior restaurada" in bridge.modelsResult and bridge.llmConfig.get('model')=='fake-ok')
    Path(args.artifacts,'selftest-rolled-back').touch()
    save_custom('fake-text',ports.get('text',ports['ok']),tool='unsupported')
    use('fake-text')
    if bridge.modelsResult.startswith('Modelo ativo: fake-text'):check('text-only model shows INDISPONÍVEL for tool use',bridge.modelsStatus=='INDISPONÍVEL: tool_use não suportado')
    else:check('text-only model failed its test and was rolled back',"configuração anterior restaurada" in bridge.modelsResult)
    Path(args.artifacts,'status-unavailable').touch()
    select_row(visual_item('model_'+custom_id('fake-fail')))
    remove=visual_item('removeCustomButton');remove.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    confirm=window.findChild(QObject,'removeCustomConfirm');wait(lambda:confirm.property('visible'),3)
    confirm.close();QTest.qWait(50)
    check('cancelled removal keeps the custom model',any(m['label']=='fake-fail' for m in bridge.modelsCustom))
    remove=visual_item('removeCustomButton');remove.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:confirm.property('visible'),3);visual_item('confirmRemoveCustomButton').forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:not any(m['label']=='fake-fail' for m in bridge.modelsCustom),30)
    check('confirmed removal deletes it through the Core',not any(m['label']=='fake-fail' for m in bridge.modelsCustom))
    Path(args.artifacts,'custom-removed').touch()
elif args.phase=='chat':
    # Gate protocol (C1 UI): the gate starts a real Core with llm_engine installed, approved and enabled, configured with a
    # fake OpenAI-compatible provider and a fake key written by the gate (this phase never sees or types a key).
    # Message prefixes understood by the fake provider:
    #   (none)  - SSE partials that grow, then a final text
    #   tool:open_app - proposes open_app (a state change, so it waits for Autorizar); the fake matches this prefix (fake_llm_server.py PREFIXES)
    #   slow:   - keeps the reply open until the Core cancels it
    # Markers written to --artifacts, in order:
    #   chat-ready   - Conversa offered by the running engine, input and send present
    #   tool-pending - proposal card with Autorizar and Negar is on screen
    #   tool-done    - after Autorizar the proposal reached executed
    #   cancelled    - a slow reply was cancelled from the UI and ended as cancelled
    #   config-saved - Motor LLM saved through the Core and the Core revision moved
    wait(lambda:bridge.chatAvailable,50)
    check('Conversa offered only because llm_engine chat runs',bridge.chatAvailable)
    open_page('conversa','assistente');wait(lambda:window.property('pageId')=='conversa',3)
    check('Conversa page shows the chat panel',visual_item('chatPanel').property('visible'))
    field=visual_item('chatInput');send=visual_item('chatSend');cancel=visual_item('chatCancel')
    check('chat input and send present while idle',field.property('enabled') and not send.property('enabled'))
    Path(args.artifacts,'chat-ready').touch()
    def observe_until(condition,seconds,observed):
        until=time.monotonic()+seconds
        while not condition():
            if time.monotonic()>until:raise TimeoutError((bridge.chatState,bridge.chatResult))
            observed();QTest.qWait(15)
    def submit(text):
        field.forceActiveFocus();field.setProperty('text','')
        for character in text:QTest.keyClick(window,character)
        send.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    partials=[];states=[]
    def observe():
        if not states or states[-1]!=bridge.chatState:states.append(bridge.chatState)
        if bridge.chatPartial and (not partials or partials[-1]!=bridge.chatPartial):partials.append(bridge.chatPartial)
    # The bridge reads the Core snapshot once a second while no speech session runs, and the fake's echo finishes faster
    # than that, so growth is observed on a slow reply (one tick every 0.3 s). This reply is cancelled from the UI once two
    # partials were seen; the cancel path is checked again further down.
    submit('slow: Gideon mostra o texto parcial enquanto ele chega.')
    observe_until(lambda:len(partials)>=2 and bridge.chatState=='streaming',30,observe)
    check('partials grew while the reply streamed',len(partials[-1])>len(partials[0]))
    check('streaming state was observed',('streaming' in states))
    cancel.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    observe_until(lambda:bridge.chatState=='cancelled',30,observe)
    check('partial reply cancelled from the UI ends as cancelled',bridge.chatState=='cancelled')
    assistant_before=[m['role'] for m in bridge.chatMessages].count('assistant')
    submit('Oi, responda em uma frase.')
    observe_until(lambda:bridge.chatState=='done',40,observe)
    check('final assistant text is shown once',[m['role'] for m in bridge.chatMessages].count('assistant')==assistant_before+1 and bridge.chatMessages[-1]['text']!='')
    check('live bubble hidden once the final reply is shown',not visual_item('chatStreaming').property('visible'))
    submit('tool:open_app abra o navegador')
    observe_until(lambda:any(p['state']=='pending' for p in bridge.toolProposals),40,observe)
    pending=next(p for p in bridge.toolProposals if p['state']=='pending');pid=pending['proposal_id']
    check('tool proposal card offers Autorizar and Negar only while pending',visual_item('authorize_'+pid).property('visible') and visual_item('deny_'+pid).property('visible'))
    Path(args.artifacts,'tool-pending').touch()
    authorize=visual_item('authorize_'+pid);authorize.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    observe_until(lambda:next((p['state'] for p in bridge.toolProposals if p['proposal_id']==pid),'')=='executed',30,observe)
    check('authorized tool reaches executed with a sandbox receipt',next(p for p in bridge.toolProposals if p['proposal_id']==pid)['result'] is not None)
    check('decision buttons disappear after the decision',not visual_item('authorize_'+pid).property('visible'))
    Path(args.artifacts,'tool-done').touch()
    observe_until(lambda:bridge.chatState=='done',40,observe)
    submit('slow: responda devagar')
    observe_until(lambda:bridge.chatState in ('waiting','streaming'),20,observe)
    check('cancel enabled during slow reply',cancel.property('enabled'))
    cancel.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    observe_until(lambda:bridge.chatState=='cancelled',30,observe)
    check('cancel reaches the Core and ends the reply as cancelled',bridge.chatState=='cancelled' and not cancel.property('enabled'))
    Path(args.artifacts,'cancelled').touch()
    open_page('cfg_privacidade','configuracoes');wait(lambda:window.property('pageId')=='cfg_privacidade',3)
    llm_open=visual_item('llmOpenButton');llm_open.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    dialog=window.findChild(QObject,'llmDialog');wait(lambda:dialog.property('visible'),3)
    key=window.findChild(QObject,'llmKey')
    check('key field is empty and masked when Motor LLM opens',key.property('text')=='' and key.property('displayText')=='')
    saved_consent=bridge.llmConfig.get('cloud_consent')is True
    box=window.findChild(QObject,'llmConsent')
    check('cloud consent checkbox reflects the saved Core consent when Motor LLM opens',box.property('checked')==saved_consent)
    check('cloud consent warning stays visible next to the checkbox',window.findChild(QObject,'llmConsentWarning').property('visible'))
    check('key status shows only configured or not configured',window.findChild(QObject,'llmKeyStatus').property('text') in ('Chave configurada','Sem chave'))
    revision=bridge.llmRevision;save=window.findChild(QObject,'saveLlmConfigButton')
    check('save configuration offered once the form is loaded',save.property('enabled'))
    save.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.llmRevision!=revision,10)
    check('Core saved configuration and moved its revision',bridge.llmResult=='Configuração salva pelo Core')
    check('saving without touching the checkbox keeps the saved consent',bridge.llmConfig.get('cloud_consent')==saved_consent)
    Path(args.artifacts,'config-saved').touch()
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'))
    # Reopen, then a user click flips the box; saving sends the flipped value; a second round restores the saved one.
    def reopen_llm():
        # The form is a page part (Modelos LLM > Provedor e chaves), not a dialog: leaving the page and coming back reloads it from the Core.
        open_page('hoje','assistente');open_page('modelos','extensoes')
        reopened=window.findChild(QObject,'llmDialog');wait(lambda:reopened.property('visible'),3);return reopened
    dialog=reopen_llm()
    box=window.findChild(QObject,'llmConsent');check('reopened dialog reflects the Core consent again',box.property('checked')==saved_consent)
    box.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    check('user click flips the consent checkbox',box.property('checked')==(not saved_consent))
    revision=bridge.llmRevision;save=window.findChild(QObject,'saveLlmConfigButton')
    save.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.llmRevision!=revision,10)
    check('saving the flipped checkbox sends exactly that consent value',bridge.llmConfig.get('cloud_consent')==(not saved_consent))
    dialog=reopen_llm()
    box=window.findChild(QObject,'llmConsent');box.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    revision=bridge.llmRevision;save=window.findChild(QObject,'saveLlmConfigButton')
    save.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.llmRevision!=revision,10)
    check('original consent value restored after the round trip',bridge.llmConfig.get('cloud_consent')==saved_consent)
elif args.phase=='agent':
    # Gate protocol (C3 UI): see the module docstring. The phase types a goal, presses Iniciar and only clicks the user's own decision.
    wait(lambda:bridge.chatAvailable,50)
    # The agent is its own sub-tab (Assistente > Agente) since the redesign.
    open_page('agente','assistente');wait(lambda:window.property('pageId')=='agente',3)
    check('Agente section visible only while the engine runs',visual_item('agentPanel').property('visible'))
    goal=visual_item('agentGoal');start=visual_item('agentStart');abort=visual_item('agentAbort')
    check('Iniciar disabled with a blank goal',not start.property('enabled'))
    goal.forceActiveFocus();goal.setProperty('text','Incremente o contador uma vez');QTest.qWait(20)
    check('Iniciar enabled with a goal while idle',start.property('enabled') and not abort.property('enabled'))
    Path(args.artifacts,'agent-ready').touch()
    start.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.agentState=='awaiting_approval',60)
    check('banner names the approval state',visual_item('agentBanner').property('text')==bridge.agentStateLabel)
    pending=next(p for p in bridge.toolProposals if p['state']=='pending' and 'run_id' in p)
    pid=pending['proposal_id']
    check('proposal carries the run and step it belongs to',pending['step']>=1 and isinstance(pending['run_id'],str) and pending['run_id']!='')
    check('Autorizar on screen for the run proposal and Abortar enabled',visual_item('authorize_'+pid).property('visible') and abort.property('enabled'))
    Path(args.artifacts,'agent-awaiting').touch()
    visual_item('authorize_'+pid).forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.agentState=='done',90)
    answer=visual_item('agentAnswer')
    from PySide6.QtQml import QQmlEngine as _E,QQmlExpression as _X
    # textFormat is a QML enum PySide cannot convert: the comparison runs inside QML.
    from PySide6.QtQml import QQmlEngine,QQmlExpression
    expression=QQmlExpression(QQmlEngine.contextForObject(answer),answer,'textFormat === Text.PlainText');plain=expression.evaluate();plain=plain[0] if isinstance(plain,tuple) else plain
    check('final answer shown as PlainText',answer.property('visible') and answer.property('text')==bridge.agentAnswer and plain is True and not expression.hasError())
    check('Iniciar enabled again after the run is done',start.property('enabled'))
    Path(args.artifacts,'agent-done').touch()
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'))
elif args.phase=='perception':
    # Gate protocol (C4 UI): see the module docstring. The phase only clicks the read buttons; it never types a goal, opts in a camera or starts a recording.
    C4_PLUGINS=('screen_observe','computer_control','audio_advanced','mic_advanced','camera_gesture','display_manipulate')
    wait(lambda:bridge.perceptionAvailable,50)
    open_page('percepcao','extensoes');wait(lambda:window.property('pageId')=='percepcao',3)
    check('perception panel visible on its page',visual_item('perceptionPanel').property('visible'))
    check('every synthetic card is labelled SINTÉTICO — sem hardware real',all(visual_item('perceptionBadge_'+p).property('text')=='SINTÉTICO — sem hardware real' for p in C4_PLUGINS[:-1]))
    check('display card reads UNSUPPORTED',visual_item('perceptionBadge_display_manipulate').property('text')=='UNSUPPORTED')
    check('privacy indicators are on the page',visual_item('micIndicator').property('visible') and visual_item('cameraIndicator').property('visible'))
    Path(args.artifacts,'perception-ready').touch()
    capture=visual_item('perception_screen_observe.capture');capture.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.perceptionResult.startswith('backend: sintético') and not bridge.perceptionBusy,40)
    result=visual_item('perceptionResult')
    from PySide6.QtQml import QQmlEngine,QQmlExpression
    expression=QQmlExpression(QQmlEngine.contextForObject(result),result,'textFormat === Text.PlainText');plain=expression.evaluate();plain=plain[0] if isinstance(plain,tuple) else plain
    check('capture result shown as PlainText from the checked output',result.property('text')==bridge.perceptionResult and plain is True and not expression.hasError())
    Path(args.artifacts,'perception-captured').touch()
    status=visual_item('perception_display_manipulate.status');status.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:'UNSUPPORTED' in bridge.perceptionResult and not bridge.perceptionBusy,40)
    check('display status shows UNSUPPORTED through the Core',visual_item('perceptionResult').property('text').count('UNSUPPORTED')==1)
    Path(args.artifacts,'perception-unsupported').touch()
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'))
elif args.phase=='skills':
    # Gate protocol (S4 UI): see the module docstring. The phase types the manifest text it is given, and clicks only Validar, Executar, the step decision and Instalar como rascunho.
    from PySide6.QtQml import QQmlEngine,QQmlExpression
    wait(lambda:bridge.skillsAvailable,50)
    open_page('skills','extensoes');wait(lambda:window.property('pageId')=='skills',3)
    check('skills panel visible on its page',visual_item('skillsPanel').property('visible'))
    enabled=next((s for s in bridge.skillsItems if s['state']=='enabled'),None)
    check('enabled fixture row reads habilitada',enabled is not None and visual_item('skillState_'+enabled['id']+'_'+enabled['version']).property('text').startswith('Estado: habilitada'))
    Path(args.artifacts,'skills-ready').touch()
    # The Criar part holds the manifest editor and the Gerar com LLM card; the page starts on Minhas, so the user opens Criar first.
    choose_segment('Criar')
    before=[(s['id'],s['version'],s['state']) for s in bridge.skillsItems]
    manifest=visual_item('skillManifest');manifest.forceActiveFocus();manifest.setProperty('text','{"schema_version": 2}');QTest.qWait(20)
    validate=visual_item('skillValidate');validate.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.skillsResult!='' and not bridge.skillsBusy,40)
    result=visual_item('skillsResult');expression=QQmlExpression(QQmlEngine.contextForObject(result),result,'textFormat === Text.PlainText');plain=expression.evaluate();plain=plain[0] if isinstance(plain,tuple) else plain
    check('validation answer shown as PlainText from the Core',result.property('text')==bridge.skillsResult and plain is True and not expression.hasError())
    check('validation wrote nothing: the skill list is unchanged',[(s['id'],s['version'],s['state']) for s in bridge.skillsItems]==before)
    Path(args.artifacts,'skills-validated').touch()
    if args.llm=='yes':
        check('Gerar com LLM is offered while llm_engine runs',bridge.skillLlmAvailable)
        description=visual_item('skillDescription');description.forceActiveFocus();description.setProperty('text','Lista a hora atual');QTest.qWait(20)
        draft=visual_item('skillDraftWithLlm');check('Gerar com LLM enabled once a description is typed',draft.property('enabled'));draft.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
        wait(lambda:bool(bridge.skillDraftOutput.get('draft_id')) and not bridge.skillsBusy,90)
        output=bridge.skillDraftOutput
        draft_id=output['draft_id'].split('@')[0]
        check('LLM draft created by the Core as a draft (never enabled, never active)',output['state']=='draft' and any(s['id']==draft_id and s['state']=='draft' and s['source']=='llm_draft' and s['active'] is False for s in bridge.skillsItems))
        header=None;stack=[window.contentItem()]
        while stack and header is None:
            current=stack.pop()
            if str(current.property('text') or '').startswith('Rascunho '+output['draft_id']):header=current
            stack.extend(current.childItems())
        check('LLM draft output shown as PlainText from the Core answer',header is not None and header.property('visible'))
        expression=QQmlExpression(QQmlEngine.contextForObject(header),header,'textFormat === Text.PlainText');plain=expression.evaluate();plain=plain[0] if isinstance(plain,tuple) else plain
        check('draft header is PlainText',plain is True and not expression.hasError())
    else:
        check('Gerar com LLM says llm_engine is not running and stays disabled',not bridge.skillLlmAvailable and visual_item('skillLlmUnavailable').property('visible') and not visual_item('skillDraftWithLlm').property('enabled'))
    Path(args.artifacts,'skills-draft').touch()
    choose_segment('Minhas')
    run=visual_item('skillRun_'+enabled['id']);run.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.skillCurrentRun.get('state')=='awaiting_approval',60)
    awaiting=next(s for s in bridge.skillCurrentRun['steps'] if s['state']=='awaiting_approval')
    # The step buttons follow the Core state through the page's delegate: give the QML side a few event-loop turns to catch up.
    wait(lambda:visual_item('skillAuthorize_'+awaiting['id']).property('visible') and visual_item('skillDeny_'+awaiting['id']).property('visible'),5)
    check('awaiting step offers Autorizar and Negar',visual_item('skillAuthorize_'+awaiting['id']).property('visible') and visual_item('skillDeny_'+awaiting['id']).property('visible'))
    Path(args.artifacts,'skills-awaiting').touch()
    visual_item('skillAuthorize_'+awaiting['id']).forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    # The Core drops the run block when a run ends (docs/S4.md D2): the outcome is the newest Histórico row.
    wait(lambda:not bridge.skillCurrentRun.get('run_id') and bool(bridge.skillHistory) and bridge.skillHistory[-1]['state'] in ('done','failed','cancelled','rolled_back'),90)
    check('run reached done after the user decision',bridge.skillHistory[-1]['state']=='done' and bridge.skillHistory[-1]['skill']==enabled['id'])
    runline=visual_item('skillHistory_'+str(len(bridge.skillHistory)-1));expression=QQmlExpression(QQmlEngine.contextForObject(runline),runline,'textFormat === Text.PlainText');plain=expression.evaluate();plain=plain[0] if isinstance(plain,tuple) else plain
    check('run outcome shown as PlainText in Histórico',plain is True and not expression.hasError() and 'concluída' in runline.property('text'))
    Path(args.artifacts,'skills-run').touch()
    choose_segment('Importar/Exportar')
    name=visual_item('skillImportName');name.forceActiveFocus();name.setProperty('text','fixture-note');QTest.qWait(20)
    visual_item('skillImport').forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bool(bridge.skillImportPreview.get('name')) and not bridge.skillsBusy,40)
    check('import preview is unverified',bridge.skillImportPreview.get('unverified') is True)
    confirm=visual_item('skillImportConfirm')
    check('confirm enabled only with no findings',confirm.property('enabled')==(len(bridge.skillImportPreview.get('findings') or [])==0))
    if not bridge.skillImportPreview.get('findings'):
        imported_id=bridge.skillImportPreview.get('id')
        confirm.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space);wait(lambda:not bridge.skillsBusy and not bridge.skillImportPreview.get('name'),40)
        check('confirmed import is a draft and nothing is enabled',any(s['id']==imported_id and s['state']=='draft' and s['source']=='imported' for s in bridge.skillsItems) and not any(s['state']=='enabled' and s['source']=='imported' for s in bridge.skillsItems))
    Path(args.artifacts,'skills-import').touch()
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'))
elif args.phase=='connections':
    # Gate protocol (S5 UI): see the module docstring. The phase clicks only the read test and the user's own consent; it never adds, revokes or removes an account.
    from PySide6.QtQml import QQmlEngine,QQmlExpression
    wait(lambda:bridge.connectionsAvailable,50)
    open_page('conexoes','extensoes');wait(lambda:window.property('pageId')=='conexoes',3)
    check('connections panel visible on its page',visual_item('connectionsPanel').property('visible'))
    fake_accounts=[c for c in bridge.connectionsItems if c.get('fake') is True]
    check('the fake-served account is present in the phase (not vacuous)',len(fake_accounts)>=1)
    # One notice per page (docs/ui-spec/01-ajustes-minimalismo.md §1.2): the page banner states it once; a card repeats the
    # SERVIDOR FALSO badge only when its account differs from the others (a mixed page), never on an all-fake page.
    mixed=any(c.get('fake') is not True for c in bridge.connectionsItems)
    check('the page states once that the fake servers have no real credentials',any(i.property('visible') is True and str(i.property('text') or '').startswith('SERVIDOR FALSO — sem credenciais reais') for i in visual_items()))
    check('every fake-served account is covered by the page notice; its card badge shows only where accounts differ',bool(fake_accounts) and all(visual_item('connFake_'+c['id']).property('visible')==mixed and visual_item('connFake_'+c['id']).property('text')=='SERVIDOR FALSO' for c in fake_accounts))
    Path(args.artifacts,'connections-ready').touch()
    providers={p['id']:p for p in bridge.connectionsProviders}
    # The one-click read test sends no arguments, so only operations that need none are offered it (needs_args false).
    readable=next(((c,o) for c in bridge.connectionsItems if c['status']=='connected' for o in providers[c['provider']]['operations'] if o['risk']=='read' and o['scope'] in c['granted_scopes'] and o['needs_args'] is False),None)
    check('a connected account has a granted read operation for the test',readable is not None)
    account,operation=readable
    test_button=visual_item('connTest_'+account['id']+'_'+operation['name']);test_button.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.connectionLastCall.get('operation')==operation['name'] and not bridge.connectionsBusy,60)
    last=visual_item('connLastCall');expression=QQmlExpression(QQmlEngine.contextForObject(last),last,'textFormat === Text.PlainText');plain=expression.evaluate();plain=plain[0] if isinstance(plain,tuple) else plain
    check('read test outcome shown as PlainText from the Core snapshot',plain is True and not expression.hasError() and last.property('text').startswith('Última chamada: '+operation['name']))
    Path(args.artifacts,'connections-read').touch()
    waiting=next(((c,s) for c in bridge.connectionsItems for s in (c.get('pending_scopes') or [])),None)
    check('an account waits for consent',waiting is not None)
    account,scope=waiting
    box=visual_item('connScope_'+account['id']+'_'+scope);box.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space);QTest.qWait(20)
    consent=visual_item('connConsent_'+account['id']);check('consent offered once the scope is ticked',consent.property('enabled'));consent.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    if account['provider']=='homeassistant':
        # S5 E2.3: a token account keeps 'connecting' after consent (granted scopes arrive with the token probe).
        wait(lambda:not bridge.connectionsBusy,60)
        check('Home Assistant consent accepted: the account keeps waiting for its token',next(c for c in bridge.connectionsItems if c['id']==account['id'])['status']=='connecting')
    else:
        # The Core answers "Core ocupado" (busy) while its network slot is taken, and the bridge never queues a click: the
        # user's own consent is repeated (same ticked scope, same button) every 3 s until the Core lists the scope as granted.
        def consented():return scope in next(c for c in bridge.connectionsItems if c['id']==account['id'])['granted_scopes']
        until=time.monotonic()+60;last_click=time.monotonic()
        while not(not bridge.connectionsBusy and consented()):
            if time.monotonic()>until:raise TimeoutError((bridge.state,bridge.results.get('connections'),bridge.pending,bridge.error))
            if not bridge.connectionsBusy and not consented() and time.monotonic()-last_click>3:
                consent.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space);last_click=time.monotonic()
            QTest.qWait(15)
        check('the Core lists the consented scope as granted',scope in next(c for c in bridge.connectionsItems if c['id']==account['id'])['granted_scopes'])
    Path(args.artifacts,'connections-consented').touch()
    if os.environ.get('GIDEON_E24_MCP'):
        # S5 E2.4: discovered tools of an mcp account. Descriptions are server text shown as PlainText; Confiar re-approves one tool by name.
        def plain_of(item):
            expression=QQmlExpression(QQmlEngine.contextForObject(item),item,'textFormat === Text.PlainText');value=expression.evaluate();value=value[0] if isinstance(value,tuple) else value
            return value is True and not expression.hasError()
        mcp=next((c for c in bridge.connectionsItems if c['provider']=='mcp' and c['status']=='connected' and any(t['state']=='needs_reapproval' for t in c.get('tools') or [])),None)
        check('a connected mcp account lists a tool that needs re-approval',mcp is not None)
        tool=next(t for t in mcp['tools'] if t['state']=='needs_reapproval')
        title=visual_item('connToolsTitle_'+mcp['id'])
        # The section appears with the tools the Core listed; give the QML side a moment after the snapshot that carries them.
        wait(lambda:title.property('visible') is True,5)
        check('the tools section is visible and PlainText',title.property('visible') and plain_of(title))
        row=visual_item('connTool_'+mcp['id']+'_'+tool['name'])
        risk_label='destrutiva' if tool['risk']=='destructive' else 'escrita'
        check('the tool row names the tool, its risk and the re-approval state as PlainText',plain_of(row) and tool['name'] in row.property('text') and 'precisa de nova aprovação' in row.property('text') and risk_label in row.property('text'))
        trusted=[t for t in mcp['tools'] if t['state']=='trusted']
        check('a trusted tool is listed as confiável and offers no Confiar',bool(trusted) and 'confiável' in visual_item('connTool_'+mcp['id']+'_'+trusted[0]['name']).property('text') and not visual_item('connTrust_'+mcp['id']+'_'+trusted[0]['name']).property('visible'))
        destructive=[t for t in mcp['tools'] if t['risk']=='destructive']
        if destructive:check('a destructive tool is labelled destrutiva',all('destrutiva' in visual_item('connTool_'+mcp['id']+'_'+t['name']).property('text') for t in destructive))
        description=visual_item('connToolDesc_'+mcp['id']+'_'+tool['name']);check('the server description is shown as PlainText with its own label',plain_of(description) and description.property('text').startswith('Descrição do servidor: '))
        trust=visual_item('connTrust_'+mcp['id']+'_'+tool['name']);check('Confiar is offered for the tool awaiting re-approval',trust.property('visible') and trust.property('enabled'))
        trust.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
        # Confiar asks first (connTrustConfirm, a Modal); only its confirmation button sends the trust to the Core.
        dialog=window.findChild(QObject,'connTrustConfirm');wait(lambda:dialog.property('visible'),3)
        visual_item('connTrustConfirmButton').forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
        wait(lambda:not bridge.connectionsBusy and next(t for t in next(c for c in bridge.connectionsItems if c['id']==mcp['id'])['tools'] if t['name']==tool['name'])['state']=='trusted',60)
        check('the Core trusted the tool after the click',next(t for t in next(c for c in bridge.connectionsItems if c['id']==mcp['id'])['tools'] if t['name']==tool['name'])['state']=='trusted')
        QTest.qWait(50)
        check('the row now says confiável and Confiar is gone','confiável' in visual_item('connTool_'+mcp['id']+'_'+tool['name']).property('text') and not visual_item('connTrust_'+mcp['id']+'_'+tool['name']).property('visible'))
        Path(args.artifacts,'connections-mcp').touch()
    ha_token=os.environ.get('GIDEON_E23_HA_TOKEN')
    if ha_token:
        # S5 E2.3 set-token path: the token is typed into the hidden field, sent once, and the field is cleared.
        ha=next((c for c in bridge.connectionsItems if c['provider']=='homeassistant' and c['status']=='connecting'),None)
        check('a Home Assistant account waits for its token',ha is not None)
        field=visual_item('connToken_'+ha['id'])
        echo=QQmlExpression(QQmlEngine.contextForObject(field),field,'echoMode === TextInput.Password');masked=echo.evaluate();masked=masked[0] if isinstance(masked,tuple) else masked
        check('the token field is a password field (echoMode Password)',masked is True and not echo.hasError())
        field.forceActiveFocus()
        for character in ha_token:QTest.keyClick(window,character)
        send=visual_item('connSetToken_'+ha['id']);check('send enabled for a token of valid length',send.property('enabled'));send.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
        # the field is cleared at the click; the delegate is rebuilt when the account connects, so read it before the wait
        check('the token field is cleared right after sending',field.property('text')=='')
        wait(lambda:not bridge.connectionsBusy and next(c for c in bridge.connectionsItems if c['id']==ha['id'])['status']=='connected',60)
        check('the Core connects the Home Assistant account after the probe',next(c for c in bridge.connectionsItems if c['id']==ha['id'])['status']=='connected')
        check('the bridge snapshot never holds the token',ha_token not in json.dumps(bridge.snapshot,ensure_ascii=False))
        Path(args.artifacts,'connections-token').touch()
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'))
elif args.phase=='registry':
    # Gate protocol (S5 E3 UI): see the module docstring.
    from PySide6.QtQml import QQmlEngine,QQmlExpression
    def plain_of(item):
        expression=QQmlExpression(QQmlEngine.contextForObject(item),item,'textFormat === Text.PlainText');value=expression.evaluate();value=value[0] if isinstance(value,tuple) else value
        return value is True and not expression.hasError()
    wait(lambda:bridge.registryAvailable,50)
    open_page('conexoes','extensoes');wait(lambda:window.property('pageId')=='conexoes',3)
    # The routes are a part of the page: the Rotas segment shows them (Contas is the default part).
    choose_segment('Rotas')
    check('routes panel visible on the connections page',visual_item('routesPanel').property('visible'))
    purposes={p['id']:p for p in bridge.registryPurposes}
    check('the three fixed purposes are listed',list(purposes)==['create_issue','list_events','read_state'])
    for ident,purpose in purposes.items():
        label=visual_item('routePurpose_'+ident)
        check('purpose '+ident+' shows its label and the chosen route as PlainText',plain_of(label) and purpose['label'] in label.property('text'))
        for candidate in purpose['candidates']:
            # The candidate row is a layout: its badge, route, status and reason are its child texts.
            row=visual_item('routeCandidate_'+ident+'_'+candidate['route'])
            shown=texts_of(row);badge='Escolhida' if purpose.get('route_chosen')==candidate['route'] else 'Descartada'
            check('candidate '+ident+'/'+candidate['route']+' shows route, status and the Core reason as PlainText',all(plain_of(t) for t in shown if t.metaObject().className()=='QQuickText') and any(candidate['reason']==t.property('text') for t in shown) and any(t.property('text')==badge for t in shown))
    create=purposes['create_issue']
    check('the visual fallback is off by default and says so',bridge.registryVisualAllowed==[] and 'desligado' in visual_item('routeVisualState_create_issue').property('text'))
    warning=visual_item('routeVisualWarning_create_issue');check('a warning about the visual fallback is on screen as PlainText',warning.property('visible') and plain_of(warning) and warning.property('text').startswith('Atenção'))
    check('only create_issue offers the visual switch',visual_item('routeVisual_create_issue').property('visible') and not visual_item('routeVisual_list_events').property('visible') and not visual_item('routeVisual_read_state').property('visible'))
    Path(args.artifacts,'registry-ready').touch()
    revision=bridge.registryRevision
    plan=visual_item('routePlan_create_issue');plan.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:not bridge.registryBusy and bridge.registryResult!='',30)
    check('Planejar answered from the Core and changed nothing',bridge.registryRevision==revision and bridge.registryVisualAllowed==[] and ('Rota planejada' in bridge.registryResult or 'Nenhuma rota' in bridge.registryResult))
    result=visual_item('routesResult');check('the plan answer is shown as PlainText',result.property('visible') and plain_of(result))
    bridge.registryPlan('nope');check('an unknown purpose is refused by the bridge',bridge.registryResult=='Finalidade desconhecida')
    bridge.registryAllowVisual('read_state',True);check('a purpose with no visual route is refused by the bridge',bridge.registryResult=='Esta finalidade não tem rota visual' and bridge.registryVisualAllowed==[])
    Path(args.artifacts,'registry-plan').touch()
    # The switch is unlabelled (its state is the line next to it); turning it on asks first in routeVisualConfirm, turning it off does not.
    toggle=visual_item('routeVisual_create_issue');check('the switch offers to turn the fallback on',toggle.property('enabled') and toggle.property('checked') is False and 'desligado' in visual_item('routeVisualState_create_issue').property('text'))
    toggle.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    confirm=window.findChild(QObject,'routeVisualConfirm');wait(lambda:confirm.property('visible'),3)
    visual_item('routeVisualConfirmButton').forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:not bridge.registryBusy and bridge.registryVisualAllowed==['create_issue'],30);QTest.qWait(50)
    check('the Core lists create_issue as allowed and the card says ligado por você','ligado por você' in visual_item('routeVisualState_create_issue').property('text') and visual_item('routeVisual_create_issue').property('checked') is True)
    Path(args.artifacts,'registry-allowed').touch()
    toggle=visual_item('routeVisual_create_issue');toggle.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:not bridge.registryBusy and bridge.registryVisualAllowed==[],30);QTest.qWait(50)
    check('the same switch revoked it: desligado and the Core agrees','desligado' in visual_item('routeVisualState_create_issue').property('text') and visual_item('routeVisual_create_issue').property('checked') is False)
    Path(args.artifacts,'registry-revoked').touch()
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'))
elif args.phase=='plugins':
    # Gate protocol (C0 UI): the gate starts Core with --plugin-python, approves, installs and stages dummy_echo,
    # then launches this phase. Markers written to --artifacts by this phase, in order:
    #   ready    - dummy_echo is listed by Core as disabled and its enable control is offered
    #   revoked    - Core confirmed disabled after revoke; enable is gated until new approval and Core refuses re-enable
    #   reapproved - after explicit re-approval of the installed plugin, Qt enable runs dummy_echo again
    # The phase never restarts Core and never edits the ledger; the gate may inspect plugin-state.json after `revoked`.
    open_page('plugins','extensoes')
    wait(lambda:window.property('pageId')=='plugins',3)
    def dummy():return next((p for p in bridge.pluginItems if p.get('plugin_id')=='dummy_echo'),None)
    wait(lambda:dummy() is not None,50)
    check('Core lists dummy_echo disabled and not enabled',dummy()['state']=='disabled' and dummy()['enabled'] is False)
    check('status label shows Desativado',visual_item('pluginStatus_dummy_echo').property('text').endswith('Desativado'))
    check('enable offered for installed plugin',visual_item('enable_dummy_echo').property('enabled'))
    check('invoke unavailable while disabled',not visual_item('invoke_dummy_echo.echo').property('enabled') and not visual_item('capabilityInput_dummy_echo').property('enabled'))
    Path(args.artifacts,'ready').touch()
    enable=visual_item('enable_dummy_echo');enable.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:dummy() is not None and dummy()['state']=='running',30)
    check('Qt enable reaches Core and sandbox runs dummy_echo',dummy()['enabled'] is True and bridge.pluginResult=='Plugin ativado')
    check('status label shows sandbox running without network',visual_item('pluginStatus_dummy_echo').property('text').endswith('Sandbox, sem rede'))
    field=visual_item('capabilityInput_dummy_echo');field.forceActiveFocus();[QTest.keyClick(window,getattr(Qt.Key,'Key_'+c.upper())) for c in 'hello']
    check('typed text reaches capability input',field.property('text')=='hello')
    invoke=visual_item('invoke_dummy_echo.echo');invoke.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.capabilityResultText=='HELLO',20)
    check('capability result from real sandbox is uppercased text',visual_item('capabilityResult').property('text')=='HELLO')
    check('invocation pending text cleared when result arrives',bridge.pluginResult=='')
    QTest.qWait(100);window.grabWindow().save(str(Path(args.artifacts)/'ui.png'))
    revoke=visual_item('revoke_dummy_echo');revoke.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    confirm=window.findChild(QObject,'revokeConfirm');wait(lambda:confirm.property('visible'),3)
    check('revoke waits for confirmation',dummy()['state']=='running' and dummy()['enabled'] is True)
    confirm.accept()
    wait(lambda:dummy() is not None and dummy()['state']=='disabled' and dummy()['enabled'] is False,15)
    check('confirmed revoke disables plugin in Core',dummy()['state']=='disabled')
    check('revoke result label shown',bridge.pluginResult=='Permissões revogadas; plugin desativado')
    check('invoke controls disabled after revoke',not visual_item('invoke_dummy_echo.echo').property('enabled') and not visual_item('capabilityInput_dummy_echo').property('enabled'))
    check('capability result cleared after revoke',visual_item('capabilityResult').property('text')=='' and bridge.capabilityResultText=='')
    check('UI gates enable until new approval and shows hint',not visual_item('enable_dummy_echo').property('enabled') and visual_item('reapprovalHint_dummy_echo').property('visible'))
    bridge.enablePlugin('dummy_echo')
    wait(lambda:bridge.pluginResult=='Aprove as permissões antes de ativar',10)
    check('Core refuses re-enable until new approval',dummy()['state']=='disabled' and dummy()['enabled'] is False)
    Path(args.artifacts,'revoked').touch()
    review=visual_item('review_dummy_echo');check('review offered for installed unapproved plugin',review.property('enabled'));review.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    dialog=window.findChild(QObject,'hubReviewDialog');wait(lambda:dialog.property('visible'),3)
    ack=window.findChild(QObject,'publisherAcknowledgement');approve=window.findChild(QObject,'approveHubButton')
    check('re-review never defaults to publisher acknowledgement',not ack.property('checked') and not approve.property('enabled'))
    ack.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    approve.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:next((e for e in bridge.hubEntries if e.get('plugin_id')=='dummy_echo' and e.get('permissions_approved')),None) is not None,10)
    check('re-approval keeps dummy_echo installed and not running',bridge.hubEntries and next(e for e in bridge.hubEntries if e['plugin_id']=='dummy_echo')['status']=='installed' and dummy()['state']=='disabled')
    wait(lambda:visual_item('enable_dummy_echo').property('enabled'),5)
    check('enable offered again after re-approval',not visual_item('reapprovalHint_dummy_echo').property('visible'))
    enable=visual_item('enable_dummy_echo');enable.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:dummy() is not None and dummy()['state']=='running',30)
    check('re-enabled dummy_echo runs in sandbox again',dummy()['enabled'] is True and bridge.pluginResult=='Plugin ativado')
    Path(args.artifacts,'reapproved').touch()
elif args.phase=='permissions':
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('native S1 before permission review',bridge.resultVerified and bridge.snapshot['speech']['samples']>0)
    open_page('plugins','extensoes')
    wait(lambda:window.property('pageId')=='plugins',3)
    review=visual_item('review_benign_fixture');review.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    dialog=window.findChild(QObject,'hubReviewDialog');wait(lambda:dialog.property('visible'),3)
    ack=window.findChild(QObject,'publisherAcknowledgement');approve=window.findChild(QObject,'approveHubButton')
    check('review never defaults to publisher acknowledgement',not ack.property('checked') and not approve.property('enabled'))
    ack.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    check('actual checkbox enables explicit approval',ack.property('checked') and approve.property('enabled'))
    approve.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.hubApprovalRevision=='1' and bridge.hubEntries[0]['permissions_approved'],5)
    check('Qt action persists exact manifest approval in Core',bridge.hubApprovalResult=='Permissões aprovadas: benign_fixture')
    QTest.qWait(100);check('acknowledged approval disables duplicate submit',not approve.property('enabled'))
    check('approval remains distinct from installation and identity',bridge.hubEntries[0]['status']=='not_installed' and not bridge.snapshot['hub']['publisher_verified'])
    image=window.grabWindow();image.save(str(Path(args.artifacts)/'ui.png'));check('review fits minimum viewport',dialog.property('height')<=window.height())
    dialog.close();Path(args.artifacts,'approved').touch()
    wait(lambda:not bridge.connected,10);check('offline revokes cached approval UI',not bridge.hubEntries and not bridge.hubApprovalAvailable);Path(args.artifacts,'offline').touch()
    wait(lambda:bridge.connected,10);wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('real restart reloads exact approval',bridge.hubApprovalRevision=='1' and bridge.hubEntries[0]['permissions_approved'])
    check('native S1 after approval and restart',bridge.resultVerified and bridge.snapshot['transcript']['source']=='voice' and bridge.snapshot['speech']['samples']>0)
elif args.phase=='design':
    window.setProperty('width',1380);window.setProperty('height',904)
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('new dashboard preserves native voice command and PCM',bridge.resultVerified and bridge.snapshot['transcript']['source']=='voice' and bridge.snapshot['speech']['samples']>0)
    def capture(name):
        QTest.qWait(120);image=window.grabWindow();check(name+' renders at HiDPI',not image.isNull() and image.width()==window.width()*2)
        image.save(str(Path(args.artifacts)/(name+'.png')))
    def navigate(index):
        pid,tab={0:('hoje','assistente'),1:('cfg_voz','configuracoes'),2:('cfg_audio','configuracoes'),3:('cfg_aparencia','configuracoes'),4:('perm_visao','permissoes'),5:('diag_estado','diagnostico'),6:('plugins','extensoes')}[index]
        open_page(pid,tab);check('keyboard navigation '+pid,window.property('pageId')==pid)
    capture('home')
    navigate(1);capture('voice')
    poc=visual_item('wakeSwitch_okay_gideon');check('unqualified wake stays blocked in redesigned page',poc is not None and not poc.property('enabled'))
    navigate(2);capture('audio')
    slider=visual_item('gainSlider');slider.forceActiveFocus()
    for _ in range(10):QTest.keyClick(window,Qt.Key.Key_Left)
    check('audio gain slider responds to keyboard',round(slider.property('value'))==50)
    apply=visual_item('applyGainButton');apply.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.outputVolume==50,5);check('new audio page saves through real Core',True)
    bridge.submitText('open brave');wait(lambda:bridge.state=='speaking' and bridge.snapshot['speech_samples']>0,25)
    navigate(3)
    check('live speech keeps cancel on settings page',button.property('enabled'))
    # The live subtitle belongs to Hoje (Assistente), not to the settings pages: the redesign keeps only Cancelar global.
    navigate(0)
    check('live subtitle stays available on Hoje while speech runs',window.findChild(QObject,'transcriptViewport').property('visible') and bool(bridge.subtitle))
    navigate(2)
    wait(lambda:bridge.snapshot.get('speech_status')=='completed' and bridge.snapshot['speech']['output_volume_percent']==50,35)
    check('new audio gain applies to native Pocket PCM',bridge.resultVerified and bridge.snapshot['speech']['samples']>0)
    # The rollback control lives in Configurações > Geral ("Revisão e anterior"), not on the voice page.
    open_page('cfg_geral','configuracoes');wait(lambda:window.property('pageId')=='cfg_geral',3)
    rollback=visual_item('rollbackPreferencesButton');rollback.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.outputVolume==100,5);check('existing rollback restores new audio page change',bridge.outputVolume==100)
    navigate(3);capture('appearance')
    check('appearance offers the preset tiles and accent choices',visual_item('preset_gideon-claro') is not None and visual_item('accentVioleta') is not None)
    for index,name in ((4,'permissions'),(5,'diagnostics'),(6,'hub_page')):navigate(index);capture(name)
    for index in (0,1,3,6):
        navigate(index);window.setProperty('width',480);window.setProperty('height',520);QTest.qWait(120)
        # Owner rule: Cancelar shows only while the Core session is cancellable. Idle means hidden, so nothing is clipped here.
        check('cancel hidden at idle on small window '+str(index),not button.isVisible())
        capture('small_'+str(index))
        window.setProperty('width',1380);window.setProperty('height',904)
    bridge.submitText('open brave');wait(lambda:bridge.state=='speaking' and bridge.snapshot['speech_samples']>0,25)
    window.setProperty('width',480);window.setProperty('height',520);QTest.qWait(120)
    check('cancel visible and fits small window while speech is cancellable',button.isVisible() and button.mapToItem(window.contentItem(),QPointF(0,0)).y()+button.height()<=window.height()+.5)
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',35)
    check('cancel hidden again after speech completes',not button.isVisible())
    window.setProperty('width',1380);window.setProperty('height',904)
    navigate(0)
    changes=len(deltas)
    def ticks():
        row=Path('/proc/self/stat').read_text().split();return int(row[13])+int(row[14])
    before=ticks();started=time.monotonic();QTest.qWait(3000)
    cpu=(ticks()-before)/os.sysconf('SC_CLK_TCK')/(time.monotonic()-started)*100
    metrics['idle_ui_cpu_percent']=cpu;metrics['idle_ui_rss_bytes']=int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
    check('new static dashboard emits no idle UI deltas',len(deltas)==changes)
    check('software UI idle CPU bounded',cpu<=4.0)
    capture('home_final')
elif args.phase in ('hub','hub_quarantine'):
    open_page('plugins','extensoes')
    dialog=visual_item('pluginsPage');wait(lambda:window.property('pageId')=='plugins',3)
    label=visual_item('hubBanner')
    check('actual Qt Hub opens with actor snapshot',label.property('text')==bridge.hubDescription)
    if args.phase=='hub':
        check('Hub never presents declared permissions as approval',len(bridge.hubEntries)==3 and 'não autenticado' in bridge.hubDescription and bridge.hubEntries[0]['status']=='not_installed')
        check('Core compatibility appears in UI',bridge.hubEntries[1]['reason']=='api_version' and bridge.hubEntries[2]['reason']=='dependencies_unresolved')
    else:
        check('quarantined catalog renders no plugins',not bridge.hubEntries and 'quarentena' in label.property('text'))
    check('Hub dialog bounded in minimum window',dialog.property('height')<=window.height())
    QTest.qWait(100);image=window.grabWindow();image.save(str(Path(args.artifacts)/'ui.png'))
    check('Hub renders offscreen',not image.isNull())
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('native S1 remains verified with Hub loaded or quarantined',bridge.resultVerified and bridge.snapshot['transcript']['source']=='voice' and bridge.snapshot['speech']['samples']>0)
    check('S1 remains virtual',bridge.snapshot['speech']['sink']=='virtual')
elif args.phase=='voice':
    wait(lambda:bridge.partial)
    # The Hoje subtitle shows the Core text behind its speaker label ("Você (parcial): ").
    check('partial is actual Core subtitle',subtitle.property('text')=='Você (parcial): '+bridge.subtitle and bridge.partial)
    check('cancel enabled during live voice',button.property('enabled'))
    button.forceActiveFocus();check('keyboard focus works',button.property('activeFocus'))
    wait(lambda:bridge.snapshot.get('speech_status')=='completed')
    # The receipt is shown in Portuguese (bridge RECEIPT_PREFIXES): "Processo do app verificado no sandbox: ..."
    check('final voice text and verified result rendered',not bridge.partial and 'brave' in bridge.subtitle.lower() and 'Processo do app verificado no sandbox' in bridge.result)
    check('UI observes actual virtual PCM',bridge.snapshot['speech']['samples']>0)
    check('cancel disabled after session',not button.property('enabled') and not bridge.sessionId)
    image=window.grabWindow();check('HiDPI offscreen rendering',image.width()==1280 and image.height()==1040);image.save(str(Path(args.artifacts)/'ui.png'))
    window.setProperty('width',window.property('minimumWidth'));window.setProperty('height',window.property('minimumHeight'));QTest.qWait(100)
    # The window's root layout (Main.qml's ColumnLayout: top bar, sub-bar, page stage) is the first child of the content item.
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
elif args.phase=='pack':
    check('pack metadata comes from actual Core',len(bridge.wakeChoices)==2 and 'base-en-dev-v1' in bridge.packDescription)
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('initial native S1 uses preflighted pack',bridge.resultVerified and bridge.snapshot['speech']['samples']>0)
    window.setProperty('width',window.property('minimumWidth'));window.setProperty('height',window.property('minimumHeight'))
    open_page('cfg_voz','configuracoes');wait(lambda:window.property('pageId')=='cfg_voz',3)
    hey_switch=window.findChild(QObject,'wakeSwitch_hey_gideon');okay_switch=window.findChild(QObject,'wakeSwitch_okay_gideon')
    check('explicit phrase text presented',window.findChild(QObject,'wakeRow_hey_gideon') is not None and hey_switch.property('checked'))
    check('POC phrase cannot be selected',okay_switch is not None and not okay_switch.property('enabled'))
    select=window.findChild(QObject,'restoreWakeDefaults');select.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.configurationStatus=='restart_required',5)
    check('Qt selection persisted by actor',bridge.snapshot['preferences']['wake_phrase']=='hey_gideon')
    check('selection requires actual restart',not bridge.preferencesAvailable and not bridge.textAvailable)
    image=window.grabWindow();image.save(str(Path(args.artifacts)/'pack.png'));Path(args.artifacts,'selected').touch()
    wait(lambda:not bridge.connected,10);Path(args.artifacts,'offline').touch();wait(lambda:bridge.connected,10)
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('selected wake runs native integrated flow after restart',bridge.snapshot['base_pack']['active_phrase']=='hey_gideon' and bridge.resultVerified and bridge.snapshot['speech']['samples']>0)
    bridge.rollbackPreferences();wait(lambda:bridge.configurationStatus=='restart_required',5)
    check('rollback restores default selection with new revision',bridge.snapshot['preferences']['wake_phrase'] is None and bridge.preferencesRevision=='2')
    Path(args.artifacts,'rolled_back').touch()
elif args.phase=='safe_mode':
    check('connected Core reports safe mode',bridge.configurationStatus=='safe_mode' and bridge.state=='safe_mode')
    check('safe mode disables ordinary controls',not bridge.preferencesAvailable and not bridge.textAvailable and not button.property('enabled'))
    open_page('diag_recuperacao','diagnostico');wait(lambda:window.property('pageId')=='diag_recuperacao',3)
    recover=window.findChild(QObject,'recoverConfigurationButton');check('recovery control is actionable',recover.property('enabled'))
    check('safe mode explanatory message matches Core',window.findChild(QObject,'configurationMessage').property('text')==bridge.configurationMessage)
    window.setProperty('width',window.property('minimumWidth'));window.setProperty('height',window.property('minimumHeight'));QTest.qWait(100)
    point=recover.mapToItem(window.contentItem(),QPointF(0,0))
    check('recovery fits minimum viewport',point.x()>=0 and point.y()>=0 and point.x()+recover.width()<=window.width() and point.y()+recover.height()<=window.height())
    check('safe transcript viewport stays readable',window.findChild(QObject,'transcriptViewport').property('height')>=48)
    image=window.grabWindow();image.save(str(Path(args.artifacts)/'safe-mode.png'))
    recover.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    confirm=window.findChild(QObject,'confirmRecoverButton');confirm.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.configurationStatus=='restart_required',5)
    check('recovery requires restart, not fictitious live activation',not bridge.recoveryAvailable and not bridge.preferencesAvailable and not bridge.textAvailable)
    check('recovery acknowledgement reflects persisted Core state','reinício necessário' in bridge.preferencesResult)
    Path(args.artifacts,'recovered').touch()
    wait(lambda:not bridge.connected,10);Path(args.artifacts,'offline').touch()
    wait(lambda:bridge.connected,10)
    check('actual restarted Core leaves safe mode',bridge.configurationStatus=='ready')
    wait(lambda:bridge.snapshot.get('speech_status')=='completed',40)
    check('native voice flow resumes after real restart',bridge.snapshot['transcript']['source']=='voice' and bridge.resultVerified and bridge.snapshot['speech']['samples']>0)
    check('physical capability remains virtual only',bridge.snapshot['speech']['sink']=='virtual')
elif args.phase=='feedback':
    # Gate protocol (B2 UI): the indicator is a switch in Aparência that saves on change; the volume is a draft (the slider)
    # applied with Aplicar in Áudio; "Restaurar anterior" in Geral undoes one step (the last Core change).
    open_page('cfg_aparencia','configuracoes');wait(lambda:window.property('pageId')=='cfg_aparencia',3)
    visual=visual_item('visualPagePreference');visual.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:not bridge.visualFeedback,5)
    check('visual indicator switch saves on change and the Core confirms it',bridge.preferencesResult=='Preferências salvas pelo Core' and bridge.preferencesRevision=='1')
    open_page('cfg_audio','configuracoes');wait(lambda:window.property('pageId')=='cfg_audio',3)
    slider=visual_item('gainSlider');slider.forceActiveFocus()
    for _ in range(10):QTest.keyClick(window,Qt.Key.Key_Left)
    check('volume draft reaches 50 with the keyboard',round(slider.property('value'))==50)
    apply=visual_item('applyGainButton');apply.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.outputVolume==50 and bridge.preferencesRevision=='2',5)
    check('Aplicar saves the volume through the Core',bridge.outputVolume==50)
    QTest.qWait(50)
    check('decorative activity indicator hidden',not window.findChild(QObject,'activityIndicator').property('visible'))
    check('essential state stays visible and cancel hidden at idle',window.findChild(QObject,'aura').property('visible') and not button.property('visible'))
    bridge.submitText('open brave');wait(lambda:bridge.snapshot.get('speech_status')=='completed',35)
    check('Qt observes real attenuated native speech',bridge.resultVerified and bridge.snapshot['speech']['output_volume_percent']==50 and bridge.snapshot['speech']['samples']>0)
    QTest.qWait(100);image=window.grabWindow();image.save(str(Path(args.artifacts)/'ui.png'))
    check('feedback page stays within minimum window',not image.isNull())
    open_page('cfg_geral','configuracoes');wait(lambda:window.property('pageId')=='cfg_geral',3)
    rollback=visual_item('rollbackPreferencesButton');rollback.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.outputVolume==100 and bridge.preferencesRevision=='3',5)
    check('Qt rollback undoes only the last change (volume back to 100, indicator still off)',bridge.outputVolume==100 and not bridge.visualFeedback)
elif args.phase=='preferences':
    open_page('cfg_voz','configuracoes');wait(lambda:window.property('pageId')=='cfg_voz',3)
    check('settings page opens on actual Qt control',window.property('pageId')=='cfg_voz')
    # Gate protocol (B2 UI): the session timeout keeps its "Salvar prazo" button; the audible switch (Áudio) saves on change;
    # "Restaurar anterior" (Geral) undoes one step, the last Core change.
    timeout=visual_item('timeoutPreference');timeout.setProperty('value',20000)
    save=visual_item('savePreferencesButton');save.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.preferencesRevision=='1',5)
    check('Qt save reaches Core configuration',bridge.sessionTimeout==20000)
    check('Core reports persisted preferences',bridge.preferencesResult=='Preferências salvas pelo Core')
    open_page('cfg_audio','configuracoes');wait(lambda:window.property('pageId')=='cfg_audio',3)
    audible=visual_item('audiblePreference');audible.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.preferencesRevision=='2',5)
    check('audible switch saves on change through the Core',not bridge.audibleFeedback)
    bridge.submitText('open brave');wait(lambda:bool(bridge.result),5)
    check('same executor verifies effect with feedback off',bridge.resultVerified and bridge.state=='idle')
    check('disabled feedback produces no virtual speech',bridge.snapshot['speech'] is None and not any(e['kind']=='speech_started' for e in bridge.snapshot['events']))
    open_page('cfg_geral','configuracoes');wait(lambda:window.property('pageId')=='cfg_geral',3)
    rollback=visual_item('rollbackPreferencesButton');rollback.forceActiveFocus();QTest.keyClick(window,Qt.Key.Key_Space)
    wait(lambda:bridge.preferencesRevision=='3',5)
    check('Qt rollback undoes only the last change (feedback back on, timeout kept)',bridge.audibleFeedback and bridge.sessionTimeout==20000)
    bridge.submitText('open brave');wait(lambda:bridge.snapshot.get('speech_status')=='completed',35)
    check('restored preference integrates real native TTS',bridge.resultVerified and bridge.snapshot['speech']['samples']>0)
    QTest.qWait(100);image=window.grabWindow();image.save(str(Path(args.artifacts)/'ui.png'))
    check('settings renders offscreen',not image.isNull())
else:
    # Outer fixture controller kills/restarts Core. Observe offline, then one new server.
    Path(args.artifacts,'connected').touch();wait(lambda:not bridge.connected,10)
    check('offline clears stale session/subtitle and blocks cancel',not bridge.sessionId and not bridge.subtitle and not button.property('enabled'))
    Path(args.artifacts,'offline').touch();wait(lambda:bridge.connected,10)
    check('automatic reconnect to real restarted Core',bridge.state=='idle')
    wait(lambda:bridge.textAvailable,5)
    inputbox.forceActiveFocus();inputbox.setProperty('text','open brave');QTest.keyClick(window,Qt.Key.Key_Return)
    wait(lambda:bool(bridge.result),5)
    check('text uses actual shared sandbox executor',bridge.snapshot['transcript']['source']=='user_text' and 'Processo do app verificado no sandbox' in bridge.result)
    check('new server sequence resets safely',bridge.snapshot['sequence']>0)
print(json.dumps({'phase':args.phase,'passed':len(checks),'failed':0,'ignored':0,'checks':checks,'state_trace':trace,'metrics':metrics}),flush=True)
bridge.poll.stop();bridge.retry.stop();bridge.timeout.stop();bridge.socket.close()

window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
del engine
del bridge
