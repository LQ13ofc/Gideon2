"""Skills, Hub and plugin capability texts."""
from PySide6.QtCore import QCoreApplication,QT_TRANSLATE_NOOP
from translations import _fill,_Messages
from msgs_misc import OPS,PENDING

HUB_UPLOAD_MESSAGES=_Messages({'busy':QT_TRANSLATE_NOOP('Bridge','Importação indisponível agora: o Core precisa estar conectado, sem sessão de voz e com o catálogo verificado'),
    'entry':QT_TRANSLATE_NOOP('Bridge','Importe só o pacote de um plugin com permissões aprovadas e sem pacote guardado; nada foi enviado'),
    'path':QT_TRANSLATE_NOOP('Bridge','Escolha um arquivo comum, por caminho absoluto; links simbólicos não são aceitos; nada foi enviado'),
    'unreadable':QT_TRANSLATE_NOOP('Bridge','Não consegui abrir o arquivo do pacote; nada foi enviado'),
    'size':QT_TRANSLATE_NOOP('Bridge','O tamanho do arquivo não bate com o tamanho do catálogo; nada foi enviado'),
    'sending':QT_TRANSLATE_NOOP('Bridge','Enviando pacote ao Core…'),
    'progress':QT_TRANSLATE_NOOP('Bridge','Enviando pacote: %1 de %2 bytes'),
    'staged':QT_TRANSLATE_NOOP('Bridge','Pacote verificado e guardado pelo Core; ainda não instalado.'),
    'hub_import_missing':QT_TRANSLATE_NOOP('Bridge','O Core não abriu a importação; nada foi guardado'),
    'cancelled':QT_TRANSLATE_NOOP('Bridge','Importação cancelada; nada foi guardado'),
    'core_offline':QT_TRANSLATE_NOOP('Bridge','Core desconectado durante a importação; nada foi guardado')})
# Validator reasons (skill_invalid:<reason>, docs/S4.md D1). Each one has a Portuguese message in CODE_MESSAGES.
SKILL_REASON_MESSAGES=_Messages({
    'out_of_scope':QT_TRANSLATE_NOOP('Bridge','Passo chama capability fora das dependências declaradas'),
    'exfiltration':QT_TRANSLATE_NOOP('Bridge','Manifest tenta enviar dados para fora: caminho, URL, shell ou segredo'),
    'cycle':QT_TRANSLATE_NOOP('Bridge','Ciclo entre skills; recursão recusada'),
    'depth':QT_TRANSLATE_NOOP('Bridge','Skill aninhada além do limite de profundidade (2)'),
    'missing_dependency':QT_TRANSLATE_NOOP('Bridge','Dependência ausente: plugin ou ferramenta indisponível'),
    'oversize':QT_TRANSLATE_NOOP('Bridge','Manifest ou campo acima do limite de tamanho'),
    'unknown_key':QT_TRANSLATE_NOOP('Bridge','Campo desconhecido no manifest'),
    'schema_version':QT_TRANSLATE_NOOP('Bridge','Versão de esquema não suportada (use 1)'),
    'duplicate_id':QT_TRANSLATE_NOOP('Bridge','Já existe uma skill com este id'),
    'permissions_escalated':QT_TRANSLATE_NOOP('Bridge','Esta versão pede mais permissões que a anterior; aprove de novo'),
    'min_runtime':QT_TRANSLATE_NOOP('Bridge','Esta skill exige um Gideon mais novo'),
    'reserved_capability':QT_TRANSLATE_NOOP('Bridge','Capability reservada da Base; a skill não pode usá-la'),
    'grant_field':QT_TRANSLATE_NOOP('Bridge','Campo de permissão não é permitido dentro de passos'),
    'unknown_step':QT_TRANSLATE_NOOP('Bridge','Referência a passo inexistente'),
    'forward_ref':QT_TRANSLATE_NOOP('Bridge','Referência a passo que ainda não executou'),
    'bad_template':QT_TRANSLATE_NOOP('Bridge','Template inválido: use só ${input.x} ou ${steps.id.campo}'),
    'too_many_steps':QT_TRANSLATE_NOOP('Bridge','Mais passos que o limite (16)'),
    'too_many_deps':QT_TRANSLATE_NOOP('Bridge','Mais dependências que o limite (8)'),
    'bad_manifest':QT_TRANSLATE_NOOP('Bridge','Manifest malformado'),
    'bad_id':QT_TRANSLATE_NOOP('Bridge','Id de skill inválido'),
    'bad_version':QT_TRANSLATE_NOOP('Bridge','Versão inválida: use x.y.z'),
    'bad_publisher':QT_TRANSLATE_NOOP('Bridge','Publisher inválido'),
    'hash_mismatch':QT_TRANSLATE_NOOP('Bridge','Hash não confere: pacote adulterado'),
    'corrupt_package':QT_TRANSLATE_NOOP('Bridge','Pacote corrompido'),
    'symlink':QT_TRANSLATE_NOOP('Bridge','Link simbólico no pacote; recusado'),
    'file_too_large':QT_TRANSLATE_NOOP('Bridge','Arquivo grande demais para importar (limite 64 KiB)'),
    'path_not_allowed':QT_TRANSLATE_NOOP('Bridge','Arquivo fora da pasta de importação'),
    'unverified_publisher':QT_TRANSLATE_NOOP('Bridge','Publisher não verificado'),
})
# Operation codes the Core answers with for skill ops (not validator reasons). Codes shared with other channels reuse their CODE_MESSAGES text.
SKILL_OP_MESSAGES=_Messages({
    'stale_skill_revision':QT_TRANSLATE_NOOP('Bridge','Skills mudaram no Core; atualize e tente de novo'),
    'missing_dependency':QT_TRANSLATE_NOOP('Bridge','Dependência ausente: execução bloqueada antes de qualquer passo'),
    'skill_busy':QT_TRANSLATE_NOOP('Bridge','Já existe uma skill em execução; aguarde ou cancele'),
    'unknown_skill':QT_TRANSLATE_NOOP('Bridge','Skill desconhecida ou já removida'),
    'unknown_skill_run':QT_TRANSLATE_NOOP('Bridge','Execução de skill desconhecida ou já encerrada'),
    'skill_not_enabled':QT_TRANSLATE_NOOP('Bridge','Skill não está habilitada; nada foi executado'),
    'skill_not_approved':QT_TRANSLATE_NOOP('Bridge','Aprove a skill antes de habilitar ou executar'),
    'not_pending':QT_TRANSLATE_NOOP('Bridge','Este passo não está aguardando decisão'),
    'unknown_step':QT_TRANSLATE_NOOP('Bridge','Passo desconhecido ou fora de ordem'),
    'invalid_skill_input':QT_TRANSLATE_NOOP('Bridge','Entrada da skill inválida: confira os campos e os tipos'),
    'invalid_manifest':QT_TRANSLATE_NOOP('Bridge','Manifest inválido: objeto JSON de até 16 KiB'),
    'duplicate_skill':QT_TRANSLATE_NOOP('Bridge','Já existe uma skill com este id'),
    'undo_failed':QT_TRANSLATE_NOOP('Bridge','Desfazer um passo falhou; confira o efeito manualmente'),
    'rolled_back':QT_TRANSLATE_NOOP('Bridge','Execução revertida: os passos concluídos foram desfeitos'),
    'invalid_import':QT_TRANSLATE_NOOP('Bridge','Pacote de importação inválido'),
    'import_not_found':QT_TRANSLATE_NOOP('Bridge','Pacote não encontrado na pasta de importação'),
    'stale_import':QT_TRANSLATE_NOOP('Bridge','A pré-visualização mudou; importe de novo'),
})
PENDING_SKILL_DRAFT=QT_TRANSLATE_NOOP('Bridge','Gerando skill com o LLM…')
HUB_REASON_LABELS=_Messages({'ledger_missing':QT_TRANSLATE_NOOP('Bridge','registro de aprovações ausente'),'ledger_invalid':QT_TRANSLATE_NOOP('Bridge','registro de aprovações inválido')})

def hub_storage(hub):
    """Catalog storage for Recuperação (B9). The hub view has no storage_error field, so the screen reports that as not informed."""
    if not hub:return {'state':'none','reason':'','orphans':None,'repository':'','catalogSha':''}
    quarantined=hub.get('status')=='quarantined'
    return {'state':'quarantined' if quarantined else 'verified','reason':HUB_REASON_LABELS.get(hub.get('reason'),'') if quarantined else '',
            'orphans':hub.get('orphans'),'repository':hub.get('repository') or '','catalogSha':(hub.get('catalog_sha256') or '')[:12]}
OPS.update({
    'hub_abort':('hub',QT_TRANSLATE_NOOP('Bridge','Importação cancelada')),
    'hub_approve':('hub',lambda target:_fill(QCoreApplication.translate('Bridge','Permissões aprovadas: %1'),target)),
    'hub_install':('hub',QT_TRANSLATE_NOOP('Bridge','Plugin instalado (desativado)')),
    'hub_rollback':('hub',QT_TRANSLATE_NOOP('Bridge','Versão revertida')),
    'hub_remove':('hub',QT_TRANSLATE_NOOP('Bridge','Plugin removido')),
    'plugin_enable':('plugin',QT_TRANSLATE_NOOP('Bridge','Plugin ativado')),
    'plugin_disable':('plugin',QT_TRANSLATE_NOOP('Bridge','Plugin desativado')),
    'plugin_revoke':('plugin',QT_TRANSLATE_NOOP('Bridge','Permissões revogadas; plugin desativado')),
    'capability_invoke':('plugin',None),
    'capability_cancel':('plugin',QT_TRANSLATE_NOOP('Bridge','Cancelamento enviado')),
    # S4 skills: the Core's ack code is the result; validator reasons arrive as skill_invalid:<reason>.
    'skill_validate':('skills',QT_TRANSLATE_NOOP('Bridge','Manifest válido; nada foi gravado')),
    'skill_save_draft':('skills',QT_TRANSLATE_NOOP('Bridge','Rascunho salvo no Core')),
    'skill_dry_run':('skills',QT_TRANSLATE_NOOP('Bridge','Simulação concluída; skill marcada como testada')),
    'skill_approve':('skills',QT_TRANSLATE_NOOP('Bridge','Skill aprovada')),
    'skill_enable':('skills',QT_TRANSLATE_NOOP('Bridge','Skill habilitada')),
    'skill_disable':('skills',QT_TRANSLATE_NOOP('Bridge','Skill desabilitada')),
    'skill_rollback':('skills',QT_TRANSLATE_NOOP('Bridge','Versão anterior restaurada')),
    'skill_remove':('skills',QT_TRANSLATE_NOOP('Bridge','Skill removida')),
    'skill_run':('skills',QT_TRANSLATE_NOOP('Bridge','Execução iniciada')),
    'skill_decide':('skills',QT_TRANSLATE_NOOP('Bridge','Decisão enviada ao Core')),
    'skill_cancel':('skills',QT_TRANSLATE_NOOP('Bridge','Cancelamento enviado')),
    'skill_export':('skills',QT_TRANSLATE_NOOP('Bridge','Pacote exportado; publisher não verificado')),
    'skill_import':('skills',QT_TRANSLATE_NOOP('Bridge','Pré-visualização de importação pronta')),
    'skill_import_confirm':('skills',QT_TRANSLATE_NOOP('Bridge','Skill importada como rascunho; aprove antes de usar')),
})
PENDING.update({
    'hub_approve':QT_TRANSLATE_NOOP('Bridge','Enviando aprovação ao Core'),
    'hub_abort':QT_TRANSLATE_NOOP('Bridge','Enviando cancelamento ao Core'),
    'hub_install':QT_TRANSLATE_NOOP('Bridge','Instalando no Core'),
    'hub_rollback':QT_TRANSLATE_NOOP('Bridge','Revertendo no Core'),
    'hub_remove':QT_TRANSLATE_NOOP('Bridge','Removendo no Core'),
    'plugin_enable':QT_TRANSLATE_NOOP('Bridge','Ativando plugin…'),
    'plugin_disable':QT_TRANSLATE_NOOP('Bridge','Desativando plugin…'),
    'plugin_revoke':QT_TRANSLATE_NOOP('Bridge','Revogando permissões…'),
    'capability_invoke':QT_TRANSLATE_NOOP('Bridge','Invocando capability…'),
    'capability_cancel':QT_TRANSLATE_NOOP('Bridge','Cancelando capability…'),
    'skill_validate':QT_TRANSLATE_NOOP('Bridge','Validando manifest no Core…'),
    'skill_save_draft':QT_TRANSLATE_NOOP('Bridge','Salvando rascunho no Core…'),
    'skill_dry_run':QT_TRANSLATE_NOOP('Bridge','Simulando skill no Core…'),
    'skill_approve':QT_TRANSLATE_NOOP('Bridge','Aprovando skill no Core…'),
    'skill_enable':QT_TRANSLATE_NOOP('Bridge','Habilitando skill no Core…'),
    'skill_disable':QT_TRANSLATE_NOOP('Bridge','Desabilitando skill no Core…'),
    'skill_rollback':QT_TRANSLATE_NOOP('Bridge','Revertendo versão no Core…'),
    'skill_remove':QT_TRANSLATE_NOOP('Bridge','Removendo skill no Core…'),
    'skill_run':QT_TRANSLATE_NOOP('Bridge','Iniciando skill no Core…'),
    'skill_decide':QT_TRANSLATE_NOOP('Bridge','Enviando decisão do passo ao Core…'),
    'skill_cancel':QT_TRANSLATE_NOOP('Bridge','Cancelando skill no Core…'),
    'skill_export':QT_TRANSLATE_NOOP('Bridge','Exportando pacote pelo Core…'),
    'skill_import':QT_TRANSLATE_NOOP('Bridge','Lendo pacote pelo Core…'),
    'skill_import_confirm':QT_TRANSLATE_NOOP('Bridge','Importando como rascunho pelo Core…'),
})
OPS.update({
    'plugin_settings_clear':('plugin',QT_TRANSLATE_NOOP('Bridge','Dados do plugin apagados')),
    'registry_plan':('registry',QT_TRANSLATE_NOOP('Bridge','Rota planejada; nada foi executado')),
    'registry_allow_visual':('registry',QT_TRANSLATE_NOOP('Bridge','Fallback visual atualizado pelo Core')),
})
PENDING.update({
    'plugin_settings_clear':QT_TRANSLATE_NOOP('Bridge','Apagando dados do plugin…'),
    'registry_plan':QT_TRANSLATE_NOOP('Bridge','Planejando rota no Core…'),
    'registry_allow_visual':QT_TRANSLATE_NOOP('Bridge','Atualizando fallback visual no Core…'),
})
