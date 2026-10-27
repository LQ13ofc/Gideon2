"""Microphone, speaker, live audio and microphone assistant texts."""
import datetime
from PySide6.QtCore import QCoreApplication,QT_TRANSLATE_NOOP
from translations import _fill,_tr,_Messages
from msgs_misc import OPS,PENDING

REC_PROBLEM_TEXT=_Messages({'rumble':QT_TRANSLATE_NOOP('Bridge','capta quase só ruído grave'),'clipping':QT_TRANSLATE_NOOP('Bridge','satura'),'too_noisy':QT_TRANSLATE_NOOP('Bridge','tem muito ruído de fundo'),'too_quiet':QT_TRANSLATE_NOOP('Bridge','capta sinal muito fraco')})
REC_ERROR_TEXT=_Messages({'recorder_unavailable':QT_TRANSLATE_NOOP('Bridge','o gravador de áudio não está instalado'),'recorder_exited':QT_TRANSLATE_NOOP('Bridge','o gravador parou antes de gravar'),'sandbox_unavailable':QT_TRANSLATE_NOOP('Bridge','o isolamento do gravador (bwrap) não está disponível'),'invalid_device':QT_TRANSLATE_NOOP('Bridge','dispositivo inválido'),'audio_tool_failed':QT_TRANSLATE_NOOP('Bridge','a ferramenta de áudio falhou'),'no_audio_tool':QT_TRANSLATE_NOOP('Bridge','nenhuma ferramenta de áudio encontrada')})

def recommendation_view(rec):
    """Plain dict for QML: state, progress-free ranking rows with their Portuguese problem names, and the recommended id."""
    rec=rec if isinstance(rec,dict) else {'state':'idle','ranked':[],'recommended':None,'current':None,'current_is_bad':None,'reason':None}
    rows=[{'id':i['id'],'label':i['label'],'camera':i['camera'],'current':i['current'],'error':i.get('error',''),'score':round(float(i['score']),3),'reason':i.get('reason',''),
           'problems':', '.join(REC_PROBLEM_TEXT[p] for p in i['problems']) if i['problems'] else ('' if 'error' in i else QCoreApplication.translate('Bridge','sem problemas')),
           'recommended':i['id']==rec.get('recommended'),'problemsOk':not i['problems'] and 'error' not in i} for i in rec.get('ranked') or []]
    error=rec.get('error')
    return {'state':rec.get('state','idle'),'rows':rows,'recommended':rec.get('recommended') or '','current':rec.get('current') or '',
            'currentIsBad':rec.get('current_is_bad') is True,'reason':rec.get('reason') or '','error':REC_ERROR_TEXT.get(error,'') if error else ''}
DEFAULT_DEVICE_LABEL=QT_TRANSLATE_NOOP('Bridge','Padrão do sistema')
DEFAULT_MARK=QT_TRANSLATE_NOOP('Bridge',' · padrão do sistema')
UNAVAILABLE_DEVICE_LABEL=QT_TRANSLATE_NOOP('Bridge','Dispositivo salvo · indisponível agora')
AUDIO_REASON_MESSAGES=_Messages({'no_audio_tool':QT_TRANSLATE_NOOP('Bridge','Nenhuma ferramenta de áudio encontrada: instale pipewire-pulse/pactl'),'audio_tool_failed':QT_TRANSLATE_NOOP('Bridge','A ferramenta de áudio falhou ao listar dispositivos; tente Atualizar lista')})
LIVE_ERROR_MESSAGES=_Messages({'recorder_unavailable':QT_TRANSLATE_NOOP('Bridge','gravador de áudio indisponível (instale pipewire-pulse)'),'recorder_exited':QT_TRANSLATE_NOOP('Bridge','o gravador de áudio parou'),'sandbox_unavailable':QT_TRANSLATE_NOOP('Bridge','isolamento do gravador indisponível (bwrap ausente)'),'wake_worker_unavailable':QT_TRANSLATE_NOOP('Bridge','worker de wake indisponível'),'wake_worker_failed':QT_TRANSLATE_NOOP('Bridge','worker de wake falhou'),'restart_limit':QT_TRANSLATE_NOOP('Bridge','limite de reinícios atingido'),'invalid_device':QT_TRANSLATE_NOOP('Bridge','dispositivo de entrada inválido'),'player_unavailable':QT_TRANSLATE_NOOP('Bridge','reprodutor de áudio indisponível'),'player_write_failed':QT_TRANSLATE_NOOP('Bridge','falha ao enviar áudio ao reprodutor'),'player_failed':QT_TRANSLATE_NOOP('Bridge','o reprodutor de áudio falhou'),'player_timeout':QT_TRANSLATE_NOOP('Bridge','o reprodutor de áudio não respondeu'),'worker_crashed':QT_TRANSLATE_NOOP('Bridge','o worker de wake parou com erro (veja o diagnóstico)'),'worker_import_error':QT_TRANSLATE_NOOP('Bridge','faltam bibliotecas do worker de wake (veja o diagnóstico)'),'device_unavailable':QT_TRANSLATE_NOOP('Bridge','o microfone escolhido não está disponível'),'model_missing':QT_TRANSLATE_NOOP('Bridge','arquivo do modelo de wake ausente ou alterado')})
RESTORE_BUSY_TEXT=QT_TRANSLATE_NOOP('Bridge','Indisponível durante a sessão de voz; tente quando o Gideon estiver em espera')
RESTORE_BACKUP_TEXT=QT_TRANSLATE_NOOP('Bridge','Padrões não restaurados: não foi possível gravar a cópia config.json.bak nem trocar a configuração; os valores atuais continuam')
SENSITIVITY_RANGE_TEXT=QT_TRANSLATE_NOOP('Bridge','Sensibilidade fora de 0,5 a 1,5; nada foi enviado')
DEVICE_INVALID_TEXT=QT_TRANSLATE_NOOP('Bridge','Dispositivo inválido; nada foi enviado')

# A6 state line of the microphone consent: desligado / aguardando reinício / ouvindo / erro: motivo (texts only; no Core code).
def live_state_text(live):
    if not live:return QCoreApplication.translate('Bridge','sem informação do Core')
    if live.get('restart_required') is True:return QCoreApplication.translate('Bridge','aguardando reinício do Core')
    if not live.get('enabled'):return QCoreApplication.translate('Bridge','desligado')
    if live.get('input_state')=='capturing':return QCoreApplication.translate('Bridge','ouvindo')
    if live.get('input_state')=='error':
        error=live.get('last_error') or ''
        return QCoreApplication.translate('Bridge','erro: ')+(LIVE_ERROR_MESSAGES.get(error,QCoreApplication.translate('Bridge','falha na captura')) if not error.startswith('player_') else QCoreApplication.translate('Bridge','falha na captura'))
    return QCoreApplication.translate('Bridge','em espera')

def live_input_text(live):return QCoreApplication.translate('Bridge','Escuta do microfone: ')+live_state_text(live)
REAL_KIND_TEXT=_Messages({'open_app':QT_TRANSLATE_NOOP('Bridge','Abriu'),'volume':QT_TRANSLATE_NOOP('Bridge','Volume ajustado'),'mute':QT_TRANSLATE_NOOP('Bridge','Mudo ativado'),'unmute':QT_TRANSLATE_NOOP('Bridge','Som ativado'),'volume_up':QT_TRANSLATE_NOOP('Bridge','Volume aumentado'),'volume_down':QT_TRANSLATE_NOOP('Bridge','Volume diminuído')})
REAL_ACTION_MESSAGES=_Messages({'consent_required':QT_TRANSLATE_NOOP('Bridge','Ações no computador não ativadas: a confirmação não chegou ao Core; nada foi alterado')})
# Outcome codes of a command that produced no receipt (src/host.rs and src/core.rs codes).
COMMAND_CODE_MESSAGES=_Messages({'app_not_installed':QT_TRANSLATE_NOOP('Bridge','Aplicativo não instalado neste computador; nada foi aberto'),'launch_failed':QT_TRANSLATE_NOOP('Bridge','Não consegui iniciar o aplicativo; nada foi confirmado'),
    'launch_unconfirmed':QT_TRANSLATE_NOOP('Bridge','Pedi para abrir, mas o aplicativo não apareceu em 5 s; nada foi confirmado'),'volume_unavailable':QT_TRANSLATE_NOOP('Bridge','Não consegui ler o volume do computador; nada foi alterado'),
    'volume_unverified':QT_TRANSLATE_NOOP('Bridge','O volume lido não bate com o pedido; a mudança não foi confirmada'),'command_failed':QT_TRANSLATE_NOOP('Bridge','Comando não concluído; nada foi confirmado'),
    'app_unavailable':QT_TRANSLATE_NOOP('Bridge','Aplicativo fora da lista fixa; nada foi aberto'),'denied':QT_TRANSLATE_NOOP('Bridge','Valor fora da faixa de 0 a 100%; nada foi alterado'),'unsupported':QT_TRANSLATE_NOOP('Bridge','Comando não entendido; nada foi executado')})

def real_action_line(last):
    """State line of the last host action: 'Abriu: brave às 14:32 · confirmado'. Local time, HH:MM."""
    if not isinstance(last,dict):return QCoreApplication.translate('Bridge','Nenhuma ação no computador desde o início do Core')
    when=datetime.datetime.fromtimestamp(last['at_ms']/1000).strftime('%H:%M')
    if not last['ok']:return _fill(QCoreApplication.translate('Bridge','Não concluiu às %1; nada foi confirmado'),when)
    label=_tr(REAL_KIND_TEXT[last['kind']])+(f": {last['app']}" if last['app'] else '')
    state=QCoreApplication.translate('Bridge','confirmado') if last['verified'] else QCoreApplication.translate('Bridge','sem confirmação')
    return _fill(QCoreApplication.translate('Bridge','%1 às %2 · %3'),label,when,state)

def real_actions_state(enabled,last):
    if enabled is not True:return QCoreApplication.translate('Bridge','Desligado: os comandos usam só a simulação interna, sem efeito no computador')
    return real_action_line(last)

def live_output_text(live):
    if not live:return QCoreApplication.translate('Bridge','Saída ao vivo: sem informação do Core')
    if not live.get('enabled'):return QCoreApplication.translate('Bridge','Saída ao vivo: desligada — a resposta usa a saída virtual')
    if live.get('output_state')=='playing':return QCoreApplication.translate('Bridge','Saída ao vivo: reproduzindo')
    if live.get('output_state')=='error':
        error=live.get('last_error') or ''
        return QCoreApplication.translate('Bridge','Saída ao vivo: erro: ')+(LIVE_ERROR_MESSAGES.get(error,QCoreApplication.translate('Bridge','falha na reprodução')) if error.startswith('player_') else QCoreApplication.translate('Bridge','falha na reprodução'))
    return QCoreApplication.translate('Bridge','Saída ao vivo: em espera')
# A9 texts (Portuguese only). Numbers are shown with a decimal comma; zones carry words as well as colour.
LIVE_WARNING_TEXTS=_Messages({
    'no_frames':QT_TRANSLATE_NOOP('Bridge','Nenhum áudio chegando do microfone.'),
    'very_quiet':QT_TRANSLATE_NOOP('Bridge','Sinal muito baixo: aproxime-se ou aumente o ganho do microfone no sistema.'),
    'clipping':QT_TRANSLATE_NOOP('Bridge','O sinal está saturando (distorção): afaste-se do microfone ou reduza o ganho.'),
})
PROBE_VERDICT_TEXTS=_Messages({'ok':QT_TRANSLATE_NOOP('Bridge','Captando bem'),'quiet':QT_TRANSLATE_NOOP('Bridge','Sinal baixo'),'noisy':QT_TRANSLATE_NOOP('Bridge','Ruído alto'),'silent':QT_TRANSLATE_NOOP('Bridge','Silêncio'),'error':QT_TRANSLATE_NOOP('Bridge','Erro')})

def very_noisy_text(floor):return _fill(QCoreApplication.translate('Bridge','Este microfone tem muito ruído de fundo (%1 dBFS). Teste outro dispositivo.'),round(floor))
ZONE_TEXTS=_Messages({'hot':QT_TRANSLATE_NOOP('Bridge','Sinal alto: risco de distorção'),'low':QT_TRANSLATE_NOOP('Bridge','Sinal baixo'),'ok':QT_TRANSLATE_NOOP('Bridge','Sinal normal')})
FLOOR_TEXTS=_Messages({'bad':QT_TRANSLATE_NOOP('Bridge','ruído alto'),'warn':QT_TRANSLATE_NOOP('Bridge','ruído moderado'),'ok':QT_TRANSLATE_NOOP('Bridge','ruído baixo')})

def live_hint_view(live,online=True):
    """Hoje's state line while the microphone is on: listening, speech heard but not recognised (hint: say the phrase)."""
    if not online or not live or live.get('enabled') is not True or live.get('input_state')!='capturing':return {'line':'','hint':''}
    if (live.get('level') or {}).get('speech_unmatched') is True:return {'line':QCoreApplication.translate('Bridge','Ouvindo… fala detectada mas nenhuma frase reconhecida'),'hint':QCoreApplication.translate('Bridge','Diga: Hey Gideon')}
    return {'line':QCoreApplication.translate('Bridge','Ouvindo…'),'hint':''}
OPS.update({
    'listen_start':('listen',QT_TRANSLATE_NOOP('Bridge','Escuta iniciada: fale agora')),
})
PENDING.update({
    'listen_start':QT_TRANSLATE_NOOP('Bridge','Pedindo escuta ao Core…'),
})
OPS.update({
    # B16 (docs/A6-live-audio.md): device list, and the Core defaults restore (the Core keeps config.json.bak).
    'audio_devices':('audio',QT_TRANSLATE_NOOP('Bridge','Lista de dispositivos atualizada')),
})
PENDING.update({
    'audio_devices':QT_TRANSLATE_NOOP('Bridge','Consultando dispositivos no Core…'),
})
OPS.update({
    # A9 probe of one input: 3 s of the microphone; the message says so, and the result comes in audio.probe.
    'audio_probe':('audio',QT_TRANSLATE_NOOP('Bridge','Teste iniciado: o microfone será usado por 3 segundos')),
})
PENDING.update({
    'audio_probe':QT_TRANSLATE_NOOP('Bridge','Iniciando o teste de 3 s no Core…'),
})
OPS.update({
    # A13 microphone assistant: 2 s from each listed input, one at a time; nothing is saved and the system default is not changed.
    'audio_recommend_input':('audio',QT_TRANSLATE_NOOP('Bridge','Verificação dos microfones iniciada: 2 s em cada entrada; nada é salvo')),
})
PENDING.update({
    'audio_recommend_input':QT_TRANSLATE_NOOP('Bridge','Verificando os microfones no Core…'),
})
OPS.update({
    # A6 consent for the live microphone (docs/A6-live-audio.md): one op, read back from preferences.live_audio and audio.live.restart_required.
    'live_audio_preference':('prefs',QT_TRANSLATE_NOOP('Bridge','Escuta do microfone salva no Core; reinicie o Core para aplicar')),
})
PENDING.update({
    'live_audio_preference':QT_TRANSLATE_NOOP('Bridge','Salvando a escuta do microfone no Core…'),
})
OPS.update({
    # A11 consent for host actions (docs/A11-real-actions-test.md): applies at once; busy while a voice session or a command runs.
    'real_actions_preference':('prefs',QT_TRANSLATE_NOOP('Bridge','Ações no computador salvas no Core')),
})
PENDING.update({
    'real_actions_preference':QT_TRANSLATE_NOOP('Bridge','Salvando as ações no computador no Core…'),
})
