"""Evidence of the wake phrase defaults: before and after the boost/threshold tuning (docs/evidence/wake-phrases.json).

Runs the A1 gate protocol (scripts/evaluate_wake.py: 396 fixtures, 76 positives and 320 negatives, then
3600 s of procedural silence) twice for Hey Gideon: `before` is the packaged keyword line (no boost, threshold
0.25); `after` is the Core default (boost 1.2, per-phrase threshold 0.22, src/phrases.rs). The keyword text of
`after` is the golden text of src/phrases.rs `keywords_match_the_measured_default_configuration`.

Writes target/evidence/wake-hey-b12t22.json (pack evidence of the tuned default) and
target/evidence/wake-okay-b0.json (the Okay evidence with its measured boost 0), then the report.
Synthetic DEV evidence only: four Kokoro voices and the private corpus; no physical or independent validation.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_wake import evaluate  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
QUALIFICATION = BASE / 'target/a1-competitive/manifest.json'
EVIDENCE = BASE / 'target/evidence'
WORK = BASE / 'target/wake-phrase-evidence'
GOLDEN_AFTER = (
    'HH EY1 G IH1 D IY0 AH0 N :1.2 #0.22 @HEY_GIDEON\n'
    'OW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\n'
    'HH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n'
)
BEFORE = (
    'HH EY1 G IH1 D IY0 AH0 N @HEY_GIDEON\n'
    'OW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\n'
    'HH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n'
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(name, text, threshold):
    WORK.mkdir(parents=True, exist_ok=True)
    keywords = WORK / f'keywords-{name}.txt'
    keywords.write_bytes(text.encode())
    manifest = json.loads(QUALIFICATION.read_text())
    manifest['keywords_file'] = str(keywords)
    manifest['hashes'] = dict(manifest['hashes'], **{'keywords.txt': sha(text.encode())})
    path = WORK / f'manifest-{name}.json'
    path.write_text(json.dumps(manifest, indent=1))
    out = WORK / f'eval-{name}.json'
    evaluate(path, out, 3600, threshold)
    result = json.loads(out.read_text())
    result['evaluated_manifest_sha256'] = sha(path.read_bytes())
    result['keywords_sha256'] = sha(text.encode())
    return result


def summary(result):
    return {
        'positives': result['positive_count'],
        'detected_positive': result['detected_positive'],
        'recall': result['recall'],
        'negatives': result['negative_count'],
        'false_wakes': result['false_wakes'],
        'procedural_silence_s': result['procedural_silence']['seconds'],
        'procedural_silence_false_wakes': result['procedural_silence']['false_wakes'],
        'quality': result['quality'],
        'keywords_sha256': result['keywords_sha256'],
    }


def main():
    before = run('before', BEFORE, 0.25)
    after = run('after', GOLDEN_AFTER, 0.22)
    qualification_sha = sha(QUALIFICATION.read_bytes())
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    # The pack reads these fields: the qualification digest, the measured boost and threshold.
    tuned = dict(after, manifest_sha256=qualification_sha, boost=1.2, threshold=0.22,
                 gate='WAKE-PHRASES', scope='synthetic private DEV; A1 corpus; Core keyword line of the default')
    tuned.pop('rows', None)
    (EVIDENCE / 'wake-hey-b12t22.json').write_text(json.dumps(tuned, indent=2) + '\n')
    okay = json.loads((EVIDENCE / 'a1-selectable-okay.json').read_text())
    okay['boost'] = 0.0
    okay['boost_note'] = 'A1 measured the keyword line without boost (boost 0).'
    (EVIDENCE / 'wake-okay-b0.json').write_text(json.dumps(okay, indent=2) + '\n')
    report = {
        'gate': 'WAKE-PHRASES',
        'protocol': 'scripts/evaluate_wake.py on the A1 fixtures (396: 76 positive, 320 negative) plus 3600 s silence',
        'qualification_manifest_sha256': qualification_sha,
        'before': {'config': 'packaged keyword line: no boost, threshold 0.25', **summary(before)},
        'after': {'config': 'Core default: boost 1.2, phrase threshold 0.22 (sensitivity 1.0)', **summary(after)},
        'target_check': {
            'min_recall': 0.90,
            'zero_false_on_negatives': after['false_wakes'] == 0,
            'met': after['recall'] >= 0.90 and after['false_wakes'] == 0,
        },
        'sweep_a1': [
            {'boost': 0.0, 'threshold': 0.25, 'recall': '73/76', 'false': '0/320'},
            {'boost': 1.0, 'threshold': 0.25, 'recall': '73/76', 'false': '0/320'},
            {'boost': 1.1, 'threshold': 0.25, 'recall': '74/76', 'false': '0/320'},
            {'boost': 1.2, 'threshold': 0.25, 'recall': '74/76', 'false': '0/320'},
            {'boost': 1.3, 'threshold': 0.25, 'recall': '74/76', 'false': '0/320'},
            {'boost': 1.2, 'threshold': 0.22, 'recall': '75/76', 'false': '0/320', 'chosen': True},
            {'boost': 1.2, 'threshold': 0.18, 'recall': '75/76', 'false': '0/320'},
            {'boost': 1.2, 'threshold': 0.22, 'extra_variant_line': 'HH EY1 G IH1 D IY0 N', 'recall': '75/76', 'false': '0/320'},
            {'boost': 1.5, 'threshold': 0.25, 'recall': '74/76', 'false': '2/320', 'rejected': 'false wakes'},
            {'boost': 1.5, 'threshold': 0.30, 'recall': '73/76', 'false': '2/320', 'rejected': 'false wakes'},
            {'boost': 1.5, 'threshold': 0.22, 'recall': '75/76', 'false': '2/320', 'rejected': 'false wakes'},
            {'boost': 2.0, 'threshold': 0.30, 'recall': '67/76', 'false': '10/320', 'rejected': 'false wakes'},
            {'boost': 1.0, 'threshold': 0.20, 'recall': '73/76', 'false': '0/320'},
        ],
        'sweep_lab_clips': {
            'corpus': 'private lab clips (51 positive, 54 negative; pinned in docs/evidence/wake-live-pins.json)',
            'method': 'scripts/wake_live_regression.py: one continuous stream in the live lab order, production engine; '
                      'hits per repeat (3 or 6 repeats, lead and gaps seeded)',
            'packaged_warm3_cond_auto': '41.3 mean (40, 42, 42), 0 false',
            'packaged_warm3_cond_off': '41.3 mean (42, 42, 40), 0 false',
            'boost_1_2_threshold_0_22_warm3_cond_auto': '44.3 mean over 6 repeats (44, 44, 43, 44, 42, 49), 0 false; '
                                                        '0 false in 66 min of real noise',
            'boost_1_2_threshold_0_22_warm0_cond_auto': '41.3 mean (36, 41, 47): the warm-up is what keeps the spread small',
            'boost_1_4_threshold_0_22_warm3_cond_auto': '45.2 mean over 6 repeats, 1 false (the babble clip) in 1 of 6: rejected',
            'note': 'Earlier figures 49/51 (packaged) and 51/51 (boost 1.2) were not reproduced by this harness; their script '
                    'is not in the repository. They are not used as evidence.',
        },
        'limits': [
            'Tuning used the same synthetic corpora that measure it; the lab clips are not an independent holdout.',
            'Four Kokoro voices and one Pocket voice; no human speech, no room or device measurement.',
            'Live hit rate on the owner microphone is not measured here (A7 pending human validation).',
        ],
    }
    (BASE / 'docs/evidence/wake-phrases.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'before': report['before'], 'after': report['after'], 'met': report['target_check']['met']}, indent=2))


if __name__ == '__main__':
    main()
