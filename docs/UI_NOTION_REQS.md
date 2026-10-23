# Requisitos de UI vindos do Notion (S2 e "13 · Interface, HUD e Design System")

Fontes: Notion "S2 · Gideon App e Hub" e "13 · Interface, HUD e Design System" (lidas em 2026-10-23).

## Regras de estrutura

- Janela principal **minimalista**: Dashboard/Conversas básico, Configuração (Voz/Dispositivos), Extensões (Hub), Permissões, Diagnóstico.
- **Uma aba "Plugins" para o Hub.** A aba "LLM Models" NÃO existe antes de instalar o plugin LLM; depois aparece como painel próprio do plugin.
- Dispositivo/captura de áudio e vozes básicas ficam em **Configurações de voz**, nunca em "Modelos".
- Páginas futuras só quando houver backend real; controles ausentes ficam desativados e rotulados.
- Sem Model Manager de STT/TTS/Wake; troca de wake só por frases certificadas do pacote; sem página de download de modelos.
- Preferências (B2): frase de wake certificada, sensibilidade limitada, dispositivo de entrada/saída, feedback audível/visual,
  voz da Base, idioma, volume e performance, iniciar no login (se autorizado), privacidade e retenção de dados.

## Direção de experiência

- "Aura + Command + Spatial": o cotidiano é um **HUD vocal discreto**; tarefas profundas usam um **painel de gerenciamento**.
- Estados do HUD: Idle, WakeDetected, Listening, Transcribing, Thinking, Acting, Speaking, Error, AwaitingConfirmation.
  Mostrar transcrição, ferramenta em execução, progresso, aviso de microfone ativo, sucesso/falha verificados, botão Cancelar.
- **Um estado principal em destaque.** Evitar painéis excessivos, números inúteis, notificações repetitivas.
- Modo básico legível; **ajustes técnicos avançados revelados progressivamente**.
- Aprovação de ação mostra alvo, efeito e risco; o usuário interrompe tarefa e áudio a qualquer momento; nunca resposta otimista.
- Onboarding, estado vazio, recuperação de erro e diagnóstico simples com o mesmo cuidado que o HUD.
- Acessibilidade, foco de teclado, HiDPI; efeitos degradam em máquinas fracas; Wayland respeitado.

## Lista-alvo de áreas do Notion (nem todas têm backend hoje)

Conversations, Memory*, Souls*, Habits*, Skills, Connections, LLM Models (só com plugin LLM), Automations*, Devices, Permissions,
Diagnostics, Settings. (* sem backend hoje → não criar página; no máximo uma nota "em breve" desativada se fizer sentido.)
