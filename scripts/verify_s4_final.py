#!/usr/bin/env python3
"""S4 final gate ('Gate final S4', docs/S4.md) against the REAL release Core. Evidence: target/evidence/s4-final.json.

Parts (every group runs under verify_s4_core.group(); one failure never aborts the next group):
  CONTRACT  scripts/test_snapshot_contract.py (real Core, every snapshot through app/bridge.validate_snapshot),
            including the skill lifecycle test (draft, dry run, approve, enable, run with step approval, export,
            remove, import preview with findings, confirm).
  QT        scripts/test_ui_offscreen.py --phase skills under the Qt offscreen sandbox (ui_fixture.offscreen_command),
            twice: WITH llm_engine 1.2.0 running (the 'Gerar com LLM' button goes through the Qt slot
            skillDraftWithLlm; scripted LLM via plugin settings agent_script, loopback fake provider selection only)
            and WITHOUT the plugin (the deterministic installed skill still runs from the UI).
  S1-S3     regression sanity: Base command via the replay Core (verify_c4.py contract), C3 agent run with a
            scripted LLM and the synthetic counter tool, C4 synthetic screen capture with the skills module present.
  RESIDUE   removal of the skill leaves no item, run or import in the snapshot and no directory; the synthetic
            world is the only Base state written; the planted secret is absent from every file except the 0600
            key store and from every snapshot; nothing new appears in the repository tree.

Run with the UI venv (the bridge imports PySide6 for the contract validator):
  target/ui-venv/bin/python scripts/verify_s4_final.py [part ...]   (no argument: all parts)
"""
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
sys.path.insert(0, str(BASE / 'app'))
import verify_s4_core as g  # noqa: E402  (check/group/req helpers and the shared result table)
import verify_s4_share as sh  # noqa: E402  (boot_proc, install, promote, set_script, fake_provider, draft_manifest)
import verify_c4 as c4  # noqa: E402  (merged_catalog: hub-c1 plus the six C4 plugins)
from ui_fixture import offscreen_command  # noqa: E402
from bridge import PERCEPTION_OUTPUTS  # noqa: E402

UI_PY = BASE / 'target/ui-venv/bin/python'
CONTRACT = BASE / 'scripts/test_snapshot_contract.py'
BIN = BASE / 'target/release/gideon-base'
CAT_C1 = BASE / 'tests/fixtures/hub-c1.json'
LLM = 'llm_engine'
LLM_SRC = BASE / 'tests/fixtures/llm_engine.py'
SCREEN_SRC = BASE / 'tests/fixtures/c4/screen_observe.py'
EVIDENCE = BASE / 'target/evidence'
CLEAN_ENV = {'PATH': '/usr/bin:/bin'}
KEY = 'sk-fake-s4final-' + secrets.token_hex(12)  # planted in the Core key store; loopback fake provider only
RUN_SKILL = 'skill_fixture_run'      # enabled deterministic skill: read -> write (state-changing, needs approval)
NOTE_SKILL = 'skill_fixture_note'    # exported, removed, and placed as skill-imports/fixture-note.gskill
DRAFT_SKILL = 'skill_draft_ui'       # created by the LLM draft through the Qt button (never enabled)
DRAFT_TEXT = 'Lista a hora atual'    # typed by the Qt phase; the scripted model answers with DRAFT_SKILL
WRITE_TEXT = 'alfa-ui'               # text the enabled skill writes into the synthetic world
PARTS = ['contract', 'qt', 's1s3', 'residue']
PARTS_RUN = sys.argv[1:] or PARTS
ALL_PROCS = []
TRACKED = {}  # label -> Core root (for the final residue scan)


def repo_status():
    out = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=BASE, capture_output=True,
                         text=True, check=True).stdout
    return sorted(line for line in out.splitlines() if not line[3:].startswith('target/'))


def rw_manifest(sid, text):
    return {'schema_version': 1, 'id': sid, 'name': 'Skill de teste final S4', 'version': '1.0.0',
            'publisher': {'id': 'gideon-test', 'name': 'Gideon test'}, 'description': 'Skill sintetica do gate final S4',
            'license': 'TEST-ONLY', 'min_runtime': '0.1.0', 'triggers': [], 'inputs': {},
            'outputs': {'epoch': {'type': 'int'}, 'text': {'type': 'string'}},
            'dependency_capabilities': ['tool:synth_screen_read', 'tool:synth_set_text'], 'permissions_required': [],
            'prerequisites': [], 'attestations': [{'kind': 'test', 'text': 'synthetic test only, never shipped'}],
            'steps': [{'id': 'read', 'call': 'tool:synth_screen_read', 'args': {},
                       'save': {'epoch': 'epoch', 'text': 'text'}},
                      {'id': 'write', 'call': 'tool:synth_set_text',
                       'args': {'epoch': '${steps.read.epoch}', 'text': text}}]}


def skill_run_block(root):
    return g.run_block(root)


def run_skill_to_end(root, sid, label):
    """Authorize-every-step drive of a user run (the user's own decision path)."""
    code = g.sk_run(root, sid, {})
    g.check(f'{label}: skill run accepted ({code})', code == 'ok', code)
    g.drive(root, lambda r: r is None, f'{label} run ends')
    last = g.last_run(root)
    g.check(f'{label}: run done ({last and last["state"]})', last is not None and last['state'] == 'done', last)


def prepare_skills(root, home):
    """Fixture skills for the Qt phase: an enabled deterministic skill and a package for the import preview."""
    codes = sh.promote(root, rw_manifest(RUN_SKILL, WRITE_TEXT))
    g.check(f'fixture: {RUN_SKILL} saved, dry-run tested, approved, enabled {codes}', codes == ['ok'] * 4, codes)
    codes = sh.promote(root, sh.draft_manifest(NOTE_SKILL, '1.0.0'))
    g.check(f'fixture: {NOTE_SKILL} exported later (user path) {codes}', codes == ['ok'] * 4, codes)
    exported = g.req(root, 'skill_export', id=NOTE_SKILL, skill_version='1.0.0')
    g.check(f'fixture: export of {NOTE_SKILL} ok ({exported["code"]})', exported['code'] == 'ok', exported)
    package = (home / 'skill-exports' / f'{NOTE_SKILL}-1.0.0.gskill').read_bytes()
    code = g.req(root, 'skill_remove', id=NOTE_SKILL, revision=g.sk_revision(root))['code']
    g.check(f'fixture: {NOTE_SKILL} removed before the import ({code})', code == 'ok', code)
    sh.place_import(home, 'fixture-note', package)
    g.check('fixture: skill-imports/fixture-note.gskill is in place (0600, same bytes as the export)',
            (home / 'skill-imports' / 'fixture-note.gskill').read_bytes() == package)


def run_qt_phase(root, label, llm_flag, markers):
    """Runs the Qt skills phase on `root` in the offscreen sandbox and returns its self-report row."""
    artifacts = Path(root).parent / f'artifacts-{label}'
    artifacts.mkdir(exist_ok=True)
    command = offscreen_command(root, artifacts, 'skills') + ['--llm', llm_flag]
    ui = subprocess.Popen(command, env=CLEAN_ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for name in markers:
            until = time.monotonic() + 150
            while not (artifacts / name).exists():
                if ui.poll() is not None:
                    err = ui.stderr.read()
                    (Path(root).parent / f'ui-{label}.stderr').write_bytes(err)
                    raise RuntimeError(f'{label}: Qt skills phase exited before {name}: '
                                       + err.decode('utf-8', 'replace')[-800:])
                if time.monotonic() > until:
                    raise TimeoutError(f'{label}: Qt marker {name}')
                time.sleep(0.02)
        out, err = ui.communicate(timeout=120)
    finally:
        if ui.poll() is None:
            ui.kill()
            ui.wait(timeout=3)
    (Path(root).parent / f'ui-{label}.stderr').write_bytes(err)
    g.check(f'{label}: Qt skills phase exit 0', ui.returncode == 0, err.decode('utf-8', 'replace')[-800:])
    row = json.loads(out.decode('utf-8').strip().splitlines()[-1])
    names = row.get('checks') or []
    g.check(f'{label}: Qt self-report accepted (zero failures, passed equals the listed checks)',
            row.get('phase') == 'skills' and row.get('failed') == 0 and row.get('ignored') == 0
            and row.get('passed') == len(names) and bool(names), row)
    g.R['details'].setdefault('qt', {})[label] = {'passed': row.get('passed'), 'checks': names,
                                                 'markers': sorted(p.name for p in artifacts.iterdir())}
    return row


def llm_setup(root, url, steps):
    """Installs llm_engine, configures the loopback fake provider selection, and writes the scripted steps."""
    sh.install(root, LLM, LLM_SRC)
    g.check('llm: provider key stored by the Core (secret_set)',
            g.req(root, 'secret_set', provider='custom', key=KEY)['code'] == 'ok')
    rev = g.req(root)['llm']['revision']
    code = g.req(root, 'llm_configure', revision=rev, provider='custom', model='fake/model-1', custom_url=url,
                 local_port=None, fallback=None, cloud_consent=True)['code']
    g.check(f'llm: selection configured to the loopback fake ({code})', code == 'ok', code)
    sh.set_script(root, steps)


# ---- CONTRACT -----------------------------------------------------------------------------
def part_contract():
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    done = subprocess.run([str(UI_PY), str(CONTRACT), '-v'], cwd=BASE, env=env, capture_output=True, text=True,
                          timeout=480)
    text = done.stdout + done.stderr
    results = re.findall(r'^(test_\w+) \(.*?\) \.\.\. (.+)$', text, re.M)
    g.check(f'contract: scripts/test_snapshot_contract.py exits 0 (rc {done.returncode})', done.returncode == 0,
            text[-1500:])
    g.check(f'contract: skill lifecycle test present and ran ({len(results)} tests listed)',
            any(name == 'test_skill_lifecycle_snapshots_validate_against_real_core' for name, _ in results),
            [n for n, _ in results])
    for name, status in results:
        g.check(f'contract {name}: {status.strip()}', status.strip() == 'ok', status)
    g.R['details']['contract'] = {'tests': dict(results), 'rc': done.returncode}


# ---- QT ---------------------------------------------------------------------------------
MARKERS_ALL = ['skills-ready', 'skills-validated', 'skills-draft', 'skills-awaiting', 'skills-run', 'skills-import']


def part_qt(td, state):
    # Run A: llm_engine running. The UI drafts through the Gerar com LLM slot; the draft is never enabled.
    proc, root, home = sh.boot_proc(td, 'qt-llm', CAT_C1, ['--agent-synthetic'])
    ALL_PROCS.append(proc)
    state.update(llm_root=root, llm_home=home, llm_proc=proc)
    try:
        prepare_skills(root, home)
        fake, url = sh.fake_provider()
        ALL_PROCS.append(fake)
        draft = sh.draft_manifest(DRAFT_SKILL, '1.0.0')
        llm_setup(root, url, [sh.script_step(json.dumps(draft))])
        state['fake'] = fake
        row = run_qt_phase(root, 'llm', 'yes', MARKERS_ALL)
        state['llm_row'] = row
        item = g.item_of(root, DRAFT_SKILL)
        g.check('qt-llm: the LLM draft row is draft, llm_draft, not active (no enable from the model)',
                item is not None and item['state'] == 'draft' and item['source'] == 'llm_draft'
                and item['active'] is False, item)
        g.check('qt-llm: the fixture run skill stays enabled and active after the UI run',
                g.item_of(root, RUN_SKILL)['state'] == 'enabled' and g.item_of(root, RUN_SKILL)['active'] is True)
        g.check('qt-llm: the UI run wrote the synthetic world once (app text = write text)',
                g.app_text(home) == WRITE_TEXT, g.app_text(home))
        g.check('qt-llm: the imported note is a draft and nothing imported is enabled',
                (g.item_of(root, NOTE_SKILL) or {}).get('state') == 'draft'
                and not any(i['source'] == 'imported' and i['state'] == 'enabled' for i in g.items(root)))
    finally:
        stop_core(proc, 'qt-llm')
    # Run B: llm_engine absent. The deterministic installed skill still runs from the UI.
    proc, root, home = sh.boot_proc(td, 'qt-plain', CAT_C1, ['--agent-synthetic'])
    ALL_PROCS.append(proc)
    state.update(plain_root=root, plain_home=home, plain_proc=proc)
    try:
        prepare_skills(root, home)
        g.check('qt-plain: llm_engine is not running (no plugin, no LLM path)',
                g.item(g.req(root), LLM) is None)
        state['plain_row'] = run_qt_phase(root, 'plain', 'no', MARKERS_ALL)
        run = g.last_run(root)
        g.check('qt-plain: the UI run finished done in the synthetic world', run is not None and run['state'] == 'done'
                and g.app_text(home) == WRITE_TEXT, (run, g.app_text(home)))
        g.check('qt-plain: no draft exists without the LLM plugin', g.item_of(root, DRAFT_SKILL) is None)
    finally:
        stop_core(proc, 'qt-plain')


def stop_core(proc, label):
    if proc.poll() is None:
        kids = g.descendants(proc.pid)
        proc.terminate()
        try:
            rc = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait(timeout=5)
        g.check(f'{label}: Core clean shutdown rc 0', rc == 0, f'rc={rc}')
        until = time.monotonic() + 5
        left = [p for p in kids if g.alive(p)]
        while left and time.monotonic() < until:
            time.sleep(0.1)
            left = [p for p in kids if g.alive(p)]
        g.check(f'{label}: no child process left after shutdown', not left, left)


# ---- S1-S3 ------------------------------------------------------------------------------
def part_s1s3(td, state):
    # S1: Base command through the replay Core (wake replay and command receipt), as verify_c4.py does.
    # The replay boot keeps the repository as home (the wake replay and command sandbox read target/ assets there,
    # as verify_c4.py and verify_s4_core.py do); its synthetic world is removed right after the check.
    root = g.boot(td, 's1', extra=('--agent-synthetic',), replay=True, home=BASE)
    try:
        g.native_check(root, 'S1 native replay: Base command succeeds and the wake replay finishes')
    finally:
        g.stop('s1')
        shutil.rmtree(BASE / 'synthetic', ignore_errors=True)
    # C3: scripted agent run through the real Core (the llm_engine scripted steps, synthetic counter tool).
    proc, root, home = sh.boot_proc(td, 'c3', CAT_C1, ['--agent-synthetic'])
    ALL_PROCS.append(proc)
    try:
        fake, url = sh.fake_provider()
        ALL_PROCS.append(fake)
        llm_setup(root, url, [sh.script_step('', [('synth_counter_inc', {'epoch': 1})]),
                              sh.script_step('Contador atualizado.')])
        code = g.req(root, 'agent_start', goal='Incremente o contador')['code']
        g.check(f'C3: agent_start accepted ({code})', code == 'ok', code)
        waiting = g.wait_snap(root, lambda s: s.get('agent') is not None
                              and s['agent']['state'] == 'awaiting_approval', 25, 'C3 awaiting approval')
        proposal = next(p for p in waiting['tool_proposals'] if p['state'] == 'pending')
        g.check('C3: state-changing tool waits for the user decision',
                g.req(root, 'tool_decide', proposal_id=proposal['proposal_id'], decision='authorize')['code'] == 'ok')
        done = g.wait_snap(root, lambda s: s.get('agent') is not None and s['agent']['state'] == 'done', 25,
                           'C3 done')
        g.check('C3: agent answer shown and the counter incremented once in the synthetic world',
                done['agent']['answer'] == 'Contador atualizado.' and g.world(home)['app']['counter'] == 1,
                (done['agent'].get('answer'), g.world(home)['app']))
    finally:
        stop_core(proc, 'c3')
    # C4: synthetic screen capture through the real Core with the skills module present (same catalog family).
    cat_path, _ = c4.merged_catalog(td, 'catalog-s4-final-c4')
    proc, root, home = sh.boot_proc(td, 'c4', Path(cat_path), ['--agent-synthetic'])
    ALL_PROCS.append(proc)
    try:
        sh.install(root, 'screen_observe', SCREEN_SRC)
        result = sh.capability(root, 'screen_observe.capture', {})
        g.check(f'C4: synthetic capture ok through the Core ({result.get("error")})', result.get('ok') is True, result)
        g.check('C4: capture output passes the bridge rule (sintetico, no real backend)',
                PERCEPTION_OUTPUTS['screen_observe.capture'](result.get('output')), result.get('output'))
        g.check('C4: skills module present in the same Core (skills block in the snapshot)',
                g.req(root).get('skills') is not None)
    finally:
        stop_core(proc, 'c4')


# ---- RESIDUE ----------------------------------------------------------------------------
ALLOWED_HOME_PREFIXES = ('synthetic/', 'skill-exports/', 'skill-imports/')


def part_residue(td, state):
    proc, root, home = sh.boot_proc(td, 'residue', CAT_C1, ['--agent-synthetic'])
    ALL_PROCS.append(proc)
    try:
        fake, url = sh.fake_provider()
        ALL_PROCS.append(fake)
        prepare_skills(root, home)
        llm_setup(root, url, [sh.script_step('ok')])
        run_skill_to_end(root, RUN_SKILL, 'residue')
        world_before_remove = g.world_bytes(home)
        code = g.req(root, 'skill_remove', id=RUN_SKILL, revision=g.sk_revision(root))['code']
        g.check(f'residue: remove the enabled skill ({code})', code == 'ok', code)
        snap = g.req(root)
        skills = snap.get('skills') or {}
        live = {k: v for k, v in skills.items() if k != 'history'}
        g.check('residue: no item, run or import of the removed skill in the snapshot',
                RUN_SKILL not in json.dumps(live, ensure_ascii=False) and skills.get('run') is None
                and skills.get('import') in (None, {}), live)
        g.check('residue: the skill directory is gone from the Core root',
                not (root / 'skills' / RUN_SKILL).exists())
        g.check('residue: removal does not touch the synthetic world',
                g.world_bytes(home) == world_before_remove)
        g.R['details']['residue_history_entries_mentioning_skill'] = sum(
            1 for e in skills.get('history', []) if e.get('skill') == RUN_SKILL)
        # Secret: the planted key may live only in secrets.json (mode 0600), never in the snapshot or any file.
        g.check('residue: the provider key is absent from every snapshot',
                KEY not in json.dumps(snap, ensure_ascii=False))
        stop_core(proc, 'residue')
    except Exception:
        stop_core(proc, 'residue')
        raise
    leaks, modes = [], []
    for dirpath, _, names in os.walk(td):
        for name in names:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if KEY.encode() not in data:
                continue
            if name == 'secrets.json':
                modes.append(stat.S_IMODE(path.stat().st_mode))
            else:
                leaks.append(str(path.relative_to(td)))
    g.check('residue: the provider key appears only in secrets.json', not leaks, leaks)
    g.check('residue: secrets.json holding the key is mode 0600', modes and all(m == 0o600 for m in modes), modes)
    home_dir = Path(td) / 'residue' / 'home'
    files = sorted(str(p.relative_to(home_dir)) for p in home_dir.rglob('*') if p.is_file())
    outside = [f for f in files if not f.startswith(ALLOWED_HOME_PREFIXES)]
    g.check('residue: the only files written in the Core home are the synthetic world and skill exports/imports',
            not outside, outside)
    g.R['details']['residue_home_files'] = files


def main():
    started = time.monotonic()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    before = repo_status()
    td = tempfile.mkdtemp(prefix='gideon-s4final-')
    state = {}
    try:
        if 'contract' in PARTS_RUN:
            g.group('CONTRACT', part_contract)
        if 'qt' in PARTS_RUN:
            g.group('QT skills phase with and without llm_engine', part_qt, td, state)
        if 's1s3' in PARTS_RUN:
            g.group('S1-S3 regression sanity', part_s1s3, td, state)
        if 'residue' in PARTS_RUN:
            g.group('RESIDUE, secrets and side effects', part_residue, td, state)
    finally:
        for proc in ALL_PROCS:
            if proc.poll() is None:
                proc.kill()
    after = repo_status()
    new_files = sorted(set(after) - set(before))
    g.check('no repository change outside target/ during the gate (git status)', not new_files, new_files)
    if not g.R['failed']:
        subprocess.run(['rm', '-rf', td], check=False)
    else:
        g.R['details']['kept_root'] = td
    out = {'gate': 'S4 final', 'passed': len(g.R['passed']), 'failed': len(g.R['failed']),
           'skipped': g.R['skipped'], 'checks': g.R['passed'], 'failures': g.R['failed'], 'details': g.R['details'],
           'divergences': g.R['divergences'], 'parts': PARTS_RUN, 'binary_sha256': g.sha(BIN),
           'runtime_s': round(time.monotonic() - started, 1),
           'scope': 'release Core; llm_engine 1.2.0 scripted (agent_script) with a loopback fake provider selection; '
                    'synthetic world and synthetic tools only; Qt offscreen in bwrap; no real provider or hardware'}
    text = json.dumps(out, indent=2, ensure_ascii=False) + '\n'
    text = text.replace(KEY, '<redacted>')
    (EVIDENCE / 's4-final.json').write_text(text, encoding='utf-8')
    print(text)
    return 0 if not g.R['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
