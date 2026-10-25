#!/usr/bin/env python3
"""Pronunciation lexicon of an installed Base pack (custom wake phrases): build, configure and verify.

Run: python3 -I -B scripts/test_package_lexicon.py   (stdlib unittest; no network; no real HOME).
Every package here is a tiny synthetic tree under /tmp/gl-<hex>/ built by these tests; the 1.8 GiB
package is never built. The real gideon-configure and gideon-verify run from the fixture's bin/.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "scripts" / "package_tools"
BUILD = REPO / "scripts" / "build_package.py"
CONFIGURE = TOOLS / "gideon-configure"
VERIFY = TOOLS / "gideon-verify"
LEXICON_BYTES = b"HEY HH EY1\nGIDEON G IH1 D IY0 AH0 N\nLIGHT L AY1 T\n"
WAKE_FILES = {"enc.onnx": b"encoder", "dec.onnx": b"decoder", "join.onnx": b"joiner",
              "tokens.txt": b"HH\nEY1\nG\n", "keywords.txt": b"HH EY1 G @HEY\n"}
STT_FILES = {"encoder.ort": b"stt-encoder"}
TTS_FILES = {"model.safetensors": b"tts-model", "tokenizer.json": b"tts-tokenizer", "alba.safetensors": b"tts-voice"}
VAD_BYTES = b"vad"
FIXTURE_WAV = b"RIFF-fixture"


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


BP = load_module("build_package_lexicon", BUILD)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, mode)


def write_manifest(pkg, exclude=()):
    """PACKAGE.json listing every regular file of pkg (as build_package does), minus `exclude`."""
    entries = []
    for path in sorted(pkg.rglob("*")):
        rel = path.relative_to(pkg).as_posix()
        if path.is_dir() or rel == "PACKAGE.json" or rel in exclude:
            continue
        st = path.stat()
        entries.append({"type": "file", "path": rel, "size": st.st_size, "sha256": sha(path.read_bytes()),
                        "mode": f"{stat.S_IMODE(st.st_mode):04o}"})
    manifest = {"format": 1, "name": "gideon-base-test", "version": "0.0.0", "files": entries}
    (pkg / "PACKAGE.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.base = Path("/tmp") / f"gl-{uuid.uuid4().hex[:12]}"
        self.base.mkdir(mode=0o700)
        self.addCleanup(shutil.rmtree, self.base, True)

    def fixture(self, name):
        """A synthetic installed-layout package: bin tools, templates (with lexicon.json), assets."""
        pkg = self.base / name
        (pkg / "bin").mkdir(parents=True)
        shutil.copy2(CONFIGURE, pkg / "bin" / "gideon-configure")
        shutil.copy2(VERIFY, pkg / "bin" / "gideon-verify")
        source = self.base / f"{name}-en.phone"
        source.write_bytes(LEXICON_BYTES)
        lexicon = BP.lexicon_template(pkg, source)
        wake = {"engine": "fixture-kws", "asset_root": "@PREFIX@/assets/wake", "encoder": "enc.onnx",
                "decoder": "dec.onnx", "joiner": "join.onnx", "rejection_labels": ["REJ"],
                "supported_phrases": {"hey_gideon": {}, "okay_gideon": {}},
                "hashes": {n: sha(d) for n, d in WAKE_FILES.items()}}
        for name_, data in WAKE_FILES.items():
            write(pkg / "assets/wake" / name_, data)
        write(pkg / "assets/fixture/fixture.wav", FIXTURE_WAV)
        write(pkg / "assets/vad/silero_vad-v5.onnx", VAD_BYTES)
        for name_, data in STT_FILES.items():
            write(pkg / "assets/stt" / name_, data)
        for name_, data in TTS_FILES.items():
            write(pkg / "assets/tts" / name_, data)
        replay = dict(wake, fixtures=[{"id": "f1", "path": "@PREFIX@/assets/fixture/fixture.wav",
                                       "sha256": sha(FIXTURE_WAV)}],
                      vad={"path": "@PREFIX@/assets/vad/silero_vad-v5.onnx", "sha256": sha(VAD_BYTES)},
                      stt={"python": "@PREFIX@/venvs/stt/bin/python", "manifest": "@PROFILE@/stt-manifest.json"})
        stt = {"engine": "fixture-stt", "language": "en", "provider": "CPU", "model_root": "@PREFIX@/assets/stt",
               "hashes": {n: sha(d) for n, d in STT_FILES.items()}}
        artifacts = [{"name": n, "sha256": sha(d), "size": len(d)} for n, d in TTS_FILES.items()]
        artifacts.append({"name": "config.yaml", "sha256": "0" * 64, "size": 0})
        tts = {"engine": "fixture-tts", "voice": "@PROFILE@/tts/alba.safetensors", "root": "@PROFILE@/tts",
               "config": "@PROFILE@/tts/config.yaml", "artifacts": artifacts}
        templates = pkg / "templates"
        for name_, value in {"replay-manifest.json": replay, "qualification-manifest.json": wake,
                             "stt-manifest.json": stt, "tts-manifest.json": tts,
                             "lexicon.json": lexicon}.items():
            write(templates / name_, json.dumps(value, indent=2).encode("utf-8"))
        write(templates / "tts-config.yaml", b"root: @PROFILE@/tts\n")
        for ident, name_ in (("hey_gideon", "evidence-hey.json"), ("okay_gideon", "evidence-okay.json")):
            evidence = {"engine": "fixture-kws", "active_phrase": ident, "manifest_sha256": "0" * 64}
            write(templates / name_, json.dumps(evidence).encode("utf-8"))
        write_manifest(pkg)
        return pkg

    def configure(self, pkg, state):
        return subprocess.run([sys.executable, "-I", "-B", str(pkg / "bin" / "gideon-configure"), str(state)],
                              capture_output=True, text=True, timeout=120)

    def verify(self, pkg):
        return subprocess.run([sys.executable, "-I", "-B", str(pkg / "bin" / "gideon-verify")],
                              capture_output=True, text=True, timeout=120)


class LexiconTemplateTests(Base):
    def test_copies_lexicon_and_pins_its_digest(self):
        pkg = self.base / "pkg"
        pkg.mkdir()
        source = self.base / "en.phone"
        source.write_bytes(LEXICON_BYTES)
        template = BP.lexicon_template(pkg, source)
        self.assertEqual((pkg / "assets/wake/en.phone").read_bytes(), LEXICON_BYTES)
        self.assertEqual(template, {"path": "@PREFIX@/assets/wake/en.phone", "sha256": sha(LEXICON_BYTES)})

    def test_missing_lexicon_is_refused(self):
        pkg = self.base / "pkg"
        pkg.mkdir()
        with self.assertRaises(SystemExit):
            BP.lexicon_template(pkg, self.base / "absent.phone")
        self.assertFalse((pkg / "assets").exists())

    def test_symlinked_lexicon_is_refused(self):
        pkg = self.base / "pkg"
        pkg.mkdir()
        source = self.base / "en.phone"
        source.write_bytes(LEXICON_BYTES)
        link = self.base / "link.phone"
        os.symlink(source, link)
        with self.assertRaises(SystemExit):
            BP.lexicon_template(pkg, link)


class LexiconConfigureTests(Base):
    def test_pack_declares_the_packaged_lexicon(self):
        pkg = self.fixture("pkg")
        state = self.base / "state"
        proc = self.configure(pkg, state)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        pack = json.loads((state / "profile" / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["lexicon"], {"path": str(pkg / "assets/wake/en.phone"), "sha256": sha(LEXICON_BYTES)})

    def test_relocated_package_declares_its_own_lexicon(self):
        pkg = self.fixture("pkg")
        moved = self.base / "moved"
        shutil.copytree(pkg, moved)
        state = self.base / "state"
        proc = self.configure(moved, state)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        pack = json.loads((state / "profile" / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["lexicon"]["path"], str(moved / "assets/wake/en.phone"))
        self.assertNotIn(str(pkg), json.dumps(pack))

    def test_tampered_lexicon_is_refused_without_pack(self):
        pkg = self.fixture("pkg")
        (pkg / "assets/wake/en.phone").write_bytes(b"X" * len(LEXICON_BYTES))
        state = self.base / "state"
        proc = self.configure(pkg, state)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lexicon does not match pinned sha256", proc.stderr)
        self.assertFalse((state / "profile" / "pack.json").exists())

    def test_missing_lexicon_template_is_refused(self):
        pkg = self.fixture("pkg")
        (pkg / "templates/lexicon.json").unlink()
        proc = self.configure(pkg, self.base / "state")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no lexicon template", proc.stderr)

    def test_lexicon_outside_package_assets_is_refused(self):
        pkg = self.fixture("pkg")
        template = json.loads((pkg / "templates/lexicon.json").read_text())
        template["path"] = "@PREFIX@/../en.phone"
        (pkg / "templates/lexicon.json").write_text(json.dumps(template))
        proc = self.configure(pkg, self.base / "state")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("inside the package assets", proc.stderr)


class LexiconVerifyTests(Base):
    def test_fixture_package_with_listed_lexicon_verifies(self):
        proc = self.verify(self.fixture("pkg"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_tampered_lexicon_fails_verification(self):
        pkg = self.fixture("pkg")
        (pkg / "assets/wake/en.phone").write_bytes(b"X" * len(LEXICON_BYTES))
        proc = self.verify(pkg)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("sha256 mismatch: assets/wake/en.phone", proc.stderr)

    def test_template_pin_differing_from_listing_fails_verification(self):
        pkg = self.fixture("pkg")
        template = json.loads((pkg / "templates/lexicon.json").read_text())
        template["sha256"] = "1" * 64
        (pkg / "templates/lexicon.json").write_text(json.dumps(template))
        write_manifest(pkg)
        proc = self.verify(pkg)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("pin differs from PACKAGE.json", proc.stderr)

    def test_lexicon_missing_from_manifest_fails_verification(self):
        pkg = self.fixture("pkg")
        write_manifest(pkg, exclude={"assets/wake/en.phone"})
        proc = self.verify(pkg)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lexicon not listed in PACKAGE.json", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
