"""LLM model, agent and chat texts."""
from PySide6.QtCore import QT_TRANSLATE_NOOP
from translations import _Messages
from msgs_misc import OPS,PENDING

AGENT_STATE_LABELS=_Messages({'thinking':QT_TRANSLATE_NOOP('Bridge','Pensando'),'waiting_tool':QT_TRANSLATE_NOOP('Bridge','Executando ferramenta'),'awaiting_approval':QT_TRANSLATE_NOOP('Bridge','Aguardando sua aprovação'),'done':QT_TRANSLATE_NOOP('Bridge','Concluído'),'failed':QT_TRANSLATE_NOOP('Bridge','Falhou'),'aborted':QT_TRANSLATE_NOOP('Bridge','Abortado'),'blocked':QT_TRANSLATE_NOOP('Bridge','Bloqueado')})
FEATURE_LABELS=_Messages({'supported':QT_TRANSLATE_NOOP('Bridge','Suportado'),'unsupported':QT_TRANSLATE_NOOP('Bridge','Não suportado'),'unknown':QT_TRANSLATE_NOOP('Bridge','Desconhecido')})
# Text of each status code, in the UI language. The Core never sends these words; the bridge owns them.
MODEL_STATUS_TEXTS=_Messages({'testing':QT_TRANSLATE_NOOP('Bridge','Em teste'),'no_config':QT_TRANSLATE_NOOP('Bridge','Sem modelo selecionado'),
    'no_key':QT_TRANSLATE_NOOP('Bridge','Sem chave'),'no_consent':QT_TRANSLATE_NOOP('Bridge','Sem consentimento'),
    'no_model_data':QT_TRANSLATE_NOOP('Bridge','Sem dados do modelo'),'tool_use_unsupported':QT_TRANSLATE_NOOP('Bridge','INDISPONÍVEL: tool_use não suportado'),
    'available':QT_TRANSLATE_NOOP('Bridge','Disponível')})
CHAT_STATE_LABELS=_Messages({'idle':QT_TRANSLATE_NOOP('Bridge','Em espera'),'waiting':QT_TRANSLATE_NOOP('Bridge','Aguardando resposta'),'streaming':QT_TRANSLATE_NOOP('Bridge','Respondendo'),'done':QT_TRANSLATE_NOOP('Bridge','Concluída'),'error':QT_TRANSLATE_NOOP('Bridge','Erro'),'cancelled':QT_TRANSLATE_NOOP('Bridge','Cancelada')})
# B12: actionable chat errors (Core codes of a failed chat turn). Each banner links to Extensões › Modelos LLM › Provedor e chaves.
CHAT_ERROR_BANNERS=_Messages({'key_missing':QT_TRANSLATE_NOOP('Bridge','Falta a chave do provedor'),'provider_not_configured':QT_TRANSLATE_NOOP('Bridge','Nenhum provedor configurado'),'cloud_not_authorized':QT_TRANSLATE_NOOP('Bridge','Consentimento de nuvem necessário'),'model_unsupported_feature':QT_TRANSLATE_NOOP('Bridge','O modelo atual não suporta o recurso exigido')})
OPS.update({
    'secret_set':('llm',QT_TRANSLATE_NOOP('Bridge','Chave salva pelo Core')),
    'secret_clear':('llm',QT_TRANSLATE_NOOP('Bridge','Chave removida pelo Core')),
    'llm_configure':('llm',QT_TRANSLATE_NOOP('Bridge','Configuração salva pelo Core')),
    'tool_decide':('tools',QT_TRANSLATE_NOOP('Bridge','Decisão enviada ao Core')),
    'agent_start':('agent',QT_TRANSLATE_NOOP('Bridge','Objetivo enviado ao Core')),
    'agent_abort':('agent',QT_TRANSLATE_NOOP('Bridge','Aborto enviado ao Core')),
})
PENDING.update({
    'agent_start':QT_TRANSLATE_NOOP('Bridge','Iniciando agente…'),
    'agent_abort':QT_TRANSLATE_NOOP('Bridge','Enviando aborto ao Core…'),
    'secret_set':QT_TRANSLATE_NOOP('Bridge','Salvando chave no Core…'),
    'secret_clear':QT_TRANSLATE_NOOP('Bridge','Removendo chave no Core…'),
    'llm_configure':QT_TRANSLATE_NOOP('Bridge','Salvando configuração do motor…'),
    'tool_decide':QT_TRANSLATE_NOOP('Bridge','Enviando decisão ao Core…'),
})
