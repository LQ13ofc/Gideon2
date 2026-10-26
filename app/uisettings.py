"""App-side UI settings (docs/ui-spec/01-ajustes-minimalismo.md 3.1 and 3.3).

One schema declares every interface option. Entries with source 'app' live in a JSON file per settings profile under
$XDG_CONFIG_HOME/gideon-app/<core hash>/<profile>.json, and the active profile name lives in active.json next to them.
Entries with source 'core' are read and written through the bridge (the Core owns them). Secrets are never part of the
schema, so they are never stored or exported.

Also here: the XDG autostart entry ("Iniciar no login", $XDG_CONFIG_HOME/autostart/gideon.desktop), which only this app
creates and removes, and the environment switch GIDEON_UI_NO_ONBOARDING=1 that keeps the first-run guide out of tests.
"""
import copy,hashlib,json,math,os,re,shlex,subprocess,tempfile,unicodedata
from pathlib import Path
from PySide6.QtCore import QObject,Property,Signal,Slot
from bridge import CODE_MESSAGES,set_code_detail

SCHEMA_VERSION=1
FILE_LIMIT=256*1024
IMPORT_LIMIT=64*1024
STRING_LIMIT=200
DEFAULT_PRESET='gideon-escuro'
# Colour roles (docs/research/ux-temas.md 6.1). `accent` has its own key; the others may be overridden in theme.colors.
ROLES=('bg','surface','surfaceVariant','outline','text','textMuted','accent','onAccent','success','warning','error','info')
COLOR_ROLES=tuple(role for role in ROLES if role!='accent')
DERIVED=('hover','pressed','focus','tint')
TEXT_FOREGROUNDS=('text','textMuted','success','warning','error','info')
TEXT_BACKGROUNDS=('bg','surface','surfaceVariant')
THEME_KEYS=frozenset({'theme.preset','theme.accent','theme.colors','theme.contrast'})
HEX=re.compile(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})')
CONTROL=re.compile(r'[\x00-\x1f\x7f]')
# Settings profiles (docs/ui-spec/01-ajustes-minimalismo.md 3.1; docs/research/ux-config-navegacao.md item 11).
PROFILE_DEFAULT='Padrão'
PROFILE_NAME=re.compile(r'[A-Za-z0-9 _-]{1,32}')
PROFILE_LIMIT=20
ACTIVE_FILE='active.json'
# XDG autostart (Desktop Entry spec). The marker line says the file was written by this app; only such a file is removed.
AUTOSTART_NAME='gideon.desktop'
AUTOSTART_MARK='X-Gideon-Managed=true'
AUTOSTART_NO_COMMAND='não foi possível descobrir o comando de inicialização'
ONBOARDING_ENV='GIDEON_UI_NO_ONBOARDING'
LAUNCH_ENV='GIDEON_LAUNCH_CMD'
PLAIN_ARG=re.compile(r'[A-Za-z0-9_./:=@+-]+')
PROFILE_ARG=re.compile(r'[A-Za-z0-9_.-]{1,64}')
# Presets (docs/research/ux-temas.md 6.4), values in ROLES order.
PRESET_ROWS=(
    ('gideon-escuro','Gideon escuro',('#121417','#1b1f24','#262c33','#7d8794','#e6e9ee','#a7b0bc','#7aa2f7','#0b1020','#6bcb8b','#e8b04b','#f07178','#6cb6ff')),
    ('gideon-claro','Gideon claro',('#fbfbfd','#ffffff','#eef1f5','#7a8491','#1a1d21','#4b5563','#2f5fd0','#ffffff','#1e7a3f','#8a5a00','#b42318','#1d5fa8')),
    ('alto-contraste','Alto contraste',('#000000','#0a0a0a','#1a1a1a','#ffffff','#ffffff','#d0d0d0','#ffd400','#000000','#00e676','#ffb300','#ff5252','#40c4ff')),
    ('escuro-neutro','Escuro neutro',('#232629','#31363b','#3b4045','#7f8c8d','#fcfcfc','#bdc3c7','#3daee9','#0b0f13','#52be80','#f79134','#f58b98','#4bb4eb')),
    ('claro-neutro','Claro neutro',('#eff0f1','#fcfcfc','#e3e5e7','#7f8c8d','#232629','#4d5358','#1d6fa8','#ffffff','#1d7542','#8a4500','#b3261e','#1c6ba3')),
    ('escuro-suave','Escuro suave',('#1e1e2e','#313244','#45475a','#7f849c','#cdd6f4','#afb6ce','#89b4fa','#1e1e2e','#a6e3a1','#f9e2af','#f59db5','#89dceb')),
    ('escuro-frio','Escuro frio',('#2e3440','#3b4252','#434c5e','#939eb2','#eceff4','#d8dee9','#88c0d0','#2e3440','#abc395','#ebcb8b','#eaabb1','#a7bed4')),
    ('daltonismo-seguro','Daltonismo seguro',('#15171c','#1e2228','#2a2f37','#8a93a0','#edeff2','#b5bcc6','#56b4e9','#000000','#2bb594','#e69f00','#e8753c','#56b4e9')),
)
PRESETS={ident:{'label':label,'tokens':dict(zip(ROLES,values))} for ident,label,values in PRESET_ROWS}
PRESET_OPTIONS=[{'value':ident,'label':label} for ident,label,_values in PRESET_ROWS]
MESSAGES={
    'unknown_key':'Configuração desconhecida; nada foi alterado',
    'core_readonly':'Esta opção é do Core: altere-a pela própria tela; nada foi alterado',
    'contrast':'Cor não atende ao contraste mínimo e não pode ser corrigida; nada foi alterado',
    'storage':CODE_MESSAGES['preferences_storage_error'],
    'unavailable':CODE_MESSAGES['preferences_unavailable'],
    'profile_name':'Nome inválido: use de 1 a 32 letras sem acento, números, espaço, _ ou -; nada foi alterado',
    'profile_reserved':'Padrão é o perfil inicial: não pode ser criado, renomeado nem excluído; nada foi alterado',
    'profile_exists':'Já existe um perfil com esse nome; nada foi alterado',
    'profile_missing':'Perfil não encontrado; nada foi alterado',
    'profile_active':'O perfil ativo não pode ser excluído: troque de perfil antes; nada foi alterado',
    'profile_limit':f'Limite de {PROFILE_LIMIT} perfis atingido; exclua um perfil antes',
    'autostart_foreign':'Já existe um atalho de inicialização que o Gideon não criou; nada foi alterado',
    'autostart_unavailable':AUTOSTART_NO_COMMAND,
    'autostart_storage':'Não foi possível gravar o atalho de inicialização; nada foi alterado',
}


def _entry(key,section,subtab,typ,default,label,help_,level='basic',mn=None,mx=None,options=None,restart=False,keywords=(),source='app'):
    return {'key':key,'section':section,'subtab':subtab,'type':typ,'default':default,'min':mn,'max':mx,'options':list(options or []),'level':level,'label':label,'help':help_,'restart':restart,'keywords':list(keywords),'source':source}


def _opts(*pairs):
    return [{'value':value,'label':label} for value,label in pairs]


_APARENCIA='Aparência';_GERAL='Geral';_VOZ='Voz e Wake';_AUDIO='Áudio';_DISPOSITIVOS='Dispositivos'
SCHEMA=(
    _entry('theme.mode','Modo','Aparência','enum','system','Modo de cor','Escuro, claro, ou seguir o esquema do sistema.',options=_opts(('system','Seguir o sistema'),('dark','Escuro'),('light','Claro')),keywords=('tema','claro','escuro','dark','light','sistema','modo','cor')),
    _entry('theme.preset','Modo','Aparência','enum','gideon-escuro','Tema','Conjunto de cores pronto. Os ajustes de cor partem dele.',options=PRESET_OPTIONS,keywords=('tema','paleta','preset','cores')),
    _entry('theme.accent','Modo','Aparência','color','','Cor de destaque','Cor das ações principais e do foco. Vazio usa a cor do tema.',keywords=('destaque','acento','accent','cor','botao','foco')),
    _entry('theme.density','Forma e texto','Aparência','float',1.0,'Densidade','Espaço interno de cartões e linhas. 1,00 é o padrão.',mn=0.85,mx=1.25,keywords=('espaco','compacto','densidade','margem')),
    _entry('theme.radius','Forma e texto','Aparência','int',8,'Raio dos cantos','Arredondamento de cartões e botões, em pixels. 0 deixa quadrado.',mn=0,mx=16,keywords=('canto','arredondado','raio','borda')),
    _entry('theme.fontSize','Texto','Aparência','int',14,'Tamanho da letra','Tamanho base do texto, em pixels. O restante escala a partir dele.',mn=12,mx=20,keywords=('fonte','texto','letra','tamanho')),
    _entry('theme.fontFamily','Texto','Aparência','enum','system','Família da fonte','Fontes instaladas no sistema. Não aceita nome livre.',options=_opts(('system','Padrão do sistema'),('sans','Sans-serif instalada'),('serif','Serif instalada')),keywords=('fonte','letra','familia','tipografia')),
    _entry('theme.contrast','Texto','Aparência','enum','normal','Contraste','Alto contraste exige 7:1 no texto e 3:1 nos componentes.',options=_opts(('normal','Normal'),('high','Alto contraste')),keywords=('contraste','acessivel','legibilidade','alto')),
    _entry('theme.lineHeight','Texto','Aparência','float',1.5,'Altura da linha','Espaço entre linhas de texto. 1,5 é o padrão.',level='advanced',mn=1.2,mx=1.8,keywords=('linha','espacamento','texto')),
    _entry('theme.titleWeight','Texto','Aparência','int',700,'Peso do título','Espessura dos títulos de página, de 500 a 800.',level='advanced',mn=500,mx=800,keywords=('negrito','titulo','peso','fonte')),
    _entry('theme.animation','Movimento e superfícies','Aparência','enum','normal','Animações','Reduzida troca movimento por transições de opacidade.',level='advanced',options=_opts(('off','Desligadas'),('reduced','Reduzidas'),('normal','Normais')),keywords=('animacao','movimento','transicao','reduzir')),
    _entry('theme.translucency','Movimento e superfícies','Aparência','int',0,'Translucidez','Desfoque do fundo, em pixels. 0 usa superfície opaca.',level='advanced',mn=0,mx=24,keywords=('blur','transparencia','translucidez','vidro')),
    _entry('theme.shadow','Movimento e superfícies','Aparência','int',30,'Intensidade da sombra','Força da sombra dos cartões, de 0 a 100 por cento.',level='advanced',mn=0,mx=100,keywords=('sombra','profundidade')),
    _entry('theme.orb','Presença','Aparência','bool',True,'Mostrar o orbe do Gideon','Mostra o indicador de estado do assistente.',keywords=('orbe','indicador','bola','estado')),
    _entry('theme.orbSize','Presença','Aparência','enum','medium','Tamanho do orbe','Tamanho do indicador de estado do assistente.',options=_opts(('small','Pequeno'),('medium','Médio')),keywords=('orbe','tamanho')),
    _entry('theme.colors','Cores avançadas','Aparência','json',{},'Cores por papel','Substitui cores por papel. Cada cor passa pela validação de contraste.',level='advanced',keywords=('cor','papel','token','hex','personalizar')),
    _entry('behavior.startTab','Início','Geral','enum','assistente','Aba ao abrir','Aba mostrada quando o app abre.',options=_opts(('assistente','Assistente'),('extensoes','Extensões'),('permissoes','Permissões'),('configuracoes','Configurações'),('diagnostico','Diagnóstico')),keywords=('inicio','abrir','aba','padrao')),
    _entry('behavior.rememberWindow','Janela','Geral','bool',True,'Lembrar tamanho e posição da janela','Reabre a janela onde foi fechada.',keywords=('janela','tamanho','posicao')),
    # WP-17: push-to-talk through the global shortcut (portal GlobalShortcuts). Off by default; the switch asks for consent.
    _entry('shortcut.pushToTalk','Atalhos','Geral','bool',False,'Pressionar para falar com atalho global','Um atalho do sistema inicia a escuta. Desligado por padrão; ligar pede consentimento.',keywords=('atalho','global','falar','pressionar','escuta')),
    _entry('shortcut.pushToTalkTrigger','Atalhos','Geral','string','CTRL+ALT+G','Atalho sugerido','Combinação registrada no portal de atalhos (ex.: CTRL+ALT+G). O sistema pode trocá-la.',keywords=('atalho','combinacao','tecla')),
    _entry('behavior.tips','Ajuda','Geral','bool',True,'Mostrar dicas','Exibe dicas curtas nas telas.',keywords=('dica','ajuda')),
    _entry('behavior.shortcuts','Ajuda','Geral','bool',True,'Atalhos de teclado','Liga os atalhos de teclado neste app.',keywords=('atalho','teclado','ctrl')),
    _entry('behavior.advanced','Opções','Geral','bool',False,'Mostrar opções avançadas','Revela opções avançadas em todas as telas. Não altera valores.',keywords=('avancado','opcoes','avancadas','detalhe')),
    # DIAG-02: the developer mode is the Core preference preferences.developer_mode (src/storage.rs); every page reads it from there.
    _entry('behavior.devMode','Opções','Geral','bool',False,'Modo desenvolvedor','Mostra ferramentas de desenvolvimento em Diagnóstico.',level='dev',keywords=('desenvolvedor','dev','debug','teste'),source='core'),
    _entry('behavior.onboardingDone','Introdução','Geral','bool',False,'Introdução concluída','Marca que a primeira execução guiada já foi vista neste perfil. Refazer fica em Geral.',level='advanced',keywords=('introducao','onboarding','primeira','execucao','guia','boas-vindas')),
    _entry('behavior.toastSeconds','Avisos','Geral','int',4,'Duração dos avisos','Tempo, em segundos, que um aviso fica na tela.',mn=2,mx=10,keywords=('aviso','toast','mensagem','segundos')),
    _entry('behavior.confirmWrites','Avisos','Geral','bool',True,'Confirmar ações que gravam','Pede confirmação antes de ações que gravam dados.',keywords=('confirmar','gravar','salvar','confirmacao')),
    _entry('behavior.reduceMotionFollowSystem','Movimento','Geral','bool',False,'Seguir a preferência de movimento do sistema','Reduz animações quando o sistema pede menos movimento (GNOME: animações desligadas).',level='advanced',keywords=('movimento','reduzir','sistema','animacao')),
    _entry('perf.lowPower','Desempenho','Geral','bool',False,'Modo econômico','Desliga animações e translucidez e reduz sombras. Vale na hora.',keywords=('economico','bateria','desempenho','energia','animacao','sombra','lento')),
    _entry('core.wakePhrase','Frase de despertar',_VOZ,'enum','','Frase de despertar','Só frases certificadas do pacote. A troca vale depois de reiniciar o Core.',restart=True,keywords=('wake','frase','despertar','hey gideon','ativacao'),source='core'),
    _entry('core.sessionTimeoutMs','Sessão',_VOZ,'int',30000,'Prazo da sessão (ms)','Tempo máximo de uma sessão de voz, em milissegundos. Vale na próxima sessão.',level='advanced',mn=50,mx=60000,keywords=('prazo','timeout','sessao','tempo','segundos'),source='core'),
    _entry('core.wakeSensitivity','Detecção',_VOZ,'float',1.0,'Sensibilidade do wake','Ajusta o limiar do detector. Efeito acústico ainda não validado com microfone real.',mn=0.5,mx=1.5,keywords=('sensibilidade','sensivel','limiar','wake','detector','intensidade','despertar'),source='core'),
    _entry('voice.partials','Transcrição',_VOZ,'bool',True,'Mostrar transcrição parcial','Mostra o texto enquanto você fala.',keywords=('parcial','transcricao','ao vivo','legenda')),
    _entry('voice.showConfidence','Transcrição',_VOZ,'bool',False,'Mostrar confiança da transcrição','Exibe a confiança numérica de cada transcrição.',level='advanced',keywords=('confianca','transcricao','numero')),
    _entry('core.responseGain','Volume',_AUDIO,'int',100,'Ganho da resposta por voz','Volume da resposta na saída virtual. 0 por cento é mudo; não altera o volume do sistema.',mn=0,mx=100,keywords=('volume','ganho','resposta','mudo','saida'),source='core'),
    _entry('core.audibleFeedback','Resposta',_AUDIO,'bool',True,'Resposta por voz','Gideon responde em voz alta. Vale a partir da próxima sessão.',keywords=('resposta','voz','audio','falar','som'),source='core'),
    # Device choices come from the Core's audio_devices list (build_schema); the static option is the system default.
    _entry('core.audioInput','Entrada',_DISPOSITIVOS,'enum','default','Microfone (entrada)','Dispositivo de captura da escuta ao vivo. Vale na próxima sessão de voz.',options=_opts(('default','Padrão do sistema')),keywords=('microfone','mic','entrada','captura','dispositivo','input'),source='core'),
    _entry('core.inputConditioning','Entrada',_DISPOSITIVOS,'bool',True,'Melhorar sinal do microfone (automático)','Filtra graves e a componente contínua só para o detector de wake. A fala gravada e a transcrição não mudam. Medido com ruído real do microfone (docs/A9-wake-real-noise.md). Vale na próxima sessão de voz.',keywords=('microfone','ruido','sinal','filtro','graves','wake','deteccao','automatico','melhorar','sinal'),source='core'),
    _entry('core.audioOutput','Saída',_DISPOSITIVOS,'enum','default','Alto-falante (saída)','Dispositivo de reprodução da resposta por voz. Vale na próxima sessão de voz.',options=_opts(('default','Padrão do sistema')),keywords=('alto-falante','saida','reproducao','dispositivo','output','speaker','som'),source='core'),
    _entry('audio.cues','Sinais',_AUDIO,'bool',True,'Sons de início e fim','Toca um sinal ao começar e terminar a escuta.',keywords=('som','sinal','bip','cues','escuta')),
    _entry('core.visualFeedback','Indicadores',_APARENCIA,'bool',True,'Indicador visual de atividade','Mostra o estado do Gideon na tela. Vale a partir da próxima sessão.',keywords=('indicador','visual','atividade','estado'),source='core'),
)
# CFG-06: the Idiomas sub-tab (app/pages/CfgIdiomas.qml) is Core-backed and has no schema row, so search could not reach it.
# These entries are search-only: no value, no default, no QML row and never in SPECS. A result opens the sub-tab
# (CfgSettings.js maps the subtab label 'Idiomas' to cfg_idiomas).
NAV_ENTRIES=(
    {'key':'lang.stt','label':'Idiomas de transcrição (STT)','section':'Idioma','subtab':'Idiomas','help':'Idiomas que o Gideon entende ao ouvir. Só idiomas instalados podem ser escolhidos.','keywords':['idioma','idiomas','transcricao','reconhecimento','stt','ouvir','fala','lingua']},
    {'key':'lang.tts','label':'Idioma da resposta em voz (TTS)','section':'Idioma','subtab':'Idiomas','help':'Idioma em que o Gideon fala. Vale no próximo início do Core.','keywords':['idioma','idiomas','voz','resposta','tts','falar','lingua']},
    {'key':'lang.voice','label':'Voz da resposta em idioma','section':'Idioma','subtab':'Idiomas','help':'Voz usada na resposta em voz. Só vozes instaladas podem ser escolhidas.','keywords':['voz','voice','idioma','tts']},
    {'key':'lang.install','label':'Instalar idioma','section':'Idioma','subtab':'Idiomas','help':'A instalação depende da aprovação do download pelo dono; hoje fica indisponível.','keywords':['instalar','download','baixar','idioma','pacote']},
)
SPECS={spec['key']:spec for spec in SCHEMA}
APP_KEYS=tuple(k for k,spec in SPECS.items() if spec['source']=='app')
CORE_KEYS=tuple(k for k,spec in SPECS.items() if spec['source']=='core')


def parse_color(value):
    """Normalized '#rrggbb' or None. Accepts '#rgb' and '#rrggbb' in any case."""
    if not isinstance(value,str):return None
    match=HEX.fullmatch(value.strip())
    if not match:return None
    digits=match.group(1).lower()
    if len(digits)==3:digits=''.join(c*2 for c in digits)
    return '#'+digits


def _rgb(color):return tuple(int(color[i:i+2],16) for i in (1,3,5))


def _hex(rgb):return '#%02x%02x%02x'%tuple(max(0,min(255,round(c))) for c in rgb)


def _luminance(color):
    def channel(value):
        value=value/255
        return value/12.92 if value<=0.04045 else ((value+0.055)/1.055)**2.4
    red,green,blue=(channel(c) for c in _rgb(color))
    return 0.2126*red+0.7152*green+0.0722*blue


def contrast_ratio(a,b):
    """WCAG 2.1 relative contrast of two colours (1 to 21). Both must be normalized colours."""
    first,second=_luminance(a),_luminance(b)
    high,low=max(first,second),min(first,second)
    return (high+0.05)/(low+0.05)


def mix(a,b,t):
    return _hex(tuple(x+(y-x)*t for x,y in zip(_rgb(a),_rgb(b))))


def best_on(color):
    """Black or white, whichever reads better on `color`."""
    return '#000000' if contrast_ratio(color,'#000000')>=contrast_ratio(color,'#ffffff') else '#ffffff'


def derived(tokens):
    """Derived tokens are calculated from the base roles and never stored (docs/research/ux-temas.md 6.1)."""
    return {'hover':mix(tokens['surface'],tokens['accent'],0.10),'pressed':mix(tokens['surface'],tokens['accent'],0.20),'focus':tokens['accent'],'tint':mix(tokens['bg'],tokens['accent'],0.15)}


def validate_tokens(tokens,high=False):
    """WCAG check of the pairs in ux-temas.md 6.3. Failing foreground tokens move toward black or white until they pass."""
    text_min=7.0 if high else 4.5
    fallback=PRESETS[DEFAULT_PRESET]['tokens']
    colors={};errors=[]
    for role in ROLES:
        color=parse_color(tokens.get(role,fallback[role]))
        if color is None:
            errors.append(f'Cor inválida no papel {role}');color=fallback[role]
        colors[role]=color
    fixes=[]
    pairs=[('accent','bg',3.0),('accent','surface',3.0),('outline','surface',3.0)]+[(fg,bg,text_min) for fg in TEXT_FOREGROUNDS for bg in TEXT_BACKGROUNDS]+[('onAccent','accent',text_min)]
    for fg,bg,minimum in pairs:
        before=contrast_ratio(colors[fg],colors[bg])
        if before>=minimum:continue
        target=best_on(colors[bg]);found=None
        for step in range(401):
            candidate=mix(colors[fg],target,step/400)
            if contrast_ratio(candidate,colors[bg])>=minimum:
                found=candidate;break
        if found is None:
            errors.append(f'{fg} sobre {bg}: contraste {before:.2f}:1, mínimo {minimum:g}:1, sem correção possível');continue
        fixes.append({'token':fg,'from':colors[fg],'to':found,'ratio_before':round(before,2),'ratio_after':round(contrast_ratio(found,colors[bg]),2),'against':bg,'minimum':minimum})
        colors[fg]=found
    return {'ok':not errors,'fixes':fixes,'errors':errors,'tokens':{**colors,**derived(colors)}}


def effective_tokens(values):
    """Preset, then the accent (onAccent is recalculated), then per-role overrides."""
    preset=values.get('theme.preset',DEFAULT_PRESET)
    tokens=dict(PRESETS.get(preset,PRESETS[DEFAULT_PRESET])['tokens'])
    accent=parse_color(values.get('theme.accent') or '')
    if accent:
        tokens['accent']=accent;tokens['onAccent']=best_on(accent)
    for role,color in (values.get('theme.colors') or {}).items():
        if role in COLOR_ROLES and parse_color(color):tokens[role]=parse_color(color)
    return tokens


def enforce(values):
    """Validate the theme in `values` and correct it. Returns (values, fixes, errors). Fixes are stored in the values."""
    values=dict(values);fixes=[]
    high=values.get('theme.contrast')=='high'
    result=None
    for _ in range(4):
        result=validate_tokens(effective_tokens(values),high)
        if not result['fixes']:break
        for fix in result['fixes']:
            if fix['token']=='accent':values['theme.accent']=fix['to']
            else:
                colors=dict(values.get('theme.colors') or {});colors[fix['token']]=fix['to'];values['theme.colors']=colors
            fixes.append(fix)
    else:
        result=validate_tokens(effective_tokens(values),high)
    errors=list(result['errors'])
    if not errors and result['fixes']:errors.append('Correção de contraste não estabilizou')
    if values.get('theme.colors')=={}:values.pop('theme.colors')
    return values,fixes,errors


def _fold(text):
    return unicodedata.normalize('NFKD',str(text)).encode('ascii','ignore').decode('ascii').lower()


def _describe_limit(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def coerce(spec,value,options=None):
    """(value, None) when valid, else (None, reason). `options` overrides the schema options (wake phrases come from the pack)."""
    typ=spec['type'];key=spec['key']
    if typ=='bool':
        return (value,None) if type(value) is bool else (None,'use verdadeiro ou falso')
    if typ in ('int','float'):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):return None,'use um número'
        if typ=='int':
            if isinstance(value,float) and not value.is_integer():return None,'use um número inteiro'
            value=int(value)
        else:value=float(value)
        if (spec['min'] is not None and value<spec['min']) or (spec['max'] is not None and value>spec['max']):
            return None,f"fora do limite ({_describe_limit(spec['min'])} a {_describe_limit(spec['max'])})"
        return value,None
    if typ=='enum':
        allowed=[option['value'] for option in (spec['options'] if options is None else options)]
        return (value,None) if isinstance(value,str) and value in allowed else (None,'opção não existe')
    if typ=='string':
        if not isinstance(value,str) or len(value)>STRING_LIMIT or CONTROL.search(value):return None,'texto inválido'
        return value,None
    if typ=='color':
        if value=='':return '',None
        color=parse_color(value)
        return (color,None) if color else (None,'use uma cor em hexadecimal, como #7aa2f7')
    if typ=='json':
        if key=='theme.colors':
            if isinstance(value,str):
                try:value=json.loads(value)
                except ValueError:return None,'JSON inválido'
            if not isinstance(value,dict):return None,'use um objeto de papel para cor'
            out={}
            for role,color in value.items():
                if role not in COLOR_ROLES:return None,f'papel desconhecido: {role}'
                parsed=parse_color(color)
                if parsed is None:return None,f'cor inválida no papel {role}'
                out[role]=parsed
            return dict(sorted(out.items())),None
        return (value,None) if isinstance(value,dict) else (None,'use um objeto JSON')
    return None,'tipo desconhecido'


DEVICE_CHOICES={'core.audioInput':'audioInputChoices','core.audioOutput':'audioOutputChoices'}
DEVICE_PREF={'core.audioInput':'audio_input_device','core.audioOutput':'audio_output_device'}


def device_options(bridge,key):
    """Options of a device key: the bridge's choices (system default first, then the devices the Core listed)."""
    rows=getattr(bridge,DEVICE_CHOICES[key],None) or []
    return [{'value':row.get('value',''),'label':row.get('text','')} for row in rows if row.get('value')]


def build_schema(bridge=None):
    """Schema as list of dicts. The wake phrase options come from the pack the bridge exposes (wakeChoices); the device options from the Core's device list."""
    entries=copy.deepcopy(list(SCHEMA))
    for entry in entries:
        if entry['key']=='core.wakePhrase' and bridge is not None:
            choices=getattr(bridge,'wakeChoices',None) or []
            entry['options']=[{'value':c.get('id',''),'label':c.get('text','')+(f" ({c['qualification_label']})" if c.get('qualification_label') else '')} for c in choices if c.get('id')]
        if entry['key'] in DEVICE_CHOICES and bridge is not None:
            entry['options']=device_options(bridge,entry['key']) or entry['options']
    return entries


# ---- paths -------------------------------------------------------------------------------------------------------------
def _xdg_config_home():
    base=os.environ.get('XDG_CONFIG_HOME','')
    return Path(base) if base and os.path.isabs(base) else Path.home()/'.config'


def _config_base(config_home=None):
    return Path(config_home) if config_home else _xdg_config_home()


def _root_hash(root):
    return hashlib.sha256(str(Path(root).resolve()).encode('utf-8')).hexdigest()[:16] if root else 'default'


def profile_dir(root=None,config_home=None):
    """$XDG_CONFIG_HOME/gideon-app/<core hash>: the settings profiles of one Core root."""
    return _config_base(config_home)/'gideon-app'/_root_hash(root)


def settings_path(root=None,config_home=None,name=PROFILE_DEFAULT):
    """File of one settings profile (default: 'Padrão', the profile every install starts with)."""
    return profile_dir(root,config_home)/f'{name}.json'


def _legacy_path(root,config_home):
    """The single-file layout of earlier builds: $XDG_CONFIG_HOME/gideon-app/<core hash>.json."""
    return _config_base(config_home)/'gideon-app'/f'{_root_hash(root)}.json'


def profile_name_problem(name):
    """None when `name` may be created or renamed to, else the reason (Portuguese, for the user)."""
    if not isinstance(name,str) or not PROFILE_NAME.fullmatch(name) or name!=name.strip():return MESSAGES['profile_name']
    if _fold(name)==_fold(PROFILE_DEFAULT):return MESSAGES['profile_reserved']
    return None


def _atomic_write(path,payload,mode=0o600,private_folder=True):
    folder=path.parent
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if private_folder:os.chmod(folder,0o700)
    fd,tmp=tempfile.mkstemp(dir=str(folder),prefix='.'+path.name+'.',suffix='.tmp')
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as handle:
            handle.write(payload);handle.flush();os.fsync(handle.fileno())
        os.replace(tmp,path)
    except BaseException:
        try:os.unlink(tmp)
        except OSError:pass
        raise
    try:
        dir_fd=os.open(str(folder),os.O_RDONLY)
        try:os.fsync(dir_fd)
        finally:os.close(dir_fd)
    except OSError:pass


def _payload(values):
    data={'schemaVersion':SCHEMA_VERSION,'values':dict(sorted(values.items()))}
    return (json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8')


def _fail(code,error,value=None):
    return {'ok':False,'code':code,'error':error,'value':value}


def _store(values,key,value):
    if value==SPECS[key]['default']:values.pop(key,None)
    else:values[key]=value


# ---- autostart (XDG) ---------------------------------------------------------------------------------------------------
def _profile_of(root,install):
    """The Core profile name when `root` is <install>/profiles/<name> (or .../<name>/core), else None."""
    if not root:return None
    path=Path(root).resolve();profiles=install/'profiles'
    if path.parent==profiles:name=path.name
    elif path.name=='core' and path.parent.parent==profiles:name=path.parent.name
    else:return None
    return name if PROFILE_ARG.fullmatch(name) and not name.startswith('.') else None


def discover_launch(root=None):
    """(argv, None) for the command that starts this install and profile, or (None, reason).
    GIDEON_LAUNCH_CMD (an absolute executable and its arguments) wins; otherwise the packaged layout:
    <install>/versions/<v>/app/uisettings.py with <install>/current/bin/gideon-launch."""
    override=os.environ.get(LAUNCH_ENV,'').strip()
    if override:
        try:argv=shlex.split(override)
        except ValueError:return None,AUTOSTART_NO_COMMAND
        if argv and os.path.isabs(argv[0]) and os.access(argv[0],os.X_OK):return argv,None
        return None,AUTOSTART_NO_COMMAND
    package=Path(__file__).resolve().parents[1]
    if len(package.parents)<2 or package.parent.name!='versions':return None,AUTOSTART_NO_COMMAND
    install=package.parent.parent
    profile=_profile_of(root,install)
    launch=install/'current'/'bin'/'gideon-launch'
    if profile is None or not os.access(launch,os.X_OK):return None,AUTOSTART_NO_COMMAND
    return [str(launch),'--install-root',str(install),profile],None


def _exec_value(argv):
    """Desktop Entry Exec value: quoted arguments (XDG Exec rules), then string escaping and %% for field codes."""
    parts=[]
    for arg in argv:
        if any(ord(c)<32 for c in arg):return None
        parts.append(arg if PLAIN_ARG.fullmatch(arg) else '"'+re.sub(r'(["`$\\])',r'\\\1',arg)+'"')
    return ' '.join(parts).replace('\\','\\\\').replace('%','%%')


def _desktop_text(exec_value):
    return ('[Desktop Entry]\nType=Application\nName=Gideon\nComment=Abre o Gideon ao entrar no computador\n'
            f'Exec={exec_value}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n{AUTOSTART_MARK}\n')


def _autostart_file(config_home=None):
    return _config_base(config_home)/'autostart'/AUTOSTART_NAME


def _read_autostart(path):
    """None when absent. Else {'managed','enabled'}: enabled when the entry is not Hidden and not switched off by X-GNOME."""
    try:
        if not path.exists():return None
        if path.stat().st_size>FILE_LIMIT:raise ValueError('too large')
        lines={line.strip() for line in path.read_text(encoding='utf-8').splitlines()}
    except (OSError,ValueError):
        return {'managed':False,'enabled':False}
    managed=AUTOSTART_MARK in lines
    enabled=('Hidden=true' not in lines) and ('X-GNOME-Autostart-enabled=false' not in lines)
    return {'managed':managed,'enabled':enabled}


class UiSettings(QObject):
    changed=Signal(str)
    valuesChanged=Signal()

    def __init__(self,bridge=None,root=None,config_home=None,parent=None):
        super().__init__(parent)
        self._bridge=bridge
        self._root=root;self._config_home=config_home
        self._values={}
        self._revision=0
        self._reduced_system=None
        self._migrate_legacy()
        self.profile=self._read_active()
        self.path=settings_path(root,config_home,self.profile)
        self._values=self._load_values(self.path)
        set_code_detail(bool(self._values.get('behavior.advanced',False)))
        if bridge is not None:
            for name in ('preferencesChanged','packChanged','audioChanged'):
                signal=getattr(bridge,name,None)
                if signal is not None:signal.connect(self._core_changed)
        self._core_cache=self._core_snapshot()

    # ---- profiles: files and active profile
    def _dir(self):return profile_dir(self._root,self._config_home)

    def _file(self,name):return settings_path(self._root,self._config_home,name)

    def _migrate_legacy(self):
        """Earlier builds kept one file per Core root; it becomes the 'Padrão' profile (moved, never copied)."""
        legacy=_legacy_path(self._root,self._config_home)
        target=self._file(PROFILE_DEFAULT)
        try:
            if legacy.exists() and not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                os.replace(legacy,target)
        except OSError:pass

    def _names(self):
        names={PROFILE_DEFAULT}
        try:
            for path in self._dir().glob('*.json'):
                stem=path.stem
                if path.name!=ACTIVE_FILE and (stem==PROFILE_DEFAULT or PROFILE_NAME.fullmatch(stem)):names.add(stem)
        except OSError:pass
        return names

    def _read_active(self):
        try:
            data=json.loads((self._dir()/ACTIVE_FILE).read_bytes().decode('utf-8'))
            name=data.get('active') if isinstance(data,dict) else None
        except (OSError,ValueError):name=None
        return name if isinstance(name,str) and name in self._names() else PROFILE_DEFAULT

    def _write_active(self,name):
        payload=(json.dumps({'schemaVersion':SCHEMA_VERSION,'active':name},ensure_ascii=False,sort_keys=True)+'\n').encode('utf-8')
        try:
            _atomic_write(self._dir()/ACTIVE_FILE,payload)
            return True
        except OSError:
            return False

    # ---- persistence
    def _load_values(self,path):
        """Validated values of one profile file. A file that cannot be read is moved aside (.bad) and gives defaults."""
        try:
            if not path.exists():return {}
            if path.stat().st_size>FILE_LIMIT:raise ValueError('file too large')
            data=json.loads(path.read_bytes().decode('utf-8'))
            if not isinstance(data,dict) or data.get('schemaVersion')!=SCHEMA_VERSION or not isinstance(data.get('values'),dict):raise ValueError('unexpected shape')
        except (OSError,ValueError):
            self._quarantine(path);return {}
        values={}
        for key,raw in data['values'].items():
            spec=SPECS.get(key)
            if spec is None or spec['source']!='app':continue
            value,reason=coerce(spec,raw)
            if reason is None:_store(values,key,value)
        values,_fixes,errors=enforce(values)
        if errors:
            values.pop('theme.accent',None);values.pop('theme.colors',None)
        return values

    def _quarantine(self,path):
        try:os.replace(path,path.with_name(path.name+'.bad'))
        except OSError:pass

    def _save(self):
        try:
            _atomic_write(self.path,_payload(self._values))
            return True
        except OSError:
            return False

    def _commit(self,new):
        """Save `new` as the app values. Returns False and keeps the old values when the file cannot be written."""
        old=self._values
        self._values=new
        if not self._save():
            self._values=old
            return False
        changed_keys=[key for key in APP_KEYS if self._value_in(old,key)!=self._value_in(new,key)]
        self._revision+=1
        for key in changed_keys:self.changed.emit(key)
        self.valuesChanged.emit()
        if 'behavior.advanced' in changed_keys:set_code_detail(bool(self._current('behavior.advanced')))
        return True

    # ---- values
    def _value_in(self,values,key):
        return copy.deepcopy(values[key]) if key in values else copy.deepcopy(SPECS[key]['default'])

    def _current(self,key):
        if SPECS[key]['source']=='core':return self._core_value(key)
        return self._value_in(self._values,key)

    def _core_value(self,key):
        bridge=self._bridge
        default=SPECS[key]['default']
        if bridge is None:return default
        prefs=getattr(bridge,'snapshot',{}).get('preferences') or {}
        if key=='core.wakePhrase':
            pack=getattr(bridge,'snapshot',{}).get('base_pack') or {}
            return prefs.get('wake_phrase') or pack.get('default_phrase') or ''
        if key in DEVICE_PREF:return prefs.get(DEVICE_PREF[key]) or default
        readers={'behavior.devMode':'developerMode','core.responseGain':'outputVolume','core.audibleFeedback':'audibleFeedback','core.visualFeedback':'visualFeedback','core.sessionTimeoutMs':'sessionTimeout','core.wakeSensitivity':'wakeSensitivity','core.inputConditioning':'inputConditioningOn'}
        return getattr(bridge,readers[key],default)

    def _core_snapshot(self):
        return {key:self._core_value(key) for key in CORE_KEYS}

    def _core_changed(self):
        self._core_cache=self._core_snapshot()
        self.valuesChanged.emit()

    def _options(self,spec):
        if spec['key']=='core.wakePhrase' or spec['key'] in DEVICE_CHOICES:
            return next(entry for entry in build_schema(self._bridge) if entry['key']==spec['key'])['options']
        return spec['options']

    def _set_core(self,spec,value):
        bridge=self._bridge;key=spec['key'];current=self._current(key)
        if bridge is None or not getattr(bridge,'preferencesAvailable',False):
            return _fail('preferences_unavailable',MESSAGES['unavailable'],current)
        coerced,reason=coerce(spec,value,self._options(spec))
        if reason is not None:
            return _fail('invalid_value',f'Valor recusado: {reason}; nada foi alterado',current)
        # The wake phrase compares with the saved preference, not the effective phrase: with none saved the pack default
        # is in effect, and choosing that default must still be saved (otherwise the Core never gets the choice).
        if key=='core.wakePhrase':unchanged=coerced==((getattr(bridge,'snapshot',None) or {}).get('preferences') or {}).get('wake_phrase')
        else:unchanged=coerced==current
        if unchanged:
            return {'ok':True,'value':coerced,'pending':False}
        if key=='core.wakePhrase':bridge.selectWake(coerced)
        elif key=='core.responseGain':bridge.saveFeedback(bool(bridge.visualFeedback),int(coerced))
        elif key=='core.visualFeedback':bridge.saveFeedback(bool(coerced),int(bridge.outputVolume))
        elif key=='core.audibleFeedback':bridge.savePreferences(bool(coerced),int(bridge.sessionTimeout))
        elif key=='core.sessionTimeoutMs':bridge.savePreferences(bool(bridge.audibleFeedback),int(coerced))
        elif key=='behavior.devMode':bridge.setDeveloperMode(bool(coerced))
        elif key=='core.wakeSensitivity':bridge.setWakeSensitivity(float(coerced))
        elif key=='core.inputConditioning':bridge.setInputConditioning(bool(coerced))
        elif key in DEVICE_PREF:
            # The Core takes both device names in one request; the other one keeps its current value.
            other='core.audioOutput' if key=='core.audioInput' else 'core.audioInput'
            inputs,outputs=(coerced,self._current(other)) if key=='core.audioInput' else (self._current(other),coerced)
            bridge.setAudioDevices(inputs,outputs)
        result={'ok':True,'value':coerced,'pending':True}
        if spec['restart']:result['restart']=True
        return result

    # ---- schema and values exposed to QML
    @Property('QVariantList',notify=valuesChanged)
    def schema(self):return build_schema(self._bridge)

    @Property('QVariantMap',notify=valuesChanged)
    def values(self):return {key:self._current(key) for key in SPECS}

    @Property('QVariantList',notify=valuesChanged)
    def modifiedKeys(self):return sorted(key for key in self._values if key in SPECS)

    @Property(int,notify=valuesChanged)
    def revision(self):return self._revision

    @Property(str,notify=valuesChanged)
    def activeProfile(self):return self.profile

    @Property(bool,notify=valuesChanged)
    def noOnboarding(self):
        """True when GIDEON_UI_NO_ONBOARDING=1: explorers and gates start without the first-run guide."""
        return os.environ.get(ONBOARDING_ENV,'')=='1'

    @Property(bool,notify=valuesChanged)
    def reducedMotionSystem(self):
        """The desktop asks for less motion (GNOME enable-animations false). Probed once; False when unknown."""
        if self._reduced_system is None:self._reduced_system=_system_reduced_motion()
        return self._reduced_system

    @Slot(str,'QVariant',result='QVariantMap')
    def set(self,key,value):
        spec=SPECS.get(key)
        if spec is None:return _fail('unknown_key',MESSAGES['unknown_key'])
        if spec['source']=='core':return self._set_core(spec,value)
        current=self._current(key)
        coerced,reason=coerce(spec,value,self._options(spec))
        if reason is not None:return _fail('invalid_value',f'Valor recusado: {reason}; nada foi alterado',current)
        new=dict(self._values);_store(new,key,coerced);corrected=[]
        if key in THEME_KEYS:
            new,fixes,errors=enforce(new)
            if errors:return _fail('contrast',MESSAGES['contrast'],current)
            corrected=fixes
        if not self._commit(new):return _fail('storage',MESSAGES['storage'],current)
        result={'ok':True,'value':self._current(key)}
        if corrected:result['corrected']=corrected
        return result

    @Slot(str,result='QVariantMap')
    def reset(self,key):
        spec=SPECS.get(key)
        if spec is None:return _fail('unknown_key',MESSAGES['unknown_key'])
        if spec['source']=='core':return _fail('core_readonly',MESSAGES['core_readonly'],self._current(key))
        new=dict(self._values);new.pop(key,None);corrected=[]
        if key in THEME_KEYS:
            new,fixes,errors=enforce(new)
            if errors:return _fail('contrast',MESSAGES['contrast'],self._current(key))
            corrected=fixes
        if not self._commit(new):return _fail('storage',MESSAGES['storage'],self._current(key))
        result={'ok':True,'value':self._current(key)}
        if corrected:result['corrected']=corrected
        return result

    @Slot(result='QVariantMap')
    def resetAll(self):
        count=len(self._values)
        if not self._commit({}):return _fail('storage',MESSAGES['storage'])
        return {'ok':True,'count':count}

    @Slot(result=str)
    def exportJson(self):
        data={'kind':'gideon-ui-settings','schemaVersion':SCHEMA_VERSION,'values':dict(sorted(self._values.items()))}
        return json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)

    @Slot(str,result='QVariantMap')
    def importJson(self,text):
        def refuse(error):
            return {'ok':False,'applied':0,'rejected':[],'error':error}
        if not isinstance(text,str) or not text.strip() or len(text.encode('utf-8'))>IMPORT_LIMIT:
            return refuse('Arquivo vazio ou grande demais (limite de 64 KiB)')
        try:data=json.loads(text)
        except ValueError:return refuse('Arquivo não é JSON válido')
        if not isinstance(data,dict) or data.get('schemaVersion')!=SCHEMA_VERSION or not isinstance(data.get('values'),dict):
            return refuse('Formato ou versão de configuração não suportada')
        new=dict(self._values);rejected=[];accepted=[]
        for key,raw in data['values'].items():
            spec=SPECS.get(key)
            if spec is None:
                rejected.append({'key':str(key),'error':'Configuração desconhecida'});continue
            if spec['source']=='core':
                rejected.append({'key':key,'error':'Opção do Core: não é importada'});continue
            coerced,reason=coerce(spec,raw,self._options(spec))
            if reason is not None:
                rejected.append({'key':key,'error':reason});continue
            _store(new,key,coerced);accepted.append(key)
        new,fixes,errors=enforce(new)
        if errors:
            for key in THEME_KEYS:
                if key in self._values:new[key]=self._values[key]
                else:new.pop(key,None)
            rejected.append({'key':'theme','error':'Combinação de cores não atende ao contraste mínimo; tema anterior mantido'})
            accepted=[key for key in accepted if key not in THEME_KEYS]
        if not self._commit(new):return refuse(MESSAGES['storage'])
        return {'ok':True,'applied':len(accepted),'rejected':rejected,'corrected':fixes}

    @Slot(str,result='QVariantList')
    def search(self,query):
        phrase=_fold(query).strip()
        tokens=phrase.split()
        if not tokens:return []
        results=[]
        for spec in SCHEMA+NAV_ENTRIES:
            label=_fold(spec['label']);keywords=_fold(' '.join(spec['keywords']));help_text=_fold(spec['help'])
            group=_fold(spec['section']+' '+spec['subtab']);key=_fold(spec['key'])
            score=0;matched=True
            for token in tokens:
                best=0
                if token in label:best=max(best,4)
                if token in keywords or token in key:best=max(best,3)
                if token in group:best=max(best,2)
                if token in help_text:best=max(best,1)
                if best==0:
                    matched=False;break
                score+=best
            if not matched:continue
            if label==phrase:score+=10
            elif label.startswith(phrase):score+=5
            results.append({'key':spec['key'],'label':spec['label'],'section':spec['section'],'subtab':spec['subtab'],'score':score})
        results.sort(key=lambda row:(-row['score'],row['key']))
        return results

    @Slot(str,result='QVariantMap')
    def presetTokens(self,name):
        preset=PRESETS.get(name)
        if preset is None:return {}
        tokens=dict(preset['tokens']);tokens.update(derived(tokens))
        return tokens

    @Slot('QVariantMap',result='QVariantMap')
    def validateTheme(self,tokens):
        result=validate_tokens(dict(tokens or {}),self._current('theme.contrast')=='high')
        return {'ok':result['ok'],'fixes':result['fixes'],'errors':result['errors'],'tokens':result['tokens']}

    @Slot(str,str,result=float)
    def contrast(self,a,b):
        first,second=parse_color(a),parse_color(b)
        if first is None or second is None:return 0.0
        return contrast_ratio(first,second)

    # ---- settings profiles (docs/ui-spec/01-ajustes-minimalismo.md 3.1)
    @Slot(result='QVariantList')
    def profiles(self):
        return [{'name':name,'active':name==self.profile,'default':name==PROFILE_DEFAULT} for name in sorted(self._names(),key=lambda n:(n!=PROFILE_DEFAULT,_fold(n)))]

    def _known(self,name):return isinstance(name,str) and name in self._names()

    def _values_of(self,name):
        return dict(self._values) if name==self.profile else self._load_values(self._file(name))

    @Slot(str,result='QVariantMap')
    def createProfile(self,name):
        problem=profile_name_problem(name)
        if problem is not None:return _fail('profile_name',problem)
        if any(_fold(existing)==_fold(name) for existing in self._names()):return _fail('profile_exists',MESSAGES['profile_exists'])
        if len(self._names())>=PROFILE_LIMIT:return _fail('profile_limit',MESSAGES['profile_limit'])
        try:_atomic_write(self._file(name),_payload({}))
        except OSError:return _fail('storage',MESSAGES['storage'])
        return {'ok':True,'name':name}

    @Slot(str,str,result='QVariantMap')
    def duplicateProfile(self,source,name):
        if not self._known(source):return _fail('profile_missing',MESSAGES['profile_missing'])
        problem=profile_name_problem(name)
        if problem is not None:return _fail('profile_name',problem)
        if any(_fold(existing)==_fold(name) for existing in self._names()):return _fail('profile_exists',MESSAGES['profile_exists'])
        if len(self._names())>=PROFILE_LIMIT:return _fail('profile_limit',MESSAGES['profile_limit'])
        try:_atomic_write(self._file(name),_payload(self._values_of(source)))
        except OSError:return _fail('storage',MESSAGES['storage'])
        return {'ok':True,'name':name}

    @Slot(str,result='QVariantMap')
    def switchProfile(self,name):
        if not self._known(name):return _fail('profile_missing',MESSAGES['profile_missing'])
        if name==self.profile:return {'ok':True,'name':name,'changed':0}
        old_profile,old_path,old_values=self.profile,self.path,self._values
        new_path=self._file(name);new_values=self._load_values(new_path)
        if not self._write_active(name):return _fail('storage',MESSAGES['storage'])
        self.profile=name;self.path=new_path;self._values=new_values
        changed_keys=[key for key in APP_KEYS if self._value_in(old_values,key)!=self._value_in(new_values,key)]
        self._revision+=1
        for key in changed_keys:self.changed.emit(key)
        self.valuesChanged.emit()
        set_code_detail(bool(self._current('behavior.advanced')))
        return {'ok':True,'name':name,'changed':len(changed_keys),'previous':old_profile,'path':str(old_path)}

    @Slot(str,result='QVariantMap')
    def deleteProfile(self,name):
        if name==PROFILE_DEFAULT:return _fail('profile_reserved',MESSAGES['profile_reserved'])
        if not self._known(name):return _fail('profile_missing',MESSAGES['profile_missing'])
        if name==self.profile:return _fail('profile_active',MESSAGES['profile_active'])
        try:os.unlink(self._file(name))
        except OSError:return _fail('storage',MESSAGES['storage'])
        return {'ok':True,'name':name}

    @Slot(str,str,result='QVariantMap')
    def renameProfile(self,old,new):
        if old==PROFILE_DEFAULT:return _fail('profile_reserved',MESSAGES['profile_reserved'])
        if not self._known(old):return _fail('profile_missing',MESSAGES['profile_missing'])
        problem=profile_name_problem(new)
        if problem is not None:return _fail('profile_name',problem)
        if any(_fold(existing)==_fold(new) and existing!=old for existing in self._names()):return _fail('profile_exists',MESSAGES['profile_exists'])
        source,target=self._file(old),self._file(new)
        if source==target:return {'ok':True,'name':new}
        try:os.replace(source,target)
        except OSError:return _fail('storage',MESSAGES['storage'])
        if old==self.profile:
            if not self._write_active(new):
                try:os.replace(target,source)
                except OSError:pass
                return _fail('storage',MESSAGES['storage'])
            self.profile=new;self.path=target
            self.valuesChanged.emit()
        return {'ok':True,'name':new}

    # ---- Iniciar no login (XDG autostart)
    @Slot(result='QVariantMap')
    def autostartState(self):
        argv,reason=discover_launch(self._root)
        path=_autostart_file(self._config_home)
        found=_read_autostart(path)
        return {'supported':argv is not None,'reason':reason or '','path':str(path),'exists':found is not None,
                'managed':bool(found and found['managed']),'enabled':bool(found and found['enabled'])}

    @Slot(bool,result='QVariantMap')
    def setAutostart(self,enable):
        path=_autostart_file(self._config_home)
        found=_read_autostart(path)
        if not enable:
            if found is None:return {'ok':True,'enabled':False}
            if not found['managed']:return _fail('autostart_foreign',MESSAGES['autostart_foreign'])
            try:os.unlink(path)
            except OSError:return _fail('autostart_storage',MESSAGES['autostart_storage'])
            return {'ok':True,'enabled':False}
        argv,reason=discover_launch(self._root)
        if argv is None:return _fail('autostart_unavailable',MESSAGES['autostart_unavailable'])
        if found is not None and not found['managed']:return _fail('autostart_foreign',MESSAGES['autostart_foreign'])
        exec_value=_exec_value(argv)
        if exec_value is None:return _fail('autostart_unavailable',MESSAGES['autostart_unavailable'])
        try:_atomic_write(path,_desktop_text(exec_value).encode('utf-8'),mode=0o644,private_folder=False)
        except OSError:return _fail('autostart_storage',MESSAGES['autostart_storage'])
        return {'ok':True,'enabled':True}


def _system_reduced_motion():
    """GNOME's 'enable-animations' is false. Other desktops expose nothing Qt can read here, so they count as not reduced."""
    try:
        done=subprocess.run(['gsettings','get','org.gnome.desktop.interface','enable-animations'],capture_output=True,text=True,timeout=1,env={'PATH':'/usr/bin:/bin'})
    except (OSError,subprocess.SubprocessError):return False
    return done.returncode==0 and done.stdout.strip()=='false'
