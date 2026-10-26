# Glossário de tradução da interface (WP-20)

Idioma-fonte: português do Brasil (pt-BR). Idiomas de destino: inglês (en) e francês (fr). Este arquivo é a referência
para quem escreve ou revisa as traduções em `app/translations/en/` e `app/translations/fr/`. Os termos abaixo já estão
aplicados nos catálogos existentes; um termo novo entra aqui antes de entrar nos `.ts`.

## Regras

1. **Português é a fonte.** Todo texto visível passa por `qsTr("...")` (QML e JS) ou `QCoreApplication.translate("Bridge", "...")`
   (Python). Fora disso, o texto não pode aparecer na tela.
2. **Marcadores em tabelas.** Quando um texto fica numa tabela (objeto ou array) e só é usado depois, ele recebe
   `QT_TR_NOOP("...")` na tabela, e a leitura usa `qsTr(...)` no momento da chamada. Tabela de texto avaliada uma vez
   (variável de módulo) não atualiza ao trocar o idioma.
3. **Nomes de idiomas** ficam no idioma do próprio idioma (endônimos): "Português (Brasil)", "Français". Inglês e
   francês aparecem traduzidos dentro das outras línguas: "Inglês" → English / Anglais.
4. **Códigos do Core não são traduzidos.** Códigos de erro (`stale_preferences`, `busy`, `invalid_preferences`...) e
   nomes técnicos (plugin ids, capabilities, `ui_language`) nunca aparecem na tela como texto e nunca são traduzidos.
5. **Marcas e nomes próprios** não mudam: Gideon, Core, Hub, Skills, Plugins, LLM, GitHub, Google, Home Assistant, MCP,
   Wake, Hey Gideon, Ollama, OpenRouter, Moonshine, Pocket, Parakeet.
6. **Placeholders** `%1`, `%2` são mantidos na mesma ordem. O texto "%1 bytes" continua com o número na frente.
7. **Frases com travessão de lista** ("Nenhuma · …") mantêm o separador ` · ` como ele está na fonte.
8. **Tom**: frases curtas, imperativo cordial em pt-BR ("Escolha", "Salve"), infinitivo em EN/FR só para rótulos de
   botão. Sem emojis.
9. **Consistência de estado**: "Em espera" é o estado do assistente em repouso (EN *Idle*, FR *En veille*), não "parado".
   "Parado" é só para o que foi interrompido (EN *Stopped*, FR *Arrêté*).

## Termos da interface

| pt-BR | en | fr | Onde aparece / observação |
|---|---|---|---|
| Assistente | Assistant | Assistant | aba de nível 1 |
| Extensões | Extensions | Extensions | aba de nível 1 |
| Permissões | Permissions | Autorisations | aba de nível 1 |
| Configurações | Settings | Paramètres | aba de nível 1 |
| Diagnóstico | Diagnostics | Diagnostic | aba de nível 1 |
| Hoje | Today | Aujourd'hui | página inicial |
| Conversa | Conversation | Conversation | |
| Histórico | History | Historique | sub-aba do Assistente |
| Agente | Agent | Agent | |
| Atividade | Activity | Activité | |
| Automações | Automations | Automatisations | |
| Hábitos | Habits | Habitudes | |
| Conexões | Connections | Connexions | |
| Modelos LLM | LLM models | Modèles LLM | |
| Percepção e ação | Perception and action | Perception et action | |
| Visão geral | Overview | Vue d'ensemble | Permissões |
| Concessões | Grants | Autorisations accordées | Permissões |
| Auditoria | Audit | Audit | |
| Memória | Memory | Mémoire | |
| Voz e Wake | Voice and wake | Voix et réveil | Wake = detecção da frase de despertar |
| Idiomas | Languages | Langues | |
| Áudio | Audio | Audio | |
| Dispositivos | Devices | Appareils | |
| Aparência | Appearance | Apparence | |
| Privacidade | Privacy | Confidentialité | |
| Almas | Souls | Âmes | personas do assistente |
| Geral | General | Général | |
| Estado | Status | État | diagnóstico |
| Motores | Engines | Moteurs | diagnóstico |
| Recuperação | Recovery | Récupération | diagnóstico |
| Desenvolvedor | Developer | Développeur | |
| Motor LLM | LLM engine | moteur LLM | |
| Frase de despertar | wake phrase | phrase de réveil | |
| Sessão de voz | voice session | session vocale | |
| Core | Core | Core | não traduzir |
| Plugin / Skill | Plugin / Skill | Plugin / Skill | não traduzir |
| Hub | Hub | Hub | não traduzir |
| Salvar | Save | Enregistrer | botão |
| Aplicar | Apply | Appliquer | botão |
| Cancelar | Cancel | Annuler | botão e ação de interrupção |
| Desfazer | Undo | Défaire | ação de reverter a última mudança |
| Restaurar | Restore | Restaurer | |
| Fechar | Close | Fermer | |
| Instalar | Install | Installer | |
| Verificar e ativar | Verify and activate | Vérifier et activer | botão de idioma (CFG-03) |
| Offline | Offline | Hors ligne | estado da barra |
| Pensando | Thinking | Réflexion | estado da barra |
| Ouvindo | Listening | À l'écoute | estado da barra |
| Respondendo | Speaking | Réponse en cours | estado da barra |
| Em espera | Idle | En veille | estado do assistente |
| Modo seguro | Safe mode | Mode sécurisé | estado do Core |
| Core indisponível | Core unavailable | Core indisponible | estado do Core |
| Reinício necessário | Restart required | Redémarrage nécessaire | |
| Pronto | Ready | Prêt | |
| Falhou | Failed | Échec | estado |
| Concluído | Done | Terminé | estado |
| Desativado | Off | Désactivé | interruptor de estado |
| Cancelado | Cancelled | Annulé | |
| Indisponível | Unavailable | Indisponible | |
| Desconhecido | Unknown | Inconnu | |
| Suportado / Não suportado | Supported / Not supported | Pris en charge / Non pris en charge | |
| Instalado / Não instalado | Installed / Not installed | Installé / Non installé | idiomas |
| Confiável | Trusted | Approuvé | ferramenta de conexão |
| Escopo | scope | périmètre | permissão de conexão |
| Auditoria | Audit | Audit | |

## Como acrescentar uma tradução

1. Escreva o texto em `qsTr("...")` (ou `QT_TR_NOOP` em tabela). Não concatene textos dentro de `qsTr`: use `%1`.
2. Rode `target/ui-venv/bin/python scripts/i18n_tools.py update`. Ele cria os `.ts` do arquivo e marca o texto novo como
   `unfinished`.
3. Escreva a tradução em `app/translations/en/<caminho>.ts` e `app/translations/fr/<caminho>.ts`, usando este glossário.
4. Rode `target/ui-venv/bin/python scripts/test_i18n.py`. O teste falha se algum texto ficou sem tradução, se o catálogo
   não bate com o código ou se sobrou português fora de `qsTr`.
