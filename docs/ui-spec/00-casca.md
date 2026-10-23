# Especificação da casca (vale para todas as telas)

Janela de referência: 1380 × 904 px (mínimo 720 × 520). Coordenadas em px a partir do canto superior esquerdo da janela.
Estilo: KDE/Plasma (Breeze), tema escuro do Gideon (tokens em docs/UI_DESIGN.md).

## Regiões

| Região | Posição / tamanho | Conteúdo |
|---|---|---|
| **Barra de abas (nível 1)** | y 0–56, largura total, fundo #0e1a3a, borda inferior 1 px #263a73 | Esquerda: logo (orbe 28 px) + "Gideon" (16 px bold) em x 16–120. Depois as 5 abas, cada uma com ícone 18 px + rótulo 14 px, altura 40, padding horizontal 14, espaço 4. Aba ativa: fundo acento a 18 %, barra inferior 3 px de acento, texto branco bold. Direita (alinhada a x = largura − 16): botão de busca/paleta '🔍 Ctrl+K' (altura 30, largura 120, abre a paleta de comandos centralizada: campo + lista de resultados com prefixos p: páginas, s: configurações, c: comandos), pílula de estado (altura 30, ponto colorido + texto) e, à esquerda dela, botão **Cancelar** (secundário, altura 30), visível só quando há algo cancelável. |
| **Barra de sub-abas (nível 2)** | y 56–100, largura total, fundo #0b1530 | Texto 14 px, altura 44, padding horizontal 18; ativa: texto branco bold + sublinhado 2 px de acento; inativa: #9db0e0; desabilitada: #5a6a95 + tooltip com o motivo. Badges/contadores ficam logo após o rótulo (altura 18, raio 9). |
| **Cabeçalho da sub-aba** | y 116–176 (margem 24 acima), x 32 até largura − 32 | Título 24 px bold; subtítulo 14 px #9db0e0 (máx. 1 linha, ≤ 90 caracteres); **ação primária** (botão 40 px de altura) alinhada à direita na linha do título. |
| **Faixa de resumo** | y 184–224, mesma largura | Cartão de altura 40 com 1 linha: frase-resumo à esquerda (14 px bold) e badges à direita. Opcional. |
| **Área de conteúdo** | de y 236 até altura − 24; x 32 até largura − 32 (máx. 1100 px, centralizada acima de 1240 px) | Rola na vertical dentro da área; cabeçalho e barras ficam fixos. Grade de 12 colunas, gap 16. Cartões: raio 14, padding 20, título 17 px semibold, corpo 14 px, legenda 12 px. |
| **Rodapé** | não existe | O estado vive na pílula. Mensagens transitórias aparecem como toast no canto inferior direito (4 s). |

## Componentes e textos padrão

- **Badge**: altura 22, raio 11, cor + palavra. Tons: Sucesso (#5ee0a0), Aviso (#f2c15c), Erro (#ff7d8a), Info (#7693ff), Neutro (#9db0e0).
- **Botão primário**: fundo #3a5bd9, texto branco, altura 40, raio 10. **Secundário**: contorno #2a3d78. **Perigo**: contorno e texto #ff7d8a; sempre com confirmação em diálogo ("Tem certeza?" + descrição do efeito + [Cancelar] [Confirmar], Cancelar é o foco inicial).
- **Bloco "Como funciona"**: linha recolhível (altura 56) com título e 1 linha de resumo; recolhido por padrão; ícone ▸/▾ à direita.
- **Estado vazio**: moldura tracejada; ícone 32 px centralizado; 1 frase (14 px); botão do próximo passo; altura mínima 140.
- **Linha desativada com motivo**: controle esmaecido + texto de 12 px abaixo "Indisponível: <motivo>".
- **Selos de honestidade** (discretos, ao lado do item): "SINTÉTICO", "SERVIDOR FALSO", "não verificado", "em desenvolvimento", "requer prova de conceito", "UNSUPPORTED".
- **Pílula de estado**: Em espera (ponto neutro) · Ouvindo (azul) · Transcrevendo (azul) · Pensando (violeta) · Executando (azul) · Falando (ciano) · Erro (vermelho) · Offline (cinza, "Core desconectado").
- **Toast**: sucesso/erro da última ação; mesmo texto que o recibo do Core traduzido.
- **Teclado**: Ctrl+1…5 troca de aba; Ctrl+Tab percorre sub-abas; Esc fecha diálogos; foco visível com anel de 2 px de acento.
- **Rótulos nunca em inglês** e nunca códigos crus (traduzir via tabela de exibição da ponte).
- **Responsivo**: < 900 px as abas viram só ícones (tooltip com o nome) e o cabeçalho empilha título e ação; < 720 px não suportado (tamanho mínimo).

## Convenção dos arquivos de especificação

Cada sub-aba tem: **Objetivo · Condição de aparecimento · Nível · Layout (grade) · Wireframe · Elementos (tabela) · Estados · Textos · Dados · Regras**.
Na tabela de elementos: `#` (ordem de leitura), `Região/posição`, `Tipo`, `Texto exato`, `Fonte de dados` (propriedade ou slot da ponte), `Ação → resultado`, `Estados`, `Nível`.
