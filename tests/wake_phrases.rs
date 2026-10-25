//! Wake phrase setup (src/phrases.rs): ledger migration, validation codes, keyword sets, the switch with rollback,
//! the synthetic measurement through a fake TTS/worker pair, and multi-phrase detections. No models, no devices.
use gideon_base::phrases::{self, code, CustomFile, Lexicon, Setting, Stored};
use gideon_base::storage::{Config, Storage};
use gideon_base::wake::{Detection, Packet, WakeDescriptor, WakeInput};
use std::collections::BTreeMap;
use std::fs;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

const BASE_KEYWORDS: &str = "HH EY1 G IH1 D IY0 AH0 N @HEY_GIDEON\nOW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\nHH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n";
const LEXICON: &str = "HEY HH EY1\nGIDEON G IH1 D IY0 AH0 N\nLIGHT L AY1 T\nOPEN OW1 P AH0 N\nHI HH AY1\nCOMPUTER K AH0 M P Y UW1 T ER0\nHELLO HH AH0 L OW1\nYOU Y UW1\n";
const VOCAB: &str =
    "HH\nEY1\nG\nIH1\nD\nIY0\nAH0\nN\nL\nAY1\nT\nOW1\nP\nK\nM\nY\nUW1\nER0\nOW2\nAY1\n";

fn private_dir(path: &Path) {
    fs::create_dir_all(path).unwrap();
    fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
}

fn write_private(path: &Path, bytes: &[u8]) {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
        .unwrap();
    std::io::Write::write_all(&mut file, bytes).unwrap();
}

/// Packaged-looking wake manifest and its keyword file under `dir`; returns the manifest path.
fn base_manifest(dir: &Path) -> PathBuf {
    let assets = dir.join("assets");
    private_dir(&assets);
    fs::write(assets.join("keywords.txt"), BASE_KEYWORDS).unwrap();
    let manifest = dir.join("base-manifest.json");
    let value = serde_json::json!({
        "version": 1,
        "engine": "test-engine",
        "asset_root": assets,
        "encoder": "encoder.onnx",
        "decoder": "decoder.onnx",
        "joiner": "joiner.onnx",
        "hashes": {"encoder.onnx": "0", "decoder.onnx": "0", "joiner.onnx": "0", "tokens.txt": "0", "keywords.txt": "0"},
        "supported_phrases": {"hey_gideon": "HEY_GIDEON", "okay_gideon": "OKAY_GIDEON"},
        "rejection_labels": ["REJECT_HI"],
        "active_phrase": "hey_gideon",
        "fixtures": []
    });
    fs::write(&manifest, serde_json::to_vec(&value).unwrap()).unwrap();
    manifest
}

fn defaults() -> Vec<phrases::Entry> {
    let choice = |id: &str, label: &str, qualification: &'static str| phrases::Entry {
        id: id.into(),
        text: id.replace('_', " "),
        tokens: if id == "hey_gideon" {
            "HH EY1 G IH1 D IY0 AH0 N".into()
        } else {
            "OW2 K EY1 G IH1 D IY0 AH0 N".into()
        },
        label: label.into(),
        language: "en".into(),
        boost: if id == "hey_gideon" { 1.2 } else { 0.0 },
        threshold: 0.22,
        qualification,
        custom: false,
        measurement: None,
    };
    vec![
        choice("hey_gideon", "HEY_GIDEON", "dev_qualified"),
        choice("okay_gideon", "OKAY_GIDEON", "poc_required"),
    ]
}

fn custom_file(tokens: &str, text: &str, measurement: Option<phrases::Measurement>) -> CustomFile {
    CustomFile {
        version: 1,
        revision: 1,
        phrases: vec![Stored {
            id: phrases::custom_id(tokens),
            text: text.into(),
            tokens: tokens.into(),
            sha256: phrases::digest(text, tokens),
            measurement,
        }],
    }
}

/// `sh` stand-in for the interpreter: `--check` succeeds, the TTS worker answers one clip, the wake test reports
/// three hits in four positives and no false wake. `BAD` makes every call fail.
fn fake_python(path: &Path, bad: bool) {
    private_dir(path.parent().unwrap());
    // /usr/bin/sh: the sandbox binds /usr only (there is no /bin inside it).
    let body = if bad {
        "#!/usr/bin/sh\nexit 1\n".to_string()
    } else {
        "#!/usr/bin/sh\ncase \"$*\" in\n  *--check*) echo '{\"check\": \"ok\"}' ;;\n  *tts_worker*) read -r line; echo '{\"op\":\"ready\",\"session_id\":1}'; echo '{\"op\":\"pcm\",\"session_id\":1,\"samples\":[0.1,-0.1,0.05]}'; echo '{\"op\":\"done\",\"session_id\":1}' ;;\n  *) echo '{\"positives\":4,\"hits\":3,\"negatives\":6,\"false_wakes\":0,\"latency_ms_median\":900}' ;;\nesac\n".to_string()
    };
    write_private(path, body.as_bytes());
    fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
}

fn home_with_scripts(dir: &Path) -> PathBuf {
    let home = dir.join("home");
    private_dir(&home.join("scripts"));
    for script in ["wake_worker.py", "wake_phrase_test.py", "tts_worker.py"] {
        write_private(&home.join("scripts").join(script), b"# fake\n");
    }
    home
}

#[test]
fn legacy_ledger_loads_and_migrates_to_one_active_phrase() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("core");
    private_dir(&root);
    // A ledger written before wake_phrases existed: only the single `wake_phrase` field.
    write_private(
        &root.join("config.json"),
        br#"{"version":1,"session_timeout_ms":30000,"wake_phrase":"okay_gideon","revision":3}"#,
    );
    let mut storage = Storage::open(&root).unwrap();
    assert!(storage.config.wake_phrases.is_empty());
    let migrated = phrases::migrated(
        &storage.config.wake_phrases,
        storage.config.wake_phrase.as_deref(),
        "hey_gideon",
    );
    assert_eq!(
        migrated,
        vec![Setting {
            id: "okay_gideon".into(),
            active: true,
            sensitivity: None
        }]
    );
    // A ledger with neither field falls back to the packaged default.
    assert_eq!(
        phrases::migrated(&[], None, "hey_gideon")[0].id,
        "hey_gideon"
    );

    // Writing the list keeps the legacy field in step with the first active phrase, and survives a restart.
    let list = vec![
        Setting {
            id: "hey_gideon".into(),
            active: true,
            sensitivity: Some(1.2),
        },
        Setting {
            id: "custom_0123456789ab".into(),
            active: false,
            sensitivity: None,
        },
    ];
    storage.update_wake_phrases(3, list.clone()).unwrap();
    assert_eq!(storage.config.wake_phrase.as_deref(), Some("hey_gideon"));
    assert_eq!(storage.config.revision, 4);
    drop(storage);
    let reopened = Storage::open(&root).unwrap();
    assert_eq!(reopened.config.wake_phrases, list);
    // Too many active phrases never reach the ledger.
    let mut reopened = reopened;
    let many: Vec<Setting> = (0..6)
        .map(|i| Setting {
            id: format!("p{i}"),
            active: true,
            sensitivity: None,
        })
        .collect();
    assert!(reopened.update_wake_phrases(4, many).is_err());
    let _ = Config::default();
}

#[test]
fn validation_refuses_generic_short_and_unknown_phrases_with_codes() {
    let lexicon = Lexicon::parse(LEXICON, VOCAB);
    let refused = |text: &str| phrases::check(text, Some(&lexicon)).code;
    assert_eq!(refused(""), code::EMPTY);
    assert_eq!(refused("hey"), code::TOO_FEW_WORDS);
    assert_eq!(refused("computer"), code::TOO_FEW_WORDS);
    assert_eq!(refused("hey you"), code::TOO_GENERIC);
    assert_eq!(refused("hey gideon 2"), code::INVALID_CHARACTERS);
    assert_eq!(refused("hey blorf"), code::WORD_NOT_IN_LEXICON);
    assert_eq!(refused("hi light"), code::TOO_FEW_TOKENS);
    assert_eq!(refused("one two three four five"), code::TOO_MANY_WORDS);
    assert_eq!(
        phrases::check("hey gideon", None).code,
        code::LEXICON_UNAVAILABLE
    );
    let accepted = phrases::check("  Open   Light ", Some(&lexicon));
    assert!(accepted.ok, "{accepted:?}");
    assert_eq!(accepted.text.as_deref(), Some("Open Light"));
    assert_eq!(accepted.tokens.as_deref(), Some("OW1 P AH0 N L AY1 T"));
}

#[test]
fn keyword_set_is_boosted_per_phrase_and_adds_custom_lines() {
    let catalog = {
        let mut all = defaults();
        all.extend(phrases::entries(
            &[],
            &custom_file("L AY1 T G IH1 D IY0 AH0 N", "Light Gideon", None),
        ));
        all
    };
    let active = vec![Setting {
        id: "hey_gideon".into(),
        active: true,
        sensitivity: None,
    }];
    let text = phrases::keywords_text(BASE_KEYWORDS, &catalog, &active, 1.0).unwrap();
    // The measured default: boost 1.2, phrase threshold 0.22; competitors keep their packaged lines.
    assert_eq!(
        text,
        "HH EY1 G IH1 D IY0 AH0 N :1.2 #0.22 @HEY_GIDEON\nOW2 K EY1 G IH1 D IY0 AH0 N @OKAY_GIDEON\nHH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n"
    );
    // A custom phrase adds one boosted line; per-phrase sensitivity moves only its own threshold.
    let custom_id = phrases::custom_id("L AY1 T G IH1 D IY0 AH0 N");
    let both = vec![
        Setting {
            id: "hey_gideon".into(),
            active: true,
            sensitivity: Some(0.5),
        },
        Setting {
            id: custom_id.clone(),
            active: true,
            sensitivity: None,
        },
    ];
    let text = phrases::keywords_text(BASE_KEYWORDS, &catalog, &both, 1.0).unwrap();
    assert!(
        text.contains("HH EY1 G IH1 D IY0 AH0 N :1.2 #0.33 @HEY_GIDEON\n"),
        "{text}"
    );
    let label = format!(
        "CUSTOM_{}",
        custom_id["custom_".len()..].to_ascii_uppercase()
    );
    assert!(
        text.ends_with(&format!("L AY1 T G IH1 D IY0 AH0 N :1.2 #0.22 @{label}\n")),
        "{text}"
    );
    // An active phrase without its packaged line cannot become a keyword set.
    assert!(phrases::keywords_text(
        "HH AY1 G IH1 D IY0 AH0 N @REJECT_HI\n",
        &catalog,
        &active,
        1.0
    )
    .is_err());
}

#[test]
fn switch_waits_for_preflight_and_rolls_back_on_failure() {
    let dir = tempfile::tempdir().unwrap();
    let base = base_manifest(dir.path());
    let home = home_with_scripts(dir.path());
    let root = dir.path().join("core");
    private_dir(&root);
    let catalog = defaults();
    let first = vec![Setting {
        id: "hey_gideon".into(),
        active: true,
        sensitivity: None,
    }];

    // A failing interpreter refuses the switch and leaves no runtime behind.
    let bad = dir.path().join("bad/venv/bin/python");
    fake_python(&bad, true);
    assert!(phrases::stage(&root, &bad, &home, &base, &catalog, &first, 1.0).is_err());
    assert!(!root.join("wake-runtime/current").exists());

    // A passing preflight publishes `current`; a second switch keeps `previous` as the rollback target.
    let good = dir.path().join("good/venv/bin/python");
    fake_python(&good, false);
    phrases::stage(&root, &good, &home, &base, &catalog, &first, 1.0).unwrap();
    let current = root.join("wake-runtime/current/keywords.txt");
    assert!(fs::read_to_string(&current)
        .unwrap()
        .contains(":1.2 #0.22 @HEY_GIDEON"));
    let custom = custom_file("L AY1 T G IH1 D IY0 AH0 N", "Light Gideon", None);
    let mut second_catalog = catalog.clone();
    second_catalog.extend(phrases::entries(&[], &custom));
    let second = vec![Setting {
        id: custom.phrases[0].id.clone(),
        active: true,
        sensitivity: None,
    }];
    phrases::stage(&root, &good, &home, &base, &second_catalog, &second, 1.0).unwrap();
    assert!(fs::read_to_string(&current).unwrap().contains("@CUSTOM_"));
    assert!(root.join("wake-runtime/previous/keywords.txt").exists());

    // The ledger commit failed: the previous set comes back, and its manifest names its own keyword file.
    phrases::undo_switch(&root).unwrap();
    assert!(fs::read_to_string(&current)
        .unwrap()
        .contains(":1.2 #0.22 @HEY_GIDEON"));
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("wake-runtime/current/manifest.json")).unwrap())
            .unwrap();
    assert_eq!(
        manifest["keywords_file"],
        current.to_string_lossy().as_ref()
    );
    // Boot prefers the set that passes preflight.
    assert_eq!(
        phrases::boot_manifest(&root, &good, &home),
        Some(root.join("wake-runtime/current/manifest.json"))
    );
}

#[test]
fn synthetic_measurement_runs_through_a_fake_tts_and_worker_pair() {
    let dir = tempfile::tempdir().unwrap();
    let base = base_manifest(dir.path());
    let home = home_with_scripts(dir.path());
    let root = dir.path().join("core");
    private_dir(&root);
    let python = dir.path().join("wake/venv/bin/python");
    fake_python(&python, false);
    let tts_python = dir.path().join("tts/venv/bin/python");
    fake_python(&tts_python, false);
    let tts_manifest = dir.path().join("tts.json");
    fs::write(
        &tts_manifest,
        serde_json::json!({"root": dir.path()}).to_string(),
    )
    .unwrap();
    let custom = custom_file("L AY1 T G IH1 D IY0 AH0 N", "Light Gideon", None);
    let mut catalog = defaults();
    catalog.extend(phrases::entries(&[], &custom));
    let job = phrases::TestJob {
        id: custom.phrases[0].id.clone(),
        text: "Light Gideon".into(),
        tokens: custom.phrases[0].tokens.clone(),
        root: root.clone(),
        python: python.clone(),
        home: home.clone(),
        base_manifest: base.clone(),
        tts: gideon_base::tts::Config {
            python: tts_python,
            manifest: tts_manifest,
        },
        catalog,
    };
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let measurement = runtime.block_on(phrases::run_test(job)).unwrap();
    assert_eq!((measurement.positives, measurement.hits), (4, 3));
    assert_eq!((measurement.negatives, measurement.false_wakes), (6, 0));
    assert!(measurement.passed, "3 of 4 is 75 percent, at least 70");
    assert_eq!(measurement.source, "synthetic");

    // The result is stored with its phrase, and the store file still validates.
    write_private(
        &root.join("wake-phrases.json"),
        serde_json::to_string(&custom).unwrap().as_bytes(),
    );
    phrases::record_measurement(&root, &custom.phrases[0].id, measurement.clone()).unwrap();
    let stored = phrases::read_custom(&root).unwrap();
    assert_eq!(stored.revision, 2);
    assert_eq!(stored.phrases[0].measurement.as_ref(), Some(&measurement));
    // A forged `passed` flag is refused by the store.
    let mut forged = stored.clone();
    forged.phrases[0].measurement.as_mut().unwrap().passed = false;
    assert!(forged.validate().is_err());
}

#[test]
fn several_active_phrases_wake_the_session_one_at_a_time() {
    let descriptor = WakeDescriptor {
        engine: "test-engine".into(),
        supported_phrases: BTreeMap::from([
            ("hey_gideon".into(), "HEY_GIDEON".into()),
            ("custom_a".into(), "CUSTOM_A".into()),
            ("okay_gideon".into(), "OKAY_GIDEON".into()),
        ]),
        active_phrase: "hey_gideon".into(),
        active_phrases: vec!["hey_gideon".into(), "custom_a".into()],
    };
    let mut input = WakeInput::new(descriptor).unwrap();
    let packet = |phrase: Option<&str>, ts: u64| Packet {
        timestamp_us: ts,
        samples: vec![0.0; 1600],
        speech: None,
        detections: phrase
            .map(|p| Detection {
                phrase_id: p.into(),
                confidence: None,
                start_us: ts,
                end_us: ts + 100_000,
                engine: "test-engine".into(),
            })
            .into_iter()
            .collect(),
    };
    // Packets are 100 ms long here, so every detection sits past the cooldown of the previous one.
    assert!(
        input.accept(packet(Some("okay_gideon"), 0)).is_err(),
        "unlisted phrase is refused"
    );
    assert!(input.accept(packet(Some("custom_a"), 0)).unwrap().is_some());
    assert!(input.accept(packet(None, 100_000)).unwrap().is_none());
    for n in 2..30 {
        input.accept(packet(None, n * 100_000)).unwrap();
    }
    assert!(input
        .accept(packet(Some("hey_gideon"), 3_000_000))
        .unwrap()
        .is_some());
}
