# Pendências marcadas como inativas / em desenvolvimento — plano de implementação

Origem: pedido do dono (2026-10-24): "Implemente tudo que está marcado como inativo ou em desenvolvimento. Deixe tudo que estiver falando funcionando."
Fontes: textos "Indisponível…" e "ainda não…" em `app/`, `docs/ui-spec/*`, `docs/UI_INVENTORY.md`, `docs/HUMAN_VALIDATION.md`.

Regra de honestidade: nada é marcado como pronto sem teste. O que depende de hardware físico ou de modelos que não existem aqui é implementado
até onde se prova no ambiente virtual e continua rotulado "pendente de validação humana".

## Pacote A — Core (Rust)
| ID | Item | Critério de aceite |
|---|---|---|
| A1 | Sensibilidade do wake (preferência limitada) | Preferência `wake_sensitivity` (0.5–1.5, padrão 1.0) no ledger de preferências; o detector usa limiar × fator; teste de replay mostra que 0.5 rejeita um disparo limítrofe e 1.5 aceita; snapshot expõe o valor. |
| A2 | Restaurar padrões das preferências pelo Core | Op `preferences_restore_defaults{revision}` preserva backup do arquivo, volta aos padrões, CAS de revisão; teste. |
| A3 | Preferências de dispositivo de áudio | Campos `audio_input_device`/`audio_output_device` (strings limitadas, `default` por padrão) no ledger; snapshot expõe; teste. |
| A4 | Enumerar dispositivos de áudio | Op `audio_devices` lê (só leitura) os dispositivos via `pactl list short sources/sinks` ou `pw-dump` quando existir; sem ferramenta → lista vazia + motivo; teste com ferramenta falsa no PATH. |
| A5 | Entrada de áudio ao vivo (opt-in) | Flag `--live-audio` (nunca ligada por padrão, nunca nos gates com dispositivo pessoal): processo `pw-record`/`parecord` (sandbox bwrap, sem rede) alimenta o pipeline wake→STT; saída TTS via `pw-play`/`paplay`; indicador de microfone ativo no snapshot; tudo testado com gravador/player FALSOS (scripts que leem/escrevem arquivos). Rótulo permanece "pendente de validação humana". |

## Pacote B — Ponte e interface (UI)
| ID | Item | Critério de aceite |
|---|---|---|
| B1 | Primeira execução guiada (onboarding) | 4 passos curtos (boas-vindas e privacidade → frase de wake → dispositivos/volume → atalhos); aparece 1× por perfil (`behavior.onboardingDone`), refazível em Configurações › Geral. |
| B2 | Iniciar no login | Interruptor em Geral cria/remove `~/.config/autostart/gideon.desktop` (XDG) apontando para o `gideon-launch` do perfil; confirmação; teste com HOME privado. |
| B3 | Desempenho | "Modo econômico": desliga animação do orbe e translucidez, reduz sombras (`perf.lowPower`), aplica na hora; segue "reduzir movimento" do sistema. |
| B4 | Perfis de configuração do app | Criar/duplicar/trocar/excluir perfis de configurações de interface (arquivos `<perfil>.json`); exportar/importar por perfil; confirmação nas ações destrutivas. |
| B5 | Versão do pacote | Diagnóstico › Estado mostra versão/commit/hash lidos do PACKAGE.json do pacote instalado. |
| B6 | Wake de teste | Em Diagnóstico › Desenvolvedor, botão envia `virtual_wake` (só se o Core foi iniciado com entrada virtual). |
| B7 | Invocar capability com JSON | Campo JSON ≤ 2 KiB validado; envia objeto; resultado e cancelar invocação. |
| B8 | Última captura e resposta | Diagnóstico › Motores mostra os blocos `capture` e `speech`/`transcript` (início, fim, amostras, hash curto, pico/RMS) já validados pela ponte. |
| B9 | Caminho do log / catálogo | Auditoria e Recuperação mostram o diretório do Core, e o estado do armazenamento do catálogo. |
| B10 | Data de concessão de plugin | Coluna usa `approved_at_ms` do hub; "—" só se desconhecido. |
| B11 | Efeito com parâmetros | Passo de skill/proposta mostra "Abrir brave", "Volume 40" (efeito com argumentos reais). |
| B12 | Conversa: erros acionáveis | Banner específico para `key_missing`, `provider_not_configured`, `cloud_not_authorized` com link para Modelos LLM › Provedor e chaves. |
| B13 | Validação de comando em bytes | Limite de 512 bytes (não caracteres) no campo de comando, com contador. |
| B14 | Totais do catálogo de modelos | "N de M" correto vindo da saída paginada. |
| B15 | Atalhos prometidos | Ctrl+M liga/desliga microfone (quando houver sessão/entrada), Esc cancela a escuta ou fecha diálogo, Ctrl+K, Ctrl+1…5 e Ctrl+Tab testados. |
| B16 | Sensibilidade, dispositivos e restaurar (após A1–A4) | Controles ligados ao Core em Voz e Wake, Dispositivos e Geral; "Restaurar padrões do Core". |

## Não implementável neste ambiente (continua desativado COM o motivo, ou rotulado)
- Escolha de voz e velocidade da fala: só existe uma voz empacotada (Pocket TTS · Alba); outras vozes exigem baixar modelos não aprovados.
- Idioma da interface em inglês/outros: exigiria traduzir todo o app; hoje só português (fica como decisão do dono).
- Backends reais de tela/entrada/áudio avançado/microfone avançado/câmera/manipulação de display: dependem de portais, PipeWire, libei, webcam e compositor; o C4.6 é UNSUPPORTED.
- Validação com hardware físico (áudio, Wayland, Flatpak, contas reais): checklist em `docs/HUMAN_VALIDATION.md`.
