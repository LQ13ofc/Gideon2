#!/usr/bin/env python3
"""Build the relocatable gideon-base-0.1.0 package (B4) into OUT_DIR.

Usage: scripts/build_package.py OUT_DIR [--version X]   (OUT_DIR must exist; the package dir must not)
The package dir is gideon-base-<X> (default X = 0.1.0).

Copies (never symlinks into the repo) runtime, venvs, pinned assets, manifest
templates, workers, app and launchers, then writes PACKAGE.json. Stdlib only.
"""
import fnmatch
import hashlib
import json
import argparse
import mmap
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
TOOLS = REPO / "scripts" / "package_tools"
VENVS = ["a1", "stt", "tts", "ui"]
VENV_BIN_KEEP = {"python", "python3", "python3.13"}
RUNTIME_LINK = "../../../runtime/python/bin/python3.13"
WAKE_ASSETS = REPO / "target/a1-competitive/assets"
REPLAY = REPO / "target/a3-assets/replay-manifest.json"
QUAL = REPO / "target/a1-competitive/manifest.json"
STT = REPO / "target/a3-assets/manifest.json"
STT_MODEL = REPO / "target/a3-assets/model"
TTS = REPO / "target/a5-assets/manifest.json"
TTS_ROOT = REPO / "target/a5-assets"
VAD = REPO / "target/a2-assets/silero_vad-v5.onnx"
# WP-7b: Portuguese and French packs, hash-pinned by their provisioning manifests (scripts/provision_pt_fr_*.py).
PT_FR_TTS = {"pt": REPO / "target/tts-pt-assets", "fr": REPO / "target/tts-fr-assets"}
PT_FR_STT_ROOT = REPO / "target/stt-pt-fr-assets"
# Pronunciation lexicon of the KWS asset: custom wake phrases are tokenized with it (src/phrases.rs).
LEXICON = REPO / "target/a1-assets/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/en.phone"
LEXICON_REL = "assets/wake/en.phone"
FIXTURE_ID = "wake-hey-brave__bf_emma__clean"
EVIDENCE = {"evidence-hey.json": "wake-hey-b12t22.json", "evidence-okay.json": "wake-okay-b0.json"}
DEV_TTS_ROOT = str(REPO / "target/a5-assets")
PYCACHE = "__pycache__"
PACKAGE_TARGET = REPO / "target/package-build"
# Only CPython's sysconfig build-prefix module is exempt from the host-path scan (documented, not read at runtime).
LEAK_ALLOWLIST = ("runtime/python/lib/python3.13/_sysconfigdata*.py",)


def die(message):
    sys.exit(f"build_package: {message}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def resolve_runtime():
    """uv CPython dir, resolved from the venv pyvenv.cfg home (its bin/ parent)."""
    for line in (REPO / "target/a1-venv/pyvenv.cfg").read_text().splitlines():
        if line.startswith("home"):
            home = Path(line.split("=", 1)[1].strip())
            runtime = home.parent.resolve()
            if not (runtime / "bin/python3.13").is_file():
                die(f"runtime missing python3.13: {runtime}")
            return runtime
    die("home not found in a1 pyvenv.cfg")


PLUGIN_PYTHON = "runtime/python/bin/python3.13"


def check_plugin_runtime(runtime):
    """Plugins run `python -I /plugin/main.py` under bwrap with only this runtime dir and /usr bound.

    The interpreter must be a real file (or a relative symlink that stays inside runtime), and the
    stdlib must be present, so nothing depends on a host path outside the package.
    """
    python = runtime / "bin/python3.13"
    if python.is_symlink():
        target = os.readlink(python)
        resolved = os.path.normpath(os.path.join(python.parent, target))
        if os.path.isabs(target) or not resolved.startswith(str(runtime) + os.sep):
            die(f"plugin interpreter escapes runtime: {python} -> {target}")
    if not python.is_file() or not os.access(python, os.X_OK):
        die(f"plugin interpreter missing or not executable: {python}")
    if not (runtime / "lib/python3.13/os.py").is_file():
        die(f"plugin runtime stdlib missing: {runtime / 'lib/python3.13'}")


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst, follow_symlinks=True)


SANDBOX_SRC = "/gideon-src"
BWRAP = "/usr/bin/bwrap"


def build_packaged_binary():
    """Build the packaged gideon-base with host paths removed; target/release is never touched.

    The repo is bound at SANDBOX_SRC inside a bwrap namespace so that env!("CARGO_MANIFEST_DIR"),
    which rustc --remap-path-prefix does not rewrite, is also neutral. Cargo's own home and the
    rustup home are remapped to /cargo and /rustup in debug and panic strings.
    """
    if not Path(BWRAP).is_file():
        die(f"{BWRAP} required to build the packaged binary without host paths")
    cargo_home = Path(os.environ.get("CARGO_HOME") or Path.home() / ".cargo")
    rustup_home = Path(os.environ.get("RUSTUP_HOME") or Path.home() / ".rustup")
    remaps = [f"--remap-path-prefix={REPO}={SANDBOX_SRC}",
              f"--remap-path-prefix={cargo_home}=/cargo",
              f"--remap-path-prefix={rustup_home}=/rustup"]
    rustflags = " ".join(filter(None, [os.environ.get("RUSTFLAGS", "")] + remaps))
    target = f"{SANDBOX_SRC}/target/package-build"
    argv = [BWRAP, "--unshare-all", "--die-with-parent", "--clearenv",
            "--setenv", "PATH", f"{cargo_home}/bin:/usr/bin:/bin",
            "--setenv", "HOME", str(Path.home()),
            "--setenv", "CARGO_HOME", str(cargo_home),
            "--setenv", "RUSTUP_HOME", str(rustup_home),
            "--setenv", "CARGO_TARGET_DIR", target,
            "--setenv", "RUSTFLAGS", rustflags,
            "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/bin", "/sbin",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", str(cargo_home), str(cargo_home),
            "--ro-bind", str(rustup_home), str(rustup_home),
            "--bind", str(REPO), SANDBOX_SRC,
            "--chdir", SANDBOX_SRC, "--",
            "cargo", "build", "--release", "--offline", "--locked",
            "--manifest-path", f"{SANDBOX_SRC}/Cargo.toml"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        die(f"packaged cargo build failed: {proc.stderr[-800:]}")
    built = PACKAGE_TARGET / "release/gideon-base"
    if not built.is_file():
        die(f"packaged build produced no binary: {built}")
    return built


def scan_host_paths(pkg):
    """Return [(rel, mark)] for every regular file (binary or text) holding a host path mark."""
    marks = [str(REPO).encode(), str(Path.home()).encode(), b".local/share/uv"]
    hits = []
    for path in sorted(pkg.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(pkg).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in LEAK_ALLOWLIST):
            continue
        if path.stat().st_size == 0:
            continue
        with open(path, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as blob:
            for mark in marks:
                if blob.find(mark) != -1:
                    hits.append((rel, mark.decode()))
    return hits


def checked_name(name):
    """A manifest file name must be a plain relative path: no absolute, no '..', no empty or backslash parts."""
    if not isinstance(name, str) or not name or "\0" in name or "\\" in name or name.startswith("/"):
        die(f"unsafe manifest name: {name!r}")
    parts = PurePosixPath(name).parts
    if any(part in ("", ".", "..") for part in parts):
        die(f"unsafe manifest name: {name!r}")
    return name


def checked_join(base, name):
    """base / name for a validated manifest name; the result must stay inside base."""
    joined = Path(base) / checked_name(name)
    if os.path.commonpath([os.path.abspath(base), os.path.abspath(joined)]) != os.path.abspath(base):
        die(f"manifest name escapes {base}: {name!r}")
    return joined


HOME_PROBE = "relative-home-probe"
UNSUPPORTED = "unknown or duplicate option"


def supports_home(binary):
    """True when the packaged gideon-base parses --home. Probe with a relative home: it is rejected by the
    home validation before any state is touched, so an unsupported binary reports the unknown option instead."""
    proc = subprocess.run([str(binary), "--root", "/nonexistent-gideon-probe", "--home", HOME_PROBE],
                          capture_output=True, text=True, timeout=60)
    return UNSUPPORTED not in (proc.stderr + proc.stdout)


def lexicon_template(pkg, src):
    """Copy the pronunciation lexicon to LEXICON_REL in pkg and return templates/lexicon.json (path + sha256).

    gideon-configure declares this path and digest to the Core, so custom phrases work in an installed package.
    """
    if not src.is_file() or src.is_symlink():
        die(f"missing pronunciation lexicon {src}")
    copy_file(src, checked_join(pkg, LEXICON_REL))
    digest = sha256(checked_join(pkg, LEXICON_REL))
    if digest != sha256(src):
        die(f"lexicon copy does not match its source: {src}")
    return {"path": f"@PREFIX@/{LEXICON_REL}", "sha256": digest}


def copy_pinned(src_dir, names, dst_dir, hashes):
    for name in names:
        src = checked_join(src_dir, name)
        if not src.is_file():
            die(f"missing pinned asset {src}")
        if sha256(src) != hashes[name]:
            die(f"asset does not match its pin: {src}")
        copy_file(src, checked_join(dst_dir, name))


def ignore_pycache(_dir, names):
    return [n for n in names if n == PYCACHE]


def copy_venv(name, dst):
    src = REPO / f"target/{name}-venv"
    if not src.is_dir():
        die(f"missing venv {src}")

    def ignore(directory, names):
        ignored = [n for n in names if n == PYCACHE]
        if Path(directory) == src / "bin":
            ignored += [n for n in names if n not in VENV_BIN_KEEP]
        if Path(directory) == src:
            # .lock is uv's empty world-writable (0666) lock file; it is not runtime and must not ship.
            ignored += [n for n in names if n in ("pyvenv.cfg", ".lock")]
        return ignored

    shutil.copytree(src, dst, symlinks=True, ignore=ignore)
    bin_python = dst / "bin/python"
    bin_python.unlink()
    os.symlink(RUNTIME_LINK, bin_python)
    for alias in ("python3", "python3.13"):
        target = os.readlink(dst / "bin" / alias)
        if target != "python":
            die(f"unexpected venv alias {alias} -> {target}")
    lines = (src / "pyvenv.cfg").read_text().splitlines()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        out.append("home = ../../../runtime/python/bin" if key == "home" else line)
    (dst / "pyvenv.cfg").write_text("\n".join(out) + "\n", encoding="utf-8")


def rebase_fixture(manifest, row_index):
    row = dict(manifest["fixtures"][row_index])
    row["path"] = f"@PREFIX@/assets/fixture/{Path(row['path']).name}"
    return row


def wake_template(manifest, fixture_row):
    out = dict(manifest)
    out["asset_root"] = "@PREFIX@/assets/wake"
    out["fixtures"] = [fixture_row]
    return out


def parse_args():
    parser = argparse.ArgumentParser(description="Build the relocatable gideon-base package (B4) into OUT_DIR.")
    parser.add_argument("out_dir", metavar="OUT_DIR")
    parser.add_argument("--version", default=VERSION,
                        help="package version; the package dir is gideon-base-<version> (default: %(default)s)")
    return parser.parse_args()


def main():
    args = parse_args()
    version = args.version
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,39}", version):
        die(f"invalid --version: {version!r}")
    name = f"gideon-base-{version}"
    out_root = Path(args.out_dir).resolve()
    if not out_root.is_dir():
        die(f"OUT_DIR must exist: {out_root}")
    pkg = out_root / name
    if pkg.exists():
        die(f"refusing to overwrite {pkg}")
    gideon_base = REPO / "target/release/gideon-base"
    if not gideon_base.is_file():
        die("target/release/gideon-base missing; build it first")
    packaged_binary = build_packaged_binary()
    # Build into a private sibling dir, then rename on success: a die or disk-full leaves no partial package.
    staging = Path(tempfile.mkdtemp(prefix=f".{name}.partial-", dir=out_root))
    try:
        dropped = build_tree(staging / name, name, version, gideon_base, packaged_binary)
        # A package whose Core or workers need a script it does not ship fails at runtime, not at build:
        # fail here instead (the live wake worker once imported a module the package lacked).
        closure = subprocess.run([sys.executable, str(REPO / "scripts" / "package_closure_check.py"),
                                  str(staging / name)], capture_output=True, text=True)
        if closure.returncode != 0:
            die("package closure check failed:\n" + closure.stdout + closure.stderr)
        if pkg.exists():
            die(f"refusing to overwrite {pkg}")
        os.rename(staging / name, pkg)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    entries = load(pkg / "PACKAGE.json")["files"]
    total = sum(e.get("size", 0) for e in entries)
    print(f"built {pkg}")
    print(f"entries {len(entries)} regular bytes {total} ({total / 2**20:.1f} MiB)")
    print("dropped / excluded:")
    for item in dropped:
        print(f"  - {item}")


def build_tree(pkg, pkg_name, version, gideon_base, packaged_binary):
    """Populate pkg (must not exist yet). Returns the list of dropped / excluded items."""
    pkg.mkdir()
    dropped = []

    # runtime + venvs
    runtime = resolve_runtime()
    shutil.copytree(runtime, pkg / "runtime/python", symlinks=True, ignore=ignore_pycache)
    check_plugin_runtime(pkg / "runtime/python")
    for venv in VENVS:
        copy_venv(venv, pkg / "venvs" / venv)
        extra = [i.name for i in (REPO / f"target/{venv}-venv/bin").iterdir() if i.name not in VENV_BIN_KEEP]
        dropped.append(f"venvs/{venv}/bin: {len(extra)} console scripts/activate files (dev shebangs)")

    # assets: wake (dereferenced), VAD, STT, TTS binaries, one fixture
    replay = load(REPLAY)
    qual = load(QUAL)
    stt = load(STT)
    tts = load(TTS)
    fixture_index = next(i for i, r in enumerate(replay["fixtures"]) if r.get("id") == FIXTURE_ID)
    fixture_row = rebase_fixture(replay, fixture_index)
    fixture_src = Path(replay["fixtures"][fixture_index]["path"])
    if sha256(fixture_src) != replay["fixtures"][fixture_index]["sha256"]:
        die("fixture bytes do not match pin")
    copy_pinned(WAKE_ASSETS, list(qual["hashes"]), pkg / "assets/wake", qual["hashes"])
    lexicon = lexicon_template(pkg, LEXICON)
    copy_file(VAD, pkg / "assets/vad/silero_vad-v5.onnx")
    if sha256(VAD) != replay["vad"]["sha256"]:
        die("VAD does not match pin")
    copy_pinned(STT_MODEL, list(stt["hashes"]), pkg / "assets/stt", stt["hashes"])
    dropped.append("target/a3-assets/model/decoder_kv_with_attention.ort (not in STT pin set)")
    # WP-7b: Parakeet (pt+fr, read in place by the STT worker) and the Pocket packs (copied by the Core on first use).
    pt_fr_stt = load(PT_FR_STT_ROOT / "manifest.json")
    copy_pinned(PT_FR_STT_ROOT, list(pt_fr_stt["hashes"]), pkg / "assets/stt-pt-fr", pt_fr_stt["hashes"])
    for pack, pack_root in PT_FR_TTS.items():
        pack_manifest = load(pack_root / "manifest.json")
        binaries = [a for a in pack_manifest["artifacts"] if a["name"] != "config.yaml"]
        copy_pinned(pack_root, [a["name"] for a in binaries], pkg / f"assets/tts-{pack}",
                    {a["name"]: a["sha256"] for a in binaries})
        # The config names its files by absolute path; the Core renders @ROOT@ for the state directory it installs to.
        config_text = (pack_root / "config.yaml").read_text(encoding="utf-8")
        if config_text.count(str(pack_root)) != 2:
            die(f"unexpected {pack} config.yaml layout")
        (pkg / f"assets/tts-{pack}/config.yaml").write_text(config_text.replace(str(pack_root), "@ROOT@"), encoding="utf-8")
        write_json(pkg / f"templates/tts-{pack}-manifest.json", {
            "engine": pack_manifest["engine"], "language": pack_manifest["language"],
            "voice_name": pack_manifest["voice_name"],
            "artifacts": [{"name": a["name"], "sha256": a["sha256"], "size": a["size"]} for a in binaries],
        })
    write_json(pkg / "templates/stt-nemo-manifest.json", {**pt_fr_stt, "model_root": "@PREFIX@/assets/stt-pt-fr"})
    dropped.append("target/stt-pt-fr-assets: encoder/decoder/joiner/tokens are copied; manifest paths rewritten")
    dropped.append("target/tts-pt-assets, target/tts-fr-assets: model, tokenizer and voice copied; config rewritten with @ROOT@")
    tts_binaries = [a for a in tts["artifacts"] if a["name"] != "config.yaml"]
    copy_pinned(TTS_ROOT, [a["name"] for a in tts_binaries], pkg / "assets/tts",
                {a["name"]: a["sha256"] for a in tts_binaries})
    copy_file(fixture_src, pkg / "assets/fixture" / fixture_src.name)
    dropped.append("target/a5-assets/soak.wav, soak-replay.json, provision.py (not runtime)")
    dropped.append(f"QA fixture rows: {len(replay['fixtures']) - 1} of {len(replay['fixtures'])} "
                   f"(~/.cache/gideon corpus; only '{FIXTURE_ID}' kept)")
    dropped.append("target/a2-assets/replay-manifest.json (superseded by templates)")
    dropped.append("target/a1-assets/* (only the 5 pinned wake files and en.phone, the lexicon, are copied)")

    # templates (manifests with @PREFIX@ / @PROFILE@ placeholders)
    tdir = pkg / "templates"
    write_json(tdir / "lexicon.json", lexicon)
    write_json(tdir / "replay-manifest.json", {**replay, **{
        "asset_root": "@PREFIX@/assets/wake",
        "fixtures": [fixture_row],
        "vad": {**replay["vad"], "path": "@PREFIX@/assets/vad/silero_vad-v5.onnx"},
        "stt": {"python": "@PREFIX@/venvs/stt/bin/python", "manifest": "@PROFILE@/stt-manifest.json"},
    }})
    write_json(tdir / "qualification-manifest.json", wake_template(qual, fixture_row))
    write_json(tdir / "stt-manifest.json", {**stt, "model_root": "@PREFIX@/assets/stt"})
    write_json(tdir / "tts-manifest.json", {**tts, "root": "@PROFILE@/tts",
                                             "config": "@PROFILE@/tts/config.yaml",
                                             "voice": "@PROFILE@/tts/alba.safetensors"})
    config_text = (TTS_ROOT / "config.yaml").read_text(encoding="utf-8")
    if config_text.count(DEV_TTS_ROOT) < 2:
        die("unexpected config.yaml layout")
    config_text = config_text.replace(DEV_TTS_ROOT, "@PROFILE@/tts")
    (tdir / "tts-config.yaml").write_text(config_text, encoding="utf-8")
    for template_name, source in EVIDENCE.items():
        copy_file(REPO / "target/evidence" / source, tdir / template_name)
    dropped.append("target/a1-competitive/assets symlinks replaced by dereferenced copies")

    # workers, app, binaries
    # net_broker.py is the Core-brokered HTTP process (LLM routes and S5 connections): without it every
    # network call of an installed package fails (the Core resolves <home>/scripts/net_broker.py).
    for worker in ("wake_worker.py", "stt_worker.py", "tts_worker.py", "command_worker.py", "pcm_fixture.py",
                   "net_broker.py", "audio_conditioning.py", "wake_phrase_test.py"):
        copy_file(REPO / "scripts" / worker, pkg / "scripts" / worker)
    app_src = REPO / "app"
    for app_file in ("main.py", "bridge.py", "uisettings.py", "visual.py", "Main.qml", "GlassCard.qml", "GlowButton.qml"):
        copy_file(app_src / app_file, pkg / "app" / app_file)
    shutil.copytree(app_src / "assets", pkg / "app/assets", ignore=ignore_pycache)
    # Shell and pages: theme singleton, components, page files, window shell, icons (QML loads them relative to each file).
    for app_dir in ("theme", "components", "pages", "shell", "icons"):
        shutil.copytree(app_src / app_dir, pkg / "app" / app_dir, ignore=ignore_pycache)
    copy_file(packaged_binary, pkg / "bin/gideon-base")
    if not supports_home(pkg / "bin/gideon-base"):
        die("packaged gideon-base does not parse --home; gideon-core cannot start S1 (rebuild the binary)")
    for tool in ("gideon-verify", "gideon-configure", "gideon-core", "gideon-app", "gideon-install", "gideon-launch"):
        copy_file(TOOLS / tool, pkg / "bin" / tool)
    for path in list((pkg / "bin").iterdir()) + [pkg / "runtime/python/bin/python3.13"]:
        if path.is_file():
            os.chmod(path, 0o755)

    # leak scan: no repository, home, cargo, rustup or uv path may survive in any payload file (binary or text)
    leaks = scan_host_paths(pkg)
    if leaks:
        die(f"host path leaked into payload: {leaks[:20]}")

    # PACKAGE.json
    entries = []
    for path in sorted(pkg.rglob("*")):
        rel = path.relative_to(pkg).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if target.startswith("/"):
                die(f"absolute symlink not allowed: {rel}")
            resolved = os.path.normpath(os.path.join(os.path.dirname(rel), target))
            if resolved.startswith("..") or os.path.isabs(resolved):
                die(f"symlink escapes prefix: {rel} -> {target}")
            entries.append({"type": "symlink", "path": rel, "target": target})
        elif path.is_dir():
            entries.append({"type": "dir", "path": rel})
        elif path.is_file():
            st = path.stat()
            entries.append({"type": "file", "path": rel, "size": st.st_size,
                            "sha256": sha256(path), "mode": f"{stat.S_IMODE(st.st_mode):04o}"})
    entries.sort(key=lambda e: e["path"])
    try:
        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], check=True,
                                    capture_output=True, text=True).stdout.strip())
    except (subprocess.CalledProcessError, OSError):
        commit, dirty = "unknown", True
    write_json(pkg / "PACKAGE.json", {
        "format": 1,
        "name": pkg_name,
        "version": version,
        "target": "linux_x86_64",
        "commit": commit,
        "dirty": dirty,
        "placeholders": ["@PREFIX@", "@PROFILE@"],
        "gideon_base_sha256": sha256(pkg / "bin/gideon-base"),
        "release_gideon_base_sha256": sha256(gideon_base),
        "source_equivalence": "same commit, remapped paths",
        "gideon_base_build": {
            "command": "cargo build --release --offline --locked",
            "CARGO_TARGET_DIR": "target/package-build",
            "sandbox": f"bwrap; repo bound at {SANDBOX_SRC}; CARGO_MANIFEST_DIR is {SANDBOX_SRC}",
            "remap_path_prefix": [f"<repo>={SANDBOX_SRC}", "<CARGO_HOME>=/cargo", "<RUSTUP_HOME>=/rustup"],
        },
        "plugin_runtime": {
            "interpreter": f"@PREFIX@/{PLUGIN_PYTHON}",
            "flag": "--plugin-python",
            "set_by": "gideon-core (only when the interpreter file exists in the package)",
            "runtime_dir": "@PREFIX@/runtime/python",
            "invocation": "python -I /plugin/main.py",
            "sandbox": "bwrap --unshare-all; runtime_dir and /usr bound read-only; plugins run sandboxed",
        },
        "files": entries,
    })
    return dropped


if __name__ == "__main__":
    main()
