"""Personal areas, wake phrases, diagnostics, language and the op table of the Core requests."""
from PySide6.QtCore import QCoreApplication,QT_TRANSLATE_NOOP
from translations import _tr,_Messages
from msgs_errors import PREFS_DONE

# Portuguese words for the Core state codes shown in the diagnostic line (same words as Main.qml statusLabels).
DIAG_LABELS=_Messages({'unavailable':QT_TRANSLATE_NOOP('Bridge','indisponível'),'starting':QT_TRANSLATE_NOOP('Bridge','iniciando'),'replaying':QT_TRANSLATE_NOOP('Bridge','reproduzindo'),'failed':QT_TRANSLATE_NOOP('Bridge','falhou'),'replay_finished':QT_TRANSLATE_NOOP('Bridge','replay encerrado'),'ready':QT_TRANSLATE_NOOP('Bridge','pronto'),'idle':QT_TRANSLATE_NOOP('Bridge','em espera'),'muted':QT_TRANSLATE_NOOP('Bridge','mudo'),'disabled':QT_TRANSLATE_NOOP('Bridge','desligado'),'speaking':QT_TRANSLATE_NOOP('Bridge','respondendo'),'completed':QT_TRANSLATE_NOOP('Bridge','concluído'),'cancelled':QT_TRANSLATE_NOOP('Bridge','cancelado'),'timed_out':QT_TRANSLATE_NOOP('Bridge','tempo esgotado'),'audio_error':QT_TRANSLATE_NOOP('Bridge','erro de áudio'),'stt_failed':QT_TRANSLATE_NOOP('Bridge','falha na transcrição'),'stt_unavailable':QT_TRANSLATE_NOOP('Bridge','transcrição indisponível'),'transcript_final':QT_TRANSLATE_NOOP('Bridge','transcrição final'),'capture_completed':QT_TRANSLATE_NOOP('Bridge','captura concluída'),'no_speech':QT_TRANSLATE_NOOP('Bridge','sem fala detectada'),'capture_too_long':QT_TRANSLATE_NOOP('Bridge','captura longa demais')})
# Core restart (Diagnóstico > Recuperação): the Core exits 75 after acking; gideon-launch starts it again. The bridge waits this long for the snapshot.
RESTART_TIMEOUT_MS=30000
RESTART_WAIT_TEXT=QT_TRANSLATE_NOOP('Bridge','Reiniciando o Core…')
RESTART_BACK_TEXT=QT_TRANSLATE_NOOP('Bridge','Core reiniciado e conectado de novo')
RESTART_TIMEOUT_TEXT=QT_TRANSLATE_NOOP('Bridge','O Core não voltou em 30 s; use gideon-launch')

def display_wake_entry(entry,settings,active):
    """One row of Configurações › Voz e Wake: the Core entry plus the active switch, sensitivity and labels."""
    setting=next((s for s in settings if s.get('id')==entry['id']),{})
    if entry['custom']:qualification_label=QT_TRANSLATE_NOOP('Bridge','personalizada · não testada') if entry.get('measurement') is None else QT_TRANSLATE_NOOP('Bridge','personalizada · teste sintético')
    else:qualification_label=WAKE_QUALIFICATION_LABELS.get(entry['qualification'],'')
    return {**entry,'active':entry['id'] in active,'sensitivity':setting.get('sensitivity'),'qualification_label':_tr(qualification_label) if entry['custom'] else qualification_label,
            'measurement':entry.get('measurement')}
# Display mapping (round 2). The Core wire values never change; these tables only choose the text the user reads.
# Each table has checks in scripts/test_bridge_protocol.py (class DisplayMapping).
# Real status of each wake phrase qualification (docs/A9, docs/WP7c): Hey Gideon is measured on a synthetic corpus only, and
# the PT/FR native wake needs recordings of the owner's voice, so it is not enabled.
WAKE_QUALIFICATION_LABELS=_Messages({'dev_qualified':QT_TRANSLATE_NOOP('Bridge','qualificada em corpus sintético; microfone real não validado'),'poc_required':QT_TRANSLATE_NOOP('Bridge','não ativado: precisa de gravações da sua voz'),'custom':QT_TRANSLATE_NOOP('Bridge','personalizada · não testada')})
# Frases de ativação: Portuguese for every code the Core returns for the wake phrase ops (src/phrases.rs `code`).
PHRASE_MESSAGES=_Messages({
    'phrase_empty':QT_TRANSLATE_NOOP('Bridge','Digite a frase.'),
    'phrase_too_long':QT_TRANSLATE_NOOP('Bridge','Frase longa demais: use até 40 letras.'),
    'phrase_invalid_characters':QT_TRANSLATE_NOOP('Bridge','Use só letras, espaços e apóstrofo: sem números nem pontuação.'),
    'phrase_needs_two_words':QT_TRANSLATE_NOOP('Bridge','Use de 2 a 4 palavras; uma palavra sozinha é genérica demais.'),
    'phrase_too_many_words':QT_TRANSLATE_NOOP('Bridge','Use no máximo 4 palavras.'),
    'phrase_too_generic':QT_TRANSLATE_NOOP('Bridge','Frase genérica demais: use palavras mais específicas.'),
    'phrase_too_few_tokens':QT_TRANSLATE_NOOP('Bridge','Frase curta demais para o detector: use palavras com mais sons.'),
    'word_not_in_lexicon':QT_TRANSLATE_NOOP('Bridge','Palavra fora do dicionário do detector. Tente outra forma de escrever.'),
    'token_not_in_vocabulary':QT_TRANSLATE_NOOP('Bridge','Som fora do vocabulário do detector.'),
    'lexicon_unavailable':QT_TRANSLATE_NOOP('Bridge','Dicionário do detector indisponível neste pacote: frases personalizadas estão desligadas.'),
    'phrase_duplicate':QT_TRANSLATE_NOOP('Bridge','Essa frase já existe.'),
    'phrase_store_full':QT_TRANSLATE_NOOP('Bridge','Limite de 8 frases personalizadas atingido: remova uma antes.'),
    'phrase_not_found':QT_TRANSLATE_NOOP('Bridge','Frase personalizada não encontrada.'),
    'phrase_in_use':QT_TRANSLATE_NOOP('Bridge','Desative a frase antes de removê-la.'),
    'phrase_unmeasured':QT_TRANSLATE_NOOP('Bridge','Teste a frase antes de ativá-la.'),
    'phrase_measurement_failed':QT_TRANSLATE_NOOP('Bridge','Atenção: o teste sintético desta frase falhou. Ela pode não ser detectada ou disparar sem você falar. Ative só se aceitar esse risco.'),
    'phrase_test_running':QT_TRANSLATE_NOOP('Bridge','Já há um teste em andamento. Aguarde o resultado.'),
    'phrase_test_unavailable':QT_TRANSLATE_NOOP('Bridge','Teste indisponível: a voz de teste ou o dicionário não estão prontos.'),
    'phrase_test_failed':QT_TRANSLATE_NOOP('Bridge','O teste não concluiu. Tente de novo.'),
    'too_many_active_phrases':QT_TRANSLATE_NOOP('Bridge','Escolha até 5 frases ativas.'),
    'invalid_wake_phrases':QT_TRANSLATE_NOOP('Bridge','Lista de frases recusada; nada foi salvo.'),
    'wake_start_failed':QT_TRANSLATE_NOOP('Bridge','O detector não iniciou com essa lista. A lista anterior continua valendo.'),
    'stale_phrase_store':QT_TRANSLATE_NOOP('Bridge','As frases personalizadas mudaram. Atualize a tela e tente de novo.'),
    'phrase_store_error':QT_TRANSLATE_NOOP('Bridge','Não foi possível salvar as frases personalizadas.'),
    # U1: only a safe-mode configuration needs recovery; a pending restart just needs the Core restarted.
    'configuration_not_ready':QT_TRANSLATE_NOOP('Bridge','Esta ação espera o reinício do Core. Reinicie o Core para continuar; a mudança salva já vale.'),
})
PERSONAL_MESSAGES=_Messages({
    'personal_unavailable':QT_TRANSLATE_NOOP('Bridge','Dados pessoais indisponíveis: o armazenamento não abriu. Reinicie o Core.'),
    'stale_revision':QT_TRANSLATE_NOOP('Bridge','Esta tela estava desatualizada: os dados mudaram. Atualize e tente de novo.'),
    'consent_required':QT_TRANSLATE_NOOP('Bridge','Ative a fonte antes de salvar fatos dela.'),
    'retention_never':QT_TRANSLATE_NOOP('Bridge','Histórico desligado (não guardar): nada de conversa é guardado.'),
    'invalid_text':QT_TRANSLATE_NOOP('Bridge','Texto inválido ou vazio.'),
    'memory_full':QT_TRANSLATE_NOOP('Bridge','Limite de fatos atingido: apague um antes.'),
    'invalid_ttl':QT_TRANSLATE_NOOP('Bridge','Prazo inválido: use de 1 a 365 dias.'),
    'unknown_fact':QT_TRANSLATE_NOOP('Bridge','Fato não encontrado.'),
    'confirmation_required':QT_TRANSLATE_NOOP('Bridge','Confirme a ação antes de apagar.'),
    'unknown_soul':QT_TRANSLATE_NOOP('Bridge','Alma não encontrada.'),
    'soul_capacity':QT_TRANSLATE_NOOP('Bridge','Limite de almas atingido: apague uma antes.'),
    'invalid_provenance':QT_TRANSLATE_NOOP('Bridge','Origem da alma inválida para este modo.'),
    'invalid_confidence':QT_TRANSLATE_NOOP('Bridge','Confiança inválida.'),
    'invalid_evidence':QT_TRANSLATE_NOOP('Bridge','Evidência inválida: informe trechos válidos.'),
    'invalid_skill_id':QT_TRANSLATE_NOOP('Bridge','Skill inválida.'),
    'skill_not_enabled':QT_TRANSLATE_NOOP('Bridge','A Skill precisa estar habilitada.'),
    'habit_capacity':QT_TRANSLATE_NOOP('Bridge','Limite de hábitos atingido: remova um antes.'),
    'habit_paused':QT_TRANSLATE_NOOP('Bridge','Hábito pausado: revise antes de executar.'),
    'skill_version_changed':QT_TRANSLATE_NOOP('Bridge','A versão da Skill mudou: revise antes de executar.'),
    'no_previous_version':QT_TRANSLATE_NOOP('Bridge','Não há versão anterior para voltar.'),
    'invalid_inputs':QT_TRANSLATE_NOOP('Bridge','Entradas inválidas para a Skill.'),
    'unknown_habit':QT_TRANSLATE_NOOP('Bridge','Hábito não encontrado.'),
    'unknown_automation':QT_TRANSLATE_NOOP('Bridge','Automação não encontrada.'),
    'automation_capacity':QT_TRANSLATE_NOOP('Bridge','Limite de automações atingido.'),
    'schedule_in_past':QT_TRANSLATE_NOOP('Bridge','O horário já passou: escolha um horário futuro.'),
    'invalid_schedule':QT_TRANSLATE_NOOP('Bridge','Agenda inválida.'),
    'invalid_status':QT_TRANSLATE_NOOP('Bridge','Status inválido.'),
    'automation_done':QT_TRANSLATE_NOOP('Bridge','Automação já concluída.'),
    'automation_paused':QT_TRANSLATE_NOOP('Bridge','Automação pausada: revise antes de retomar.'),
    'unknown_session':QT_TRANSLATE_NOOP('Bridge','Conversa não encontrada.'),
    'conversation_capacity':QT_TRANSLATE_NOOP('Bridge','Limite de conversas atingido: apague uma antes.'),
    'invalid_request':QT_TRANSLATE_NOOP('Bridge','Pedido inválido; nada foi alterado.'),
    'unsupported_version':QT_TRANSLATE_NOOP('Bridge','Versão de pedido não suportada.'),
    'unknown_area':QT_TRANSLATE_NOOP('Bridge','Área desconhecida.'),
    'ledger_invalid':QT_TRANSLATE_NOOP('Bridge','Arquivo pessoal corrompido: a área ficou indisponível.'),
    'ledger_unreadable':QT_TRANSLATE_NOOP('Bridge','Não foi possível ler o arquivo pessoal (permissões ou link). Nada foi alterado.'),
    'ledger_write_failed':QT_TRANSLATE_NOOP('Bridge','Não foi possível gravar o arquivo pessoal. Nada foi alterado.'),
    'ledger_full':QT_TRANSLATE_NOOP('Bridge','Arquivo pessoal cheio: apague dados antes.'),
    'personal_dir_unavailable':QT_TRANSLATE_NOOP('Bridge','Pasta de dados pessoais indisponível.'),
    'core_unavailable':QT_TRANSLATE_NOOP('Bridge','Core indisponível agora.'),
    'deferred':QT_TRANSLATE_NOOP('Bridge','Adiado: o motor de Skills está ocupado. Tente de novo.'),
    'needs_review':QT_TRANSLATE_NOOP('Bridge','Revise o hábito ou a automação antes de executar.'),
    'reply_too_large':QT_TRANSLATE_NOOP('Bridge','Resultado grande demais para a tela. Use Exportar para guardar os dados em arquivo.'),
    'personal_export_failed':QT_TRANSLATE_NOOP('Bridge','Não foi possível gravar a exportação. Nada foi apagado.'),
    'live_audio_disabled':QT_TRANSLATE_NOOP('Bridge','Escuta do microfone desligada: ative o microfone em Configurações › Dispositivos.'),
    'capture_unavailable':QT_TRANSLATE_NOOP('Bridge','Captura do microfone não está ativa neste Core.'),
    'queued':QT_TRANSLATE_NOOP('Bridge','Na fila: o pedido segue quando a sessão de voz terminar.'),
    'chat_failed':QT_TRANSLATE_NOOP('Bridge','O pedido da fila não pôde ser executado.'),
    'stt_unavailable':QT_TRANSLATE_NOOP('Bridge','Transcrição indisponível agora.'),
    'busy':QT_TRANSLATE_NOOP('Bridge','Ocupado: aguarde o término da ação atual.'),
})
LANGUAGE_LABELS=_Messages({'EN':QT_TRANSLATE_NOOP('Bridge','inglês')})
RECEIPT_PREFIXES=(('Sandbox app process verified: ',QT_TRANSLATE_NOOP('Bridge','Processo do app verificado no sandbox: ')),)

def display_receipt(text):
    """Command receipt text as the user reads it: known Core prefixes are translated, anything else is shown as sent."""
    if isinstance(text,str):
        for raw,shown in RECEIPT_PREFIXES:
            if text.startswith(raw):return _tr(shown)+text[len(raw):]
    return text

def display_wake_choice(choice):
    """A wake phrase row for QML: the Core fields plus the qualification label (empty for an unknown value)."""
    return {**choice,'qualification_label':WAKE_QUALIFICATION_LABELS.get(choice.get('qualification'),'')}
OPS={}
OPS.update({
    # op -> (result channel, done message or builder). One table drives every Core answer.
    'preferences':('prefs',PREFS_DONE),
    'rollback_preferences':('prefs',PREFS_DONE),
    'select_wake':('prefs',PREFS_DONE),
    'select_wake_phrases':('prefs',PREFS_DONE),
    'wake_phrase_validate':('phrase',lambda _target:QCoreApplication.translate('Bridge','Frase verificada')),
    'wake_phrase_add':('phrase',QT_TRANSLATE_NOOP('Bridge','Frase salva: faça o teste antes de ativar')),
    'wake_phrase_remove':('phrase',QT_TRANSLATE_NOOP('Bridge','Frase personalizada removida')),
    'wake_phrase_test':('phrase',QT_TRANSLATE_NOOP('Bridge','Teste sintético iniciado: o resultado aparece na lista')),
    'feedback_preferences':('prefs',PREFS_DONE),
    'recover_configuration':('prefs',QT_TRANSLATE_NOOP('Bridge','Configuração recuperada; reinício necessário')),
    'text':('text',QT_TRANSLATE_NOOP('Bridge','Texto enviado')),
})
PENDING={}
PENDING.update({
    'text':QT_TRANSLATE_NOOP('Bridge','Enviando texto ao Core'),
})
OPS.update({
    # C-wire: restart is answered by the Core, then the socket drops (see _restart_ack); the plugin clear answers on the plugin channel.
    'core_restart':('core',QT_TRANSLATE_NOOP('Bridge','Reinício pedido ao Core')),
    'virtual_wake':('wake',QT_TRANSLATE_NOOP('Bridge','Wake de teste enviado ao Core')),
})
PENDING.update({
    'core_restart':QT_TRANSLATE_NOOP('Bridge','Pedindo reinício ao Core…'),
    'virtual_wake':QT_TRANSLATE_NOOP('Bridge','Enviando wake de teste…'),
})
OPS.update({
    'preferences_restore_defaults':('prefs',QT_TRANSLATE_NOOP('Bridge','Padrões do Core restaurados; cópia anterior em config.json.bak')),
})
PENDING.update({
    'preferences_restore_defaults':QT_TRANSLATE_NOOP('Bridge','Restaurando padrões do Core…'),
})
OPS.update({
    # Idiomas (Frente 2): one op for the STT list and the TTS language/voice; applied at the next Core start.
    'language_preference':('prefs',QT_TRANSLATE_NOOP('Bridge','Idiomas salvos no Core; reinicie o Core para aplicar')),
})
PENDING.update({
    'language_preference':QT_TRANSLATE_NOOP('Bridge','Salvando idiomas no Core…'),
})
OPS.update({
    # CFG-03: verifies the packaged models of one bundled language (hash per file) and activates them in the Core state. No download.
    'language_install':('prefs',QT_TRANSLATE_NOOP('Bridge','Modelos verificados pelo hash e ativados no Core; a escolha vale na próxima fala')),
})
PENDING.update({
    'language_install':QT_TRANSLATE_NOOP('Bridge','Verificando os modelos do idioma no pacote…'),
})
OPS.update({
    # CFG-04 retention: applies at once; `never` also removes the audit trail (purge on commit). DIAG-02 developer mode: a plain switch.
    'history_retention_preference':('prefs',QT_TRANSLATE_NOOP('Bridge','Retenção do histórico salva no Core; vale já')),
})
PENDING.update({
    'history_retention_preference':QT_TRANSLATE_NOOP('Bridge','Salvando a retenção do histórico no Core…'),
})
OPS.update({
    'developer_mode_preference':('prefs',QT_TRANSLATE_NOOP('Bridge','Modo desenvolvedor salvo no Core')),
})
PENDING.update({
    'developer_mode_preference':QT_TRANSLATE_NOOP('Bridge','Salvando o modo desenvolvedor no Core…'),
})
OPS.update({
    # WP-20: the interface language is a Core preference; the UI switches live when the snapshot reports it.
    'ui_language_preference':('prefs',QT_TRANSLATE_NOOP('Bridge','Idioma da interface salvo no Core')),
})
PENDING.update({
    'ui_language_preference':QT_TRANSLATE_NOOP('Bridge','Salvando o idioma da interface no Core…'),
})
