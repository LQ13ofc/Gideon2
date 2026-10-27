#!/usr/bin/env python3
"""WP-20 G5c, run once: move the Portuguese message objects out of app/bridge.py into app/msgs_<topic>.py.

plan    print, per module, the moved objects, their Portuguese strings and every name that cannot be resolved (writes nothing)
split   write app/msgs_*.py, remove the moved objects from app/bridge.py, and move the translate helpers into app/translations.py
verify  SNAPSHOT: compare the bridge snapshot taken before `split` with the new bridge and modules, object by object

A moved object is copied as its own source text. The only change inside an object is in the op tables: each `OPS` and
`PENDING` dict, and each `OPS.update({...})` / `PENDING.update({...})`, is split by entry, and every entry (with its
comment lines) goes to the module of its op key. The dicts stay plain dicts; the module that owns OPS is msgs_misc.

Usage: python3 scripts/tools/split_bridge_messages.py plan|split
       python3 scripts/tools/split_bridge_messages.py verify SNAPSHOT_PATH
"""
import ast
import builtins
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'app'
BRIDGE = APP / 'bridge.py'
TRANSLATIONS = APP / 'translations.py'
HELPERS = ('CONTEXT', '_tr', '_fill', '_Messages')
OP_TABLES = ('OPS', 'PENDING')
OP_HOME = 'msgs_misc'
OP_PREFIXES = (
    (('skill_', 'hub_', 'plugin_', 'capability_', 'registry_'), 'msgs_skills_hub'),
    (('connection_',), 'msgs_connections'),
    (('secret_', 'llm_', 'agent_', 'tool_'), 'msgs_llm_models'),
    (('audio_', 'listen_', 'live_audio_', 'real_actions_'), 'msgs_audio'),
)

MODULES = {
    'msgs_errors': ('PREFS_DONE', 'STALE_MESSAGE', 'GENERIC_FAILURE', 'CODE_MESSAGES', 'CAPABILITY_MESSAGES',
                    'code_message', 'text_problem', 'bounded_output'),
    'msgs_audio': ('DEFAULT_DEVICE_LABEL', 'DEFAULT_MARK', 'UNAVAILABLE_DEVICE_LABEL', 'AUDIO_REASON_MESSAGES',
                   'LIVE_ERROR_MESSAGES', 'RESTORE_BUSY_TEXT', 'RESTORE_BACKUP_TEXT', 'SENSITIVITY_RANGE_TEXT',
                   'DEVICE_INVALID_TEXT', 'REAL_KIND_TEXT', 'REAL_ACTION_MESSAGES', 'COMMAND_CODE_MESSAGES',
                   'LIVE_WARNING_TEXTS', 'PROBE_VERDICT_TEXTS', 'ZONE_TEXTS', 'FLOOR_TEXTS', 'REC_PROBLEM_TEXT',
                   'REC_ERROR_TEXT', 'live_state_text', 'live_input_text', 'real_action_line', 'real_actions_state',
                   'live_output_text', 'devices_status', 'level_view', 'live_hint_view', 'very_noisy_text',
                   'recommendation_banner', 'recommendation_view'),
    'msgs_connections': ('CONN_MESSAGES', 'REG_VISUAL_WARNING', 'REG_MESSAGES', 'PERMISSION_LABELS', 'EFFECT_TEXT',
                         'RISK_TEXT', 'conn_label_problem', 'display_permission', 'display_effect', 'display_risk',
                         'grant_rows', 'pending_count'),
    'msgs_skills_hub': ('SKILL_REASON_MESSAGES', 'SKILL_OP_MESSAGES', 'PENDING_SKILL_DRAFT', 'HUB_UPLOAD_MESSAGES',
                        'HUB_REASON_LABELS', 'skill_json', 'skill_id_problem', 'skill_description_problem',
                        'package_info', 'hub_storage', 'capability_request', 'json_depth_ok'),
    'msgs_llm_models': ('MODEL_STATUS_TEXTS', 'FEATURE_LABELS', 'AGENT_STATE_LABELS', 'CHAT_STATE_LABELS',
                        'CHAT_ERROR_BANNERS', 'custom_form_problem', 'custom_model', 'llm_config_problem',
                        'target_for', 'chat_problem', 'agent_goal_problem'),
    'msgs_perception': ('PERCEPTION_LABELS', 'PERCEPTION_VALUES', 'PERCEPTION_MESSAGES', 'PERCEPTION_INDICATOR_TEXTS',
                        'perception_input_problem', 'perception_text'),
    'msgs_misc': ('PERSONAL_MESSAGES', 'PHRASE_MESSAGES', 'DIAG_LABELS', 'WAKE_QUALIFICATION_LABELS',
                  'LANGUAGE_LABELS', 'RECEIPT_PREFIXES', 'display_receipt', 'display_wake_choice',
                  'display_wake_entry', 'RESTART_WAIT_TEXT', 'RESTART_BACK_TEXT', 'RESTART_TIMEOUT_TEXT',
                  'OPS', 'PENDING'),
}

DOC = {
    'msgs_errors': 'Core error codes and the general failure texts. Codes stay as they are; only the text is translated.',
    'msgs_audio': 'Microphone, speaker, live audio and microphone assistant texts.',
    'msgs_connections': 'Connection accounts, registry and permission texts.',
    'msgs_skills_hub': 'Skills, Hub and plugin capability texts.',
    'msgs_llm_models': 'LLM model, agent and chat texts.',
    'msgs_perception': 'Perception and action (camera, shortcuts, display) texts.',
    'msgs_misc': 'Personal areas, wake phrases, diagnostics, language and the op table of the Core requests.',
}

PT = re.compile('[àáâãçéêíóôõúÀÁÂÃÇÉÊÍÓÔÕÚ]|\\b(?:de|do|da|dos|das|não|para|com|sem|uma|você|seu|sua|foi|está|são|'
                'nenhum|nenhuma|Core|salvo|salva|escolha|Falha|Concluído|Pronto|Modo|Escuta|Erro|Tente|Clique|'
                'Digite|ligado|desligado|ao|pelo|pela|em|sim|pendente|aguardando|Aguardando|Enviando|Salvando)\\b')


def module_of_op(key):
    for prefixes, module in OP_PREFIXES:
        if key.startswith(prefixes):
            return module
    return OP_HOME


def loads_of(tree):
    stores, loads = set(), set()
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Name):
            (loads if isinstance(sub.ctx, ast.Load) else stores).add(sub.id)
        elif isinstance(sub, ast.arg):
            stores.add(sub.arg)
        elif isinstance(sub, (ast.FunctionDef, ast.ClassDef)):
            stores.add(sub.name)
    return loads - stores


def top_names(node):
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return [node.name]
    return []


def collect(path):
    """Pieces of the moved objects, the removal spans in the file, and the bridge's own imports."""
    src = path.read_bytes()
    tree = ast.parse(src)
    starts = [0] + [i + 1 for i, byte in enumerate(src) if byte == 10]

    def pos(lineno, col):
        return starts[lineno - 1] + col

    def line(number):
        return src[starts[number - 1]:starts[number] if number < len(starts) else len(src)]

    def head_of(lineno):
        """First line of a statement including the comment lines directly above it (kept with the statement)."""
        first, number = lineno, lineno - 1
        while number >= 1 and line(number).lstrip().startswith(b'#'):
            first, number = number, number - 1
        return first

    pieces, helper_texts, spans, imports = [], [], [], {}
    sequence = [0]

    def add(module, order, text, op=False):
        sequence[0] += 1
        piece = {'module': module, 'order': (order, sequence[0]), 'text': text, 'op': op}
        pieces.append(piece)
        return piece

    def stmt_span(node):
        head = head_of(node.lineno)
        start = starts[head - 1] if head < node.lineno else pos(node.lineno, node.col_offset)
        return start, pos(node.end_lineno, node.end_col_offset)

    def text_of(a, b):
        return src[a:b].decode('utf-8')

    def comment_lines(first, stop):
        return [line(n).strip().decode('utf-8') for n in range(first, stop) if line(n).lstrip().startswith(b'#')]

    def split_dict(name, dict_node, order, comment_head):
        """Entries of an op table grouped by module, one `name.update({...})` per module. Comment lines inside the
        dict travel with the entry below them; the comments above the statement go with its first group."""
        entries = []
        before = []
        prev_end = dict_node.lineno
        for key, value in zip(dict_node.keys, dict_node.values):
            before += comment_lines(prev_end + 1, key.lineno)
            text = text_of(pos(key.lineno, key.col_offset), pos(value.end_lineno, value.end_col_offset))
            entries.append((module_of_op(key.value), before, text))
            before = []
            prev_end = value.end_lineno
        trailing = comment_lines(prev_end + 1, dict_node.end_lineno)
        last_module = entries[-1][0]
        order_modules = []
        for module, _, _ in entries:
            if module not in order_modules:
                order_modules.append(module)
        for index, module in enumerate(order_modules):
            body = [f'    {c}' for c in comment_head] if index == 0 else []
            for entry_module, comments, text in entries:
                if entry_module == module:
                    body += [f'    {c}' for c in comments]
                    body.append(f'    {text},')
            if module == last_module:
                body += [f'    {c}' for c in trailing]
            add(module, order, name + '.update({\n' + '\n'.join(body) + '\n})', op=True)

    for index, node in enumerate(tree.body):
        if index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split('.')[0]
                if isinstance(node, ast.Import):
                    imports[bound] = f'import {alias.name}' + (f' as {alias.asname}' if alias.asname else '')
                else:
                    imports[bound] = f'from {node.module} import {alias.name}' + (f' as {alias.asname}' if alias.asname else '')
            continue
        names = top_names(node)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            target = node.value.func.value
            method = node.value.func.attr
            if isinstance(target, ast.Name) and target.id in OP_TABLES and method == 'update' and node.value.args \
                    and isinstance(node.value.args[0], ast.Dict):
                a, b = stmt_span(node)
                head = head_of(node.lineno)
                head_lines = [line(n).strip().decode('utf-8') for n in range(head, node.lineno)]
                split_dict(target.id, node.value.args[0], index, head_lines)
                spans.append((a, b, None))
                continue
            if isinstance(target, ast.Name) and target.id == 'CODE_MESSAGES' and method in ('update', 'setdefault') \
                    and any(isinstance(s, ast.Constant) and isinstance(s.value, str) and PT.search(s.value)
                            for s in ast.walk(node)):
                a, b = stmt_span(node)
                piece = add('msgs_errors', index, text_of(a, b))
                spans.append((a, b, piece))
                continue
        if names and names[0] in OP_TABLES and isinstance(node, (ast.Assign, ast.AnnAssign)) \
                and isinstance(node.value, ast.Dict):
            a, b = stmt_span(node)
            head = head_of(node.lineno)
            head_lines = [line(n).strip().decode('utf-8') for n in range(head, node.lineno)]
            add(OP_HOME, index, f'{names[0]}={{}}')
            split_dict(names[0], node.value, index, head_lines)
            spans.append((a, b, None))
            continue
        if names and names[0] in HELPERS:
            a, b = stmt_span(node)
            helper_texts.append(text_of(a, b))
            spans.append((a, b, None))
            continue
        if names and names[0] in MODULE_OF:
            a, b = stmt_span(node)
            piece = add(MODULE_OF[names[0]], index, text_of(a, b))
            spans.append((a, b, piece))
            continue
    return pieces, helper_texts, spans, imports, tree, src, starts


MODULE_OF = {name: module for module, names in MODULES.items() for name in names}


def piece_model(pieces):
    """Parse every piece; attach the names it defines and the names it loads."""
    for piece in pieces:
        parsed = ast.parse(piece['text'])
        piece['defines'] = [n for node in parsed.body for n in top_names(node)]
        piece['loads'] = loads_of(parsed)
    return pieces


def prune(pieces, imports):
    """A text object that needs a name left in bridge.py (a limit, a validator) stays in bridge.py: it is returned
    as `dropped` and translated in place. Repeats until nothing unresolved is left. Op entries cannot stay."""
    dropped = []
    while True:
        _, _, unresolved, _, _ = check(pieces, [], imports, None)
        names = set(unresolved)
        bad = [p for p in pieces if p['loads'] & names]
        if not bad:
            return pieces, dropped
        for piece in bad:
            if piece['op']:
                raise SystemExit(f'an op entry needs a name left in bridge.py: {piece["text"][:80]!r}')
        dropped += [p for p in bad if p['defines']]
        pieces = [p for p in pieces if not (p['loads'] & names)]


def check(pieces, helper_texts, imports, tree):
    moved = {}
    for piece in pieces:
        for name in piece['defines']:
            moved[name] = piece['module']
    missing = [n for n in MODULE_OF if n not in moved]
    unresolved = {}
    needs = {m: {'helpers': set(), 'stdlib': set(), 'cross': {}} for m in MODULES}
    for piece in pieces:
        module = piece['module']
        for name in sorted(piece['loads']):
            if name in HELPERS:
                needs[module]['helpers'].add(name)
            elif name in moved:
                if moved[name] != module:
                    needs[module]['cross'].setdefault(moved[name], set()).add(name)
            elif name in imports:
                needs[module]['stdlib'].add(imports[name])
            elif hasattr(builtins, name):
                pass
            else:
                unresolved.setdefault(name, set()).add(module)
    edges = {m: set(needs[m]['cross']) for m in MODULES}
    cycle = find_cycle(edges)
    return moved, missing, unresolved, needs, cycle


def find_cycle(edges):
    state = {}

    def visit(node, stack):
        state[node] = 1
        for other in edges.get(node, ()):
            if state.get(other) == 1:
                return stack + [other]
            if other not in state:
                found = visit(other, stack + [other])
                if found:
                    return found
        state[node] = 2
        return None

    for node in edges:
        if node not in state:
            found = visit(node, [node])
            if found:
                return found
    return None


def pt_count(pieces, module):
    values = set()
    for piece in pieces:
        if piece['module'] != module:
            continue
        for node in ast.walk(ast.parse(piece['text'])):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and PT.search(node.value):
                values.add(node.value)
    return values


def report(pieces, moved, missing, unresolved, cycle):
    total = set()
    for module in MODULES:
        values = pt_count(pieces, module)
        total |= values
        objects = sorted({p['defines'][0] if p['defines'] else '(op entries)' for p in pieces if p['module'] == module})
        print(f'{module}: {len(values)} Portuguese strings, {len([p for p in pieces if p["module"] == module])} pieces')
        print('   ' + ', '.join(objects))
    print(f'total distinct Portuguese strings moved: {len(total)}')
    print('missing names:', missing)
    print('unresolved names:', {k: sorted(v) for k, v in unresolved.items()})
    print('import cycle:', cycle)


def render_module(module, pieces, needs):
    chosen = sorted((p for p in pieces if p['module'] == module), key=lambda p: p['order'])
    header = [f'"""{DOC[module]}"""']
    stdlib = sorted(needs[module]['stdlib'])
    header += stdlib
    if needs[module]['helpers']:
        header.append('from translations import ' + ','.join(h for h in HELPERS if h in needs[module]['helpers']))
    for other in sorted(needs[module]['cross']):
        header.append(f'from {other} import ' + ','.join(sorted(needs[module]['cross'][other])))
    body = []
    for piece in chosen:
        if piece['text'].startswith(('def ', 'class ')) or piece['text'].startswith('#') and '\ndef ' in piece['text']:
            body.append('')
        body.append(piece['text'])
    return '\n'.join(header) + '\n\n' + '\n'.join(body) + '\n'


def write_split(pieces, helper_texts, spans, imports, src, starts, needs, moved):
    def removal(content_spans):
        mask = bytearray(len(src))
        extended = []
        for a, b in content_spans:
            j = b
            while j < len(src) and src[j:j + 1] in (b' ', b'\t'):
                j += 1
            if src[j:j + 1] == b';':
                b = j + 1
                while b < len(src) and src[b:b + 1] in (b' ', b'\t'):
                    b += 1
            else:
                i = a
                while i > 0 and src[i - 1:i] in (b' ', b'\t'):
                    i -= 1
                if src[i - 1:i] == b';':
                    a = i - 1
            extended.append((a, b))
        for a, b in extended:
            for k in range(a, b):
                mask[k] = 1
        return mask

    kept = {id(piece) for piece in pieces}
    mask = removal([(a, b) for a, b, owner in spans if owner is None or id(owner) in kept])
    out_lines = []
    for number in range(len(starts)):
        s = starts[number]
        e = starts[number + 1] if number + 1 < len(starts) else len(src)
        original = src[s:e]
        kept = bytes(original[k - s] for k in range(s, e) if not mask[k])
        if original.strip() and kept.strip() in (b'', b';'):
            continue
        if any(mask[s:e]) and kept.rstrip().endswith(b';'):
            kept = kept.rstrip()[:-1] + kept[len(kept.rstrip()):]
        out_lines.append(kept)
    text = b''.join(out_lines).decode('utf-8')
    lines = text.split('\n')
    index = lines.index('import translations')
    insert = ['from translations import CONTEXT,_fill,_tr,_Messages']
    for module in MODULES:
        names = sorted({n for n, m in moved.items() if m == module}, key=lambda n: moved_order(pieces, n))
        if names:
            insert.append(f'from {module} import ' + ','.join(names))
    lines[index + 1:index + 1] = insert
    BRIDGE.write_text('\n'.join(lines), encoding='utf-8')

    for module in MODULES:
        if not any(p['module'] == module for p in pieces):
            continue
        (APP / f'{module}.py').write_text(render_module(module, pieces, needs), encoding='utf-8')

    translations = TRANSLATIONS.read_text(encoding='utf-8')
    assert translations.count('from PySide6.QtCore import QTranslator') == 1
    translations = translations.replace('from PySide6.QtCore import QTranslator', 'from PySide6.QtCore import QCoreApplication,QTranslator')
    translations = translations.rstrip('\n') + '\n\n\n# WP-20 G5c: the translate helpers, moved from app/bridge.py so the msgs_* modules can use them without a cycle.\n'
    translations += '\n\n'.join(helper_texts) + '\n'
    TRANSLATIONS.write_text(translations, encoding='utf-8')


def moved_order(pieces, name):
    for piece in pieces:
        if name in piece['defines']:
            return piece['order']
    return (0, 0)


def load_snapshot(name, path):
    """The pre-split bridge, executed from its snapshot file under its own name."""
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_const(p, q):
    if hasattr(p, 'co_code') and hasattr(q, 'co_code'):
        return same_code(p, q)
    return type(p) is type(q) and p == q


def same_code(x, y):
    return (x.co_code == y.co_code and x.co_names == y.co_names and x.co_varnames == y.co_varnames
            and len(x.co_consts) == len(y.co_consts) and all(same_const(p, q) for p, q in zip(x.co_consts, y.co_consts)))


def same_value(a, b):
    """Equal values; a lambda or function is equal to another when its bytecode and constants are (identity would differ
    between two executions of the same source)."""
    if type(a) is object and type(b) is object:
        return True  # a sentinel (`X=object()`) is new in each execution; the bridge only compares it by identity
    if hasattr(a, '__code__') and hasattr(b, '__code__'):
        return same_code(a.__code__, b.__code__) and a.__defaults__ == b.__defaults__
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and type(a) is type(b):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    return a == b


def same_def(name, snapshot_tree, module_tree):
    a = [n for n in snapshot_tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
    b = [n for n in module_tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
    return bool(a) and bool(b) and ast.dump(a[0]) == ast.dump(b[0])


def verify(snapshot_path):
    snap_pieces, snap_helpers, _, snap_imports, snap_tree, _, _ = collect(snapshot_path)
    piece_model(snap_pieces)
    snap_pieces, _ = prune(snap_pieces, snap_imports)
    moved, *_ = check(snap_pieces, snap_helpers, {}, snap_tree)
    snapshot = load_snapshot('bridge_snapshot', snapshot_path)
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    new_bridge = importlib.import_module('bridge')
    new_tree = ast.parse(BRIDGE.read_bytes())
    problems = []
    checked = 0
    for name, module_name in sorted(moved.items()):
        checked += 1
        module = importlib.import_module(module_name)
        value = getattr(snapshot, name)
        if not hasattr(module, name):
            problems.append(f'{name}: missing in {module_name}')
            continue
        if isinstance(value, type) or callable(value) and getattr(value, '__module__', '') == 'bridge_snapshot':
            module_tree = ast.parse((APP / f'{module_name}.py').read_bytes())
            if not same_def(name, snap_tree, module_tree):
                problems.append(f'{name}: definition differs')
            continue
        if not same_value(getattr(new_bridge, name), value):
            problems.append(f'{name}: value differs in bridge')
        if not same_value(getattr(module, name), value):
            problems.append(f'{name}: value differs in {module_name}')
    for node in snap_tree.body:
        for name in top_names(node):
            if name in moved or name in HELPERS:
                continue
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                checked += 1
                if not same_def(name, snap_tree, new_tree):
                    problems.append(f'{name}: definition differs in bridge')
            else:
                checked += 1
                if not hasattr(new_bridge, name) or not same_value(getattr(new_bridge, name), getattr(snapshot, name)):
                    problems.append(f'{name}: value differs in bridge')
    for name in HELPERS:
        checked += 1
        if not hasattr(new_bridge, name):
            problems.append(f'{name}: helper missing in bridge')
    print(f'checked {checked} objects; problems: {len(problems)}')
    for item in problems:
        print('  ', item)
    return 0 if not problems else 1


def main(argv):
    if len(argv) >= 1 and argv[0] == 'verify':
        return verify(Path(argv[1]))
    if len(argv) != 1 or argv[0] not in ('plan', 'split'):
        print(__doc__)
        return 2
    pieces, helper_texts, spans, imports, tree, src, starts = collect(BRIDGE)
    piece_model(pieces)
    pieces, dropped = prune(pieces, imports)
    print('stay in bridge.py (need a bridge-local name):', sorted(d['defines'][0] for d in dropped))
    moved, missing, unresolved, needs, cycle = check(pieces, helper_texts, imports, tree)
    dropped_names = {name for piece in dropped for name in piece['defines']}
    missing = [name for name in missing if name not in dropped_names]
    report(pieces, moved, missing, unresolved, cycle)
    if argv[0] == 'plan':
        return 0
    if missing or unresolved or cycle:
        print('refusing to split: resolve the items above first')
        return 1
    write_split(pieces, helper_texts, spans, imports, src, starts, needs, moved)
    print('split written')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
