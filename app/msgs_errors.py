"""Core error codes and the general failure texts. Codes stay as they are; only the text is translated."""
from PySide6.QtCore import QT_TRANSLATE_NOOP
from translations import _Messages

PREFS_DONE=QT_TRANSLATE_NOOP('Bridge','Preferências salvas pelo Core')
# Core codes and states -> Portuguese UI text. Unknown codes fall back to a visible generic message.
CODE_MESSAGES=_Messages({
    'invalid_message':QT_TRANSLATE_NOOP('Bridge','Mensagem inválida para o Core'),
    'busy':QT_TRANSLATE_NOOP('Bridge','Core ocupado; tente novamente em instantes'),
    'invalid_text':QT_TRANSLATE_NOOP('Bridge','Texto inválido: use 1 a 512 bytes, sem quebras de linha'),
    'input_disabled':QT_TRANSLATE_NOOP('Bridge','Entrada de texto indisponível no momento'),
    'stale_hub_revision':QT_TRANSLATE_NOOP('Bridge','Catálogo mudou; atualize e tente de novo'),
    'hub_import_busy':QT_TRANSLATE_NOOP('Bridge','Importação do catálogo em andamento'),
    'permissions_not_approved':QT_TRANSLATE_NOOP('Bridge','Aprove as permissões antes de ativar'),
    'capability_unavailable':QT_TRANSLATE_NOOP('Bridge','Capability indisponível no momento'),
    'stale_plugin_revision':QT_TRANSLATE_NOOP('Bridge','Estado do plugin mudou; atualize e tente de novo'),
    'wake_not_qualified':QT_TRANSLATE_NOOP('Bridge','Frase de wake sem qualificação aprovada'),
    'plugin_not_runnable':QT_TRANSLATE_NOOP('Bridge','Plugin não pode ser executado'),
    'plugin_crashed':QT_TRANSLATE_NOOP('Bridge','Plugin encerrou com falha'),
    'timed_out':QT_TRANSLATE_NOOP('Bridge','Tempo esgotado'),
    'timeout':QT_TRANSLATE_NOOP('Bridge','Tempo do provedor esgotado'),
    'cancelled':QT_TRANSLATE_NOOP('Bridge','Cancelado'),
    'invoke_cancelled':QT_TRANSLATE_NOOP('Bridge','Cancelado'),
    'capture_completed':QT_TRANSLATE_NOOP('Bridge','Captura concluída'),
    'replaying':QT_TRANSLATE_NOOP('Bridge','Reprodução em andamento'),
    # Preferências do app e do Core (app/uisettings.py e preferências da ponte).
    'stale_preferences':QT_TRANSLATE_NOOP('Bridge','Configurações mudaram no Core; atualize e tente de novo'),
    'invalid_preferences':QT_TRANSLATE_NOOP('Bridge','Preferências recusadas pelo Core: valor inválido; nada foi salvo'),
    'invalid_languages':QT_TRANSLATE_NOOP('Bridge','Idiomas recusados: escolha de 1 a 3 idiomas válidos para escuta e uma voz de fala; nada foi salvo'),
    'language_not_installed':QT_TRANSLATE_NOOP('Bridge','Idioma ainda não instalado: o download depende da aprovação do dono; nada foi salvo'),
    'language_pack_unavailable':QT_TRANSLATE_NOOP('Bridge','Modelos do idioma ausentes ou diferentes do pacote; nada foi ativado'),
    'language_unsupported':QT_TRANSLATE_NOOP('Bridge','Idioma sem suporte nesta versão; nada foi salvo'),
    'preferences_storage_error':QT_TRANSLATE_NOOP('Bridge','Preferências indisponíveis: o arquivo de configuração não pôde ser lido ou gravado'),
    'preferences_unavailable':QT_TRANSLATE_NOOP('Bridge','Preferências indisponíveis agora; tente quando o Gideon estiver em espera'),
    'consent_required':QT_TRANSLATE_NOOP('Bridge','Escuta do microfone não ativada: a confirmação não chegou ao Core; nada foi alterado'),
    # C1: LLM engine, secrets and tool proposals (Core codes from src/llmcfg.rs, src/core.rs, src/tools.rs).
    'key_missing':QT_TRANSLATE_NOOP('Bridge','Chave ausente para este provedor'),
    'provider_not_configured':QT_TRANSLATE_NOOP('Bridge','Provedor não configurado'),
    'cloud_not_authorized':QT_TRANSLATE_NOOP('Bridge','Envio à nuvem não autorizado; marque o consentimento em Motor LLM'),
    'permission_denied':QT_TRANSLATE_NOOP('Bridge','Permissão de rede do plugin negada'),
    'http_error':QT_TRANSLATE_NOOP('Bridge','Erro HTTP do provedor'),
    'response_too_large':QT_TRANSLATE_NOOP('Bridge','Resposta do provedor grande demais'),
    'network_unavailable':QT_TRANSLATE_NOOP('Bridge','Rede indisponível para o provedor'),
    'unknown_tool':QT_TRANSLATE_NOOP('Bridge','Ferramenta desconhecida; ação recusada'),
    'invalid_args':QT_TRANSLATE_NOOP('Bridge','Argumentos inválidos; ação recusada'),
    'proposal_expired':QT_TRANSLATE_NOOP('Bridge','Proposta expirou sem decisão'),
    'proposal_denied':QT_TRANSLATE_NOOP('Bridge','Proposta negada; não pode ser autorizada'),
    'already_decided':QT_TRANSLATE_NOOP('Bridge','Proposta já foi decidida'),
    'unknown_proposal':QT_TRANSLATE_NOOP('Bridge','Proposta desconhecida ou encerrada'),
    'invalid_config':QT_TRANSLATE_NOOP('Bridge','Configuração do motor inválida'),
    'stale_llm_revision':QT_TRANSLATE_NOOP('Bridge','Configuração do motor mudou; reabra o diálogo'),
    'invalid_secret':QT_TRANSLATE_NOOP('Bridge','Chave inválida: 8 a 256 caracteres ASCII, sem espaços'),
    'invalid_provider':QT_TRANSLATE_NOOP('Bridge','Provedor desconhecido'),
    'secrets_unavailable':QT_TRANSLATE_NOOP('Bridge','Cofre de chaves indisponível'),
    'secrets_storage_error':QT_TRANSLATE_NOOP('Bridge','Falha ao gravar o cofre de chaves'),
    'llm_storage_error':QT_TRANSLATE_NOOP('Bridge','Falha ao gravar a configuração do motor'),
    'llm_unavailable':QT_TRANSLATE_NOOP('Bridge','Configuração do motor indisponível'),
    'invalid_input':QT_TRANSLATE_NOOP('Bridge','Entrada recusada pelo plugin'),
    'executor_unavailable':QT_TRANSLATE_NOOP('Bridge','Executor de comandos indisponível'),
    'user_denied':QT_TRANSLATE_NOOP('Bridge','Negada pelo usuário'),
    'superseded':QT_TRANSLATE_NOOP('Bridge','Substituída por proposta mais recente'),
    'expired':QT_TRANSLATE_NOOP('Bridge','Expirou sem decisão'),
    'plugin_unavailable':QT_TRANSLATE_NOOP('Bridge','Plugin indisponível'),
    # C2: model manager. Codes from the Core and the llm_engine.models capability (docs/C2.md).
    'model_unsupported_feature':QT_TRANSLATE_NOOP('Bridge','Modelo não suporta o recurso exigido; nada foi enviado ao provedor'),
    'model_not_found':QT_TRANSLATE_NOOP('Bridge','Modelo não encontrado no catálogo; atualize a lista'),
    'model_selftest_failed':QT_TRANSLATE_NOOP('Bridge','Teste do modelo falhou'),
    'settings_unavailable':QT_TRANSLATE_NOOP('Bridge','Armazenamento de configurações do plugin indisponível'),
    'no_lkg':QT_TRANSLATE_NOOP('Bridge','Não há configuração anterior salva para restaurar'),
    # C3: agent runtime codes (AGENT_CODES, docs/C3.md). Keep this list in step with the allowlist above.
    'agent_busy':QT_TRANSLATE_NOOP('Bridge','Já existe um agente em execução; aguarde ou aborte'),
    'unknown_run':QT_TRANSLATE_NOOP('Bridge','Execução do agente desconhecida ou já encerrada'),
    'loop_blocked':QT_TRANSLATE_NOOP('Bridge','O agente repetiu a mesma ação; execução bloqueada'),
    'stale_screen':QT_TRANSLATE_NOOP('Bridge','A tela mudou desde a observação; o agente vai reobservar'),
    'permission_revoked':QT_TRANSLATE_NOOP('Bridge','Permissão da ferramenta revogada; execução bloqueada'),
    'denied_by_user':QT_TRANSLATE_NOOP('Bridge','Negada pelo usuário; nada foi alterado'),
    'revoked':QT_TRANSLATE_NOOP('Bridge','Motor LLM desativado ou revogado; execução encerrada'),
    'max_steps':QT_TRANSLATE_NOOP('Bridge','Limite de passos do agente atingido'),
    'budget_exhausted':QT_TRANSLATE_NOOP('Bridge','Limite de tokens do agente atingido'),
    'deadline_exceeded':QT_TRANSLATE_NOOP('Bridge','Tempo limite da execução do agente atingido'),
    'verification_failed':QT_TRANSLATE_NOOP('Bridge','Verificação após a ação falhou; efeito não confirmado'),
    'awaiting_approval':QT_TRANSLATE_NOOP('Bridge','Aguardando sua aprovação na proposta de ferramenta'),
    'executor_failed':QT_TRANSLATE_NOOP('Bridge','Executor da ferramenta falhou'),
    'aborted':QT_TRANSLATE_NOOP('Bridge','Execução abortada'),
    'verify_failed':QT_TRANSLATE_NOOP('Bridge','Verificação após a ação falhou; efeito não confirmado'),
    'too_many_calls':QT_TRANSLATE_NOOP('Bridge','O modelo propôs mais ferramentas do que o limite por passo; excedentes recusados'),
    'token_budget':QT_TRANSLATE_NOOP('Bridge','Limite de tokens do agente atingido'),
    'run_deadline':QT_TRANSLATE_NOOP('Bridge','Tempo limite da execução do agente atingido'),
    'empty_answer':QT_TRANSLATE_NOOP('Bridge','O modelo respondeu sem texto'),
    'invalid_output':QT_TRANSLATE_NOOP('Bridge','Resposta do modelo fora do formato esperado'),
    'destructive_disabled':QT_TRANSLATE_NOOP('Bridge','Ação destrutiva desativada nesta build; nada foi executado'),
    'app_unavailable':QT_TRANSLATE_NOOP('Bridge','Aplicativo indisponível para a ferramenta'),
    'app_write_failed':QT_TRANSLATE_NOOP('Bridge','Não foi possível gravar a alteração'),
    'denied':QT_TRANSLATE_NOOP('Bridge','Ação recusada pelo Core'),
    'unknown_capability':QT_TRANSLATE_NOOP('Bridge','Capability do motor LLM desconhecida'),
    'plugin_error':QT_TRANSLATE_NOOP('Bridge','Motor LLM retornou erro interno'),
    # C4: perception and action plugins (docs/C4.md). permission_denied and stale_screen read differently in the perception page (PERCEPTION_MESSAGES).
    'opt_in_required':QT_TRANSLATE_NOOP('Bridge','Câmera desligada: ative o opt-in antes de capturar'),
    'unsupported':QT_TRANSLATE_NOOP('Bridge','Backend real não suportado neste ambiente; nada foi executado'),
    'unknown_service':QT_TRANSLATE_NOOP('Bridge','Serviço de percepção indisponível nesta build'),
    'capability_timeout':QT_TRANSLATE_NOOP('Bridge','Plugin de percepção não respondeu no prazo'),
    # B6: the Core refuses the test wake unless it was started with --virtual-input (src/core.rs VirtualWake).
    'virtual_input_disabled':QT_TRANSLATE_NOOP('Bridge','Wake de teste indisponível: o Core foi iniciado sem --virtual-input'),
})
STALE_MESSAGE=QT_TRANSLATE_NOOP('Bridge','Estado mudou; reabra a confirmação')
# Raw Core codes never reach the screen. Unknown codes get one generic sentence; the code is appended only when the advanced setting (behavior.advanced) is on.
GENERIC_FAILURE=QT_TRANSLATE_NOOP('Bridge','Não foi possível concluir a operação.')
CODE_MESSAGES.update({'skill_invalid':QT_TRANSLATE_NOOP('Bridge','Skill recusada pela validação do Core; nada foi gravado'),'model_output_invalid':QT_TRANSLATE_NOOP('Bridge','O modelo não devolveu um manifest JSON válido')})
# Codes of a plugin capability invocation (capability_invoke ack or capability_result error). Others fall back to code_message.
CAPABILITY_MESSAGES=_Messages({'unknown_capability':QT_TRANSLATE_NOOP('Bridge','Capacidade desconhecida ou sem plugin instalado'),'capability_unavailable':QT_TRANSLATE_NOOP('Bridge','Plugin desativado ou não está em execução'),
    'invalid_input':QT_TRANSLATE_NOOP('Bridge','Entrada recusada: objeto JSON inválido ou acima do limite'),'busy':QT_TRANSLATE_NOOP('Bridge','Outra capacidade está em execução; aguarde'),'invoke_cancelled':QT_TRANSLATE_NOOP('Bridge','Invocação cancelada'),'cancelled':QT_TRANSLATE_NOOP('Bridge','Invocação cancelada'),
    'capability_timeout':QT_TRANSLATE_NOOP('Bridge','Plugin não respondeu no prazo'),'timeout':QT_TRANSLATE_NOOP('Bridge','Tempo esgotado'),'plugin_error':QT_TRANSLATE_NOOP('Bridge','Plugin retornou erro interno'),'plugin_output_invalid':QT_TRANSLATE_NOOP('Bridge','Resposta do plugin fora do formato'),
    'plugin_not_runnable':QT_TRANSLATE_NOOP('Bridge','Plugin não pode ser executado'),'plugin_cpu_exceeded':QT_TRANSLATE_NOOP('Bridge','Plugin passou do limite de processamento'),'response_too_large':QT_TRANSLATE_NOOP('Bridge','Resposta grande demais'),'permission_denied':QT_TRANSLATE_NOOP('Bridge','Permissão negada ao plugin')})
CODE_MESSAGES.setdefault('audio_tool_failed',QT_TRANSLATE_NOOP('Bridge','A ferramenta de áudio falhou; tente de novo'))
CODE_MESSAGES.setdefault('invalid_device',QT_TRANSLATE_NOOP('Bridge','Microfone não listado pelo sistema: atualize a lista e escolha de novo'))
# DIAG-04 (docs/ui-spec/50-diagnostico.md §3.4): codes the Core emits that had no Portuguese text.
CODE_MESSAGES.update({'hub_storage_error':QT_TRANSLATE_NOOP('Bridge','Falha ao gravar o registro do catálogo.'),'plugin_storage_error':QT_TRANSLATE_NOOP('Bridge','Falha ao gravar o registro dos plugins.'),'hub_import_timeout':QT_TRANSLATE_NOOP('Bridge','Importação expirou antes de terminar.')})
