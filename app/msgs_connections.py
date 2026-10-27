"""Connection accounts, registry and permission texts."""
from PySide6.QtCore import QCoreApplication,QT_TRANSLATE_NOOP
from translations import _Messages
from msgs_misc import OPS,PENDING

# Core codes for connection ops and for connection proposals (kind 'connection'). Each one has a Portuguese text in CONN_MESSAGES.
CONN_MESSAGES=_Messages({
    'scope_not_granted':QT_TRANSLATE_NOOP('Bridge','Escopo não concedido: conceda o escopo antes de usar esta operação; nenhuma chamada foi feita'),
    'rate_limited':QT_TRANSLATE_NOOP('Bridge','Limite de chamadas do servidor atingido; tente de novo em instantes'),
    'unauthorized':QT_TRANSLATE_NOOP('Bridge','Autorização recusada pelo servidor; reconecte a conta'),
    'forbidden_scope':QT_TRANSLATE_NOOP('Bridge','O servidor recusou o escopo pedido para esta operação'),
    'account_mismatch':QT_TRANSLATE_NOOP('Bridge','A conta devolvida pelo servidor não confere; chamada recusada'),
    'provider_unreachable':QT_TRANSLATE_NOOP('Bridge','Servidor do provedor inacessível neste ambiente'),
    'real_backend_unsupported':QT_TRANSLATE_NOOP('Bridge','Backend real não suportado neste ambiente; use o servidor falso'),
    'reauth_required':QT_TRANSLATE_NOOP('Bridge','Reautenticação necessária: conecte a conta de novo'),
    'public_pending':QT_TRANSLATE_NOOP('Bridge','Ação pública aguarda sua aprovação explícita; nada foi publicado'),
    'provider_error':QT_TRANSLATE_NOOP('Bridge','O provedor devolveu erro; nada foi confirmado'),
    'unknown_connection':QT_TRANSLATE_NOOP('Bridge','Conta desconhecida ou já removida'),
    'stale_connection_revision':QT_TRANSLATE_NOOP('Bridge','Contas mudaram no Core; atualize e tente de novo'),
    'invalid_connection':QT_TRANSLATE_NOOP('Bridge','Dados da conta recusados pelo Core'),
    'connection_limit':QT_TRANSLATE_NOOP('Bridge','Limite de 8 contas atingido; remova uma conta antes'),
    'not_connected':QT_TRANSLATE_NOOP('Bridge','Conta não está conectada'),
    'unknown_operation':QT_TRANSLATE_NOOP('Bridge','Operação desconhecida para este provedor'),
    'connection_consent_required':QT_TRANSLATE_NOOP('Bridge','Escolha ao menos um escopo pedido para consentir'),
    'connection_args_invalid':QT_TRANSLATE_NOOP('Bridge','Argumentos devem ser um objeto JSON de até 4 KiB'),
    'connection_unavailable':QT_TRANSLATE_NOOP('Bridge','Conexões indisponíveis agora'),
    'not_found':QT_TRANSLATE_NOOP('Bridge','Recurso não encontrado no servidor; nada foi alterado'),
    'public_disabled':QT_TRANSLATE_NOOP('Bridge','Ação pública ou destrutiva desativada nesta build; nada foi executado'),
    'scope_not_requested':QT_TRANSLATE_NOOP('Bridge','Escopo não pedido pelo dispositivo; nada foi concedido'),
    'device_expired':QT_TRANSLATE_NOOP('Bridge','Código de confirmação expirou; conecte a conta de novo'),
    'consent_denied':QT_TRANSLATE_NOOP('Bridge','Consentimento recusado no servidor; nada foi concedido'),
    'connections_storage_error':QT_TRANSLATE_NOOP('Bridge','Contas indisponíveis: o arquivo de contas não pôde ser lido ou gravado'),
    'consent_required':QT_TRANSLATE_NOOP('Bridge','Consinta os escopos antes de enviar o token; nada foi enviado ao servidor'),
    'invalid_token':QT_TRANSLATE_NOOP('Bridge','Token inválido: use o token de longa duração do Home Assistant (16 a 256 caracteres, sem espaços)'),
    'invalid_state':QT_TRANSLATE_NOOP('Bridge','Esta conta não está aguardando um token agora'),
    'tool_trust_invalid':QT_TRANSLATE_NOOP('Bridge','Escolha ao menos uma ferramenta que aguarda sua confiança'),
    'tool_not_trusted':QT_TRANSLATE_NOOP('Bridge','Ferramenta nova ou alterada: confie nela na página Conexões antes de chamar; nada foi executado'),
    'tool_not_verified':QT_TRANSLATE_NOOP('Bridge','Servidor MCP reconectado ou reiniciado: liste as ferramentas de novo antes de chamar; nada foi executado'),
    'tool_rejected':QT_TRANSLATE_NOOP('Bridge','Ferramenta recusada pelo Core (esquema fora do subconjunto simples ou grande demais); nada foi executado'),
    'mcp_not_running':QT_TRANSLATE_NOOP('Bridge','Servidor MCP não está rodando; conecte a conta de novo'),
    'mcp_crashed':QT_TRANSLATE_NOOP('Bridge','Servidor MCP parou de responder; a conta ficou com erro e o Core segue normal'),
    'mcp_protocol':QT_TRANSLATE_NOOP('Bridge','Servidor MCP respondeu fora do protocolo; a conta ficou com erro'),
    'mcp_too_large':QT_TRANSLATE_NOOP('Bridge','Servidor MCP enviou linha grande demais; a conta ficou com erro'),
    'mcp_start_failed':QT_TRANSLATE_NOOP('Bridge','Servidor MCP não iniciou no sandbox'),
    'mcp_tool_error':QT_TRANSLATE_NOOP('Bridge','A ferramenta MCP devolveu erro; nada foi confirmado'),
    'mcp_rpc_error':QT_TRANSLATE_NOOP('Bridge','O servidor MCP recusou a chamada; nada foi confirmado'),
    'mcp_too_many_tools':QT_TRANSLATE_NOOP('Bridge','Servidor MCP listou ferramentas demais (máximo 16); lista anterior mantida'),
    'mcp_restart_limit':QT_TRANSLATE_NOOP('Bridge','Limite de reinícios do servidor MCP atingido; reinicie o Core para tentar de novo'),
})
REG_VISUAL_WARNING=QT_TRANSLATE_NOOP('Bridge','Atenção: o fallback visual dirige uma tela por cliques e digitação, é menos seguro que a API e só vale quando não há conta conectada. Nunca contorna token expirado, reautenticação ou escopo negado. A publicação ainda pede sua aprovação.')
REG_MESSAGES=_Messages({
    'route_unavailable':QT_TRANSLATE_NOOP('Bridge','Nenhuma rota disponível para esta finalidade; veja os motivos. Nada foi executado'),
    'unknown_purpose':QT_TRANSLATE_NOOP('Bridge','Finalidade desconhecida'),
    'no_visual_route':QT_TRANSLATE_NOOP('Bridge','Esta finalidade não tem rota visual'),
    'stale_registry_revision':QT_TRANSLATE_NOOP('Bridge','As rotas mudaram no Core; atualize e tente de novo'),
    'registry_storage_error':QT_TRANSLATE_NOOP('Bridge','Rotas indisponíveis: o arquivo de permissões não pôde ser lido ou gravado'),
    'registry_unavailable':QT_TRANSLATE_NOOP('Bridge','Rotas indisponíveis agora'),
    'registry_revision_exhausted':QT_TRANSLATE_NOOP('Bridge','Revisão das rotas esgotada'),
})
PERMISSION_LABELS=_Messages({'network_llm':QT_TRANSLATE_NOOP('Bridge','rede do motor LLM'),'storage_settings':QT_TRANSLATE_NOOP('Bridge','armazenamento de configurações'),'skills_author':QT_TRANSLATE_NOOP('Bridge','autoria de skills'),
                   'screen_observe':QT_TRANSLATE_NOOP('Bridge','observação de tela'),'input_control':QT_TRANSLATE_NOOP('Bridge','controle de entrada'),'audio_route':QT_TRANSLATE_NOOP('Bridge','rota de áudio'),
                   'mic_config':QT_TRANSLATE_NOOP('Bridge','configuração do microfone'),'camera_capture':QT_TRANSLATE_NOOP('Bridge','captura da câmera'),'display_manipulate':QT_TRANSLATE_NOOP('Bridge','ajuste de tela')})

def display_permission(permission):
    """Permission id as the user reads it. Unknown ids are shown as the Core sent them (they are never translated by guess)."""
    return PERMISSION_LABELS.get(permission,permission or '')
# Registry effect templates (src/tools.rs effect) and risk classes as Portuguese text. Unknown ids show no text (QML shows the absence text).
EFFECT_TEXT=_Messages({'open_app':QT_TRANSLATE_NOOP('Bridge','Abrir {app}'),'set_volume':QT_TRANSLATE_NOOP('Bridge','Volume {level}'),'mute':QT_TRANSLATE_NOOP('Bridge','Silenciar'),
             'get_status':QT_TRANSLATE_NOOP('Bridge','Consultar o estado do sistema'),'get_time':QT_TRANSLATE_NOOP('Bridge','Consultar a hora'),'get_date':QT_TRANSLATE_NOOP('Bridge','Consultar a data')})
RISK_TEXT=_Messages({'read':QT_TRANSLATE_NOOP('Bridge','baixo'),'state_changing':QT_TRANSLATE_NOOP('Bridge','médio'),'destructive':QT_TRANSLATE_NOOP('Bridge','alto'),'public':QT_TRANSLATE_NOOP('Bridge','alto')})

def display_risk(risk):
    """'baixo', 'médio' or 'alto'; '' when the proposal declares no risk (the card then says 'não declarado')."""
    return RISK_TEXT.get(risk,'')

def grant_rows(snapshot):
    """Read-only Concessões rows (docs/ui-spec/30-permissoes.md §6), built only from the snapshot. Plugins: hub entries except incompatible ones. Skills: one row per skill item. Accounts: one approved row for granted scopes and one pending row for scopes awaiting consent."""
    rows=[]
    for entry in (snapshot.get('hub') or {}).get('entries') or []:
        if entry.get('status')=='incompatible':continue
        approved=entry.get('permissions_approved') is True
        if approved:state='approved'
        elif entry.get('status') in ('installed','update_available') and entry.get('permissions'):state='pending'
        else:state='not_approved'
        row={'origin':'plugin','owner_id':entry['plugin_id'],'label':', '.join(display_permission(p) for p in entry.get('permissions') or []) or QCoreApplication.translate('Bridge','sem permissões'),'state':state}
        if approved and 'approved_at_ms' in entry:row['approved_at_ms']=entry['approved_at_ms']
        rows.append(row)
    for item in (snapshot.get('skills') or {}).get('items') or []:
        rows.append({'origin':'skill','owner_id':item['id'],'label':item['name'],'state':'approved' if item['permissions_ok'] else 'pending'})
    conn=snapshot.get('connections') or {}
    labels={(p['id'],s['id']):s['label'] for p in conn.get('providers') or [] for s in p['scopes']}
    for item in conn.get('items') or []:
        for scopes,state in ((item.get('granted_scopes') or [],'approved'),(item.get('pending_scopes') or [],'pending')):
            if scopes:rows.append({'origin':'connection','owner_id':item['id'],'label':', '.join(labels.get((item['provider'],s),s) for s in scopes),'state':state})
    return rows

def pending_count(snapshot):
    """P of docs/ui-spec/30-permissoes.md §8: installed or updated plugins with permissions and no approval, plus accounts with scopes awaiting consent, plus one per MCP tool that needs re-approval (the queue of Visão geral lists each tool). Skills and action proposals are not counted."""
    count=sum(1 for e in (snapshot.get('hub') or {}).get('entries') or [] if e.get('permissions') and not e.get('permissions_approved') and e.get('status') in ('installed','update_available'))
    items=(snapshot.get('connections') or {}).get('items') or []
    count+=sum(1 for i in items if i.get('pending_scopes'))
    return count+sum(1 for i in items for t in i.get('tools') or [] if t.get('state')=='needs_reapproval')
OPS.update({
    'connection_add':('connections',QT_TRANSLATE_NOOP('Bridge','Conta criada (desconectada)')),
    'connection_connect':('connections',QT_TRANSLATE_NOOP('Bridge','Conexão iniciada: confirme o código no servidor e consinta os escopos')),
    'connection_consent':('connections',QT_TRANSLATE_NOOP('Bridge','Escopos concedidos pelo usuário')),
    'connection_refresh':('connections',QT_TRANSLATE_NOOP('Bridge','Atualização da conta solicitada')),
    'connection_disconnect':('connections',QT_TRANSLATE_NOOP('Bridge','Conta desconectada; segredos apagados')),
    'connection_revoke':('connections',QT_TRANSLATE_NOOP('Bridge','Acesso revogado no servidor')),
    'connection_remove':('connections',QT_TRANSLATE_NOOP('Bridge','Conta removida')),
    'connection_call':('connections',QT_TRANSLATE_NOOP('Bridge','Chamada enviada ao Core; resultado em Última chamada')),
    'connection_set_token':('connections',QT_TRANSLATE_NOOP('Bridge','Token enviado ao Core para validação; o campo foi limpo')),
    'connection_trust_tools':('connections',QT_TRANSLATE_NOOP('Bridge','Ferramentas confiadas pelo usuário; cada chamada ainda pede aprovação')),
    'connection_revoke_scope':('connections',QT_TRANSLATE_NOOP('Bridge','Escopo revogado; chamadas que precisam dele pedem concessão de novo')),
})
PENDING.update({
    'connection_add':QT_TRANSLATE_NOOP('Bridge','Criando conta no Core…'),
    'connection_connect':QT_TRANSLATE_NOOP('Bridge','Iniciando conexão no Core…'),
    'connection_consent':QT_TRANSLATE_NOOP('Bridge','Enviando consentimento ao Core…'),
    'connection_refresh':QT_TRANSLATE_NOOP('Bridge','Atualizando conta no Core…'),
    'connection_disconnect':QT_TRANSLATE_NOOP('Bridge','Desconectando conta no Core…'),
    'connection_revoke':QT_TRANSLATE_NOOP('Bridge','Revogando acesso no Core…'),
    'connection_remove':QT_TRANSLATE_NOOP('Bridge','Removendo conta no Core…'),
    'connection_call':QT_TRANSLATE_NOOP('Bridge','Chamando operação pelo Core…'),
    'connection_set_token':QT_TRANSLATE_NOOP('Bridge','Validando token no Core…'),
    'connection_trust_tools':QT_TRANSLATE_NOOP('Bridge','Confiando nas ferramentas no Core…'),
    'connection_revoke_scope':QT_TRANSLATE_NOOP('Bridge','Revogando escopo no Core…'),
})
