#!/usr/bin/env python3
"""C2 contract test: plugin (llm_engine 1.1.0) <-> Qt bridge (app/bridge.py) drift guard.

Spawns tests/fixtures/llm_engine.py through the corrected host simulator of test_c2_fixtures
(the same Core envelope as src/plugins.rs) and feeds every llm_engine.models output into the
bridge's own validators: valid_models_page (list pages, every page of every tab), valid_model (describe, save_custom input),
valid_selftest (selftest), feature_ok (features). The bridge is imported read-only.
It also asserts that the constants both sides mirror are equal, and that the bridge refuses
mutated outputs while the plugin refuses the same mutated Models.

Run with the UI venv (the bridge imports PySide6):
  QT_QPA_PLATFORM=offscreen target/ui-venv/bin/python scripts/test_c2_contract.py
"""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
BRIDGE = ROOT / "app" / "bridge.py"
PLUGIN = ROOT / "tests" / "fixtures" / "llm_engine.py"
sys.path.insert(0, str(SCRIPTS))
import test_c2_fixtures as fx  # noqa: E402  (Plugin, HostSim, Route, models, custom, C2Base)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = _load(BRIDGE, "bridge_contract_view")
plugin = _load(PLUGIN, "llm_engine_contract_view")


def rec(output, model_id):
    return next(m for m in output["recommended"] if m["id"] == model_id)


def edited(obj, edit):
    copied = copy.deepcopy(obj)
    edit(copied)
    return copied


class ConstantsMirror(unittest.TestCase):
    """Values the plugin and the bridge both state must be equal (no silent drift)."""

    def test_model_keys_are_identical(self):
        self.assertEqual(plugin.MODEL_KEYS, bridge.MODEL_KEYS)

    def test_provider_sets_match(self):
        self.assertEqual(set(plugin.LOCAL_PROVIDERS), set(bridge.LOCAL_PROVIDERS))
        self.assertEqual(set(plugin.LOCAL_PROVIDERS) | set(plugin.CLOUD_PROVIDERS),
                         set(bridge.CONFIG_PROVIDERS))

    def test_enums_match(self):
        self.assertEqual(tuple(plugin.FEATURE_STATES), bridge.FEATURE_STATES)
        self.assertEqual(tuple(plugin.LATENCY_HINTS), ("low", "medium", "high", "unknown"))
        self.assertEqual(tuple(plugin.GPU_STATES), ("none", "optional", "required", "unknown"))
        self.assertEqual(set(plugin.FEATURE_KEYS), set(bridge.FEATURE_KEYS) | {"context_tokens"})

    def test_limits_match(self):
        self.assertEqual((plugin.LOCAL_PORT_MIN, plugin.LOCAL_PORT_MAX),
                         (bridge.LOCAL_PORT_MIN, bridge.LOCAL_PORT_MAX))
        self.assertEqual(plugin.MAX_CUSTOMS, bridge.MODELS_LIMIT)
        self.assertEqual(plugin.MAX_OUTPUT, bridge.OUTPUT_LIMIT)
        self.assertEqual(plugin.MAX_SETTINGS, fx.MAX_SETTINGS)


class BridgeContract(fx.C2Base):
    def models(self, inp, ctx=None):
        return fx.models(self.plugin, self.sim, inp, ctx=ctx)

    def describe(self, model_id):
        return self.ok(self.models({"action": "describe", "id": model_id}))["model"]

    # -- every output the plugin emits is accepted by the bridge ------------------------
    def test_every_list_page_is_accepted_by_the_bridge(self):
        out = self.list_out(ctx=fx.LOCAL_CTX)
        self.assertTrue(bridge.valid_models_page(out, "recommended", 0), out)
        self.assertEqual(out["selected"], {"provider": "local", "model": "gguf-local"})
        for model in out["items"]:
            self.assertTrue(bridge.valid_model(model, "recommended"), model["id"])
        for i in range(16):
            self.ok(self.save(fx.custom("c%02d" % i, label="Custom %02d" % i)))
        items, pages = self.all_pages("custom", ctx=fx.LOCAL_CTX)
        self.assertEqual(len(items), 16)
        for offset, page in zip(self.offsets(pages), pages):
            self.assertTrue(bridge.valid_models_page(page, "custom", offset), page)
            for model in page["items"]:
                self.assertTrue(bridge.valid_model(model, "custom"), model["id"])

    def test_paged_customs_with_accents_and_emoji_are_accepted(self):
        url = "https://e.io/" + "\U0001F600" * 46
        for i in range(6):
            self.ok(self.save(fx.custom("heavy-%d" % i, kind="cloud", provider="custom",
                                        model="m-%d" % i, custom_url=url,
                                        label="\U0001F600" * 12, license="\U0001F600" * 16)))
        items, pages = self.all_pages("custom")
        self.assertEqual([m["id"] for m in items], ["heavy-%d" % i for i in range(6)])
        self.assertGreater(len(pages), 1)
        for offset, page in zip(self.offsets(pages), pages):
            self.assertTrue(bridge.valid_models_page(page, "custom", offset), page)

    def offsets(self, pages):
        seen, out = 0, []
        for page in pages:
            out.append(seen)
            seen += len(page["items"])
        return out

    def test_describe_and_save_outputs_are_bridge_models_after_paging(self):
        saved = [fx.custom("mine"),
                 fx.custom("cloud-one", kind="cloud", provider="custom", model="m-1",
                           custom_url="https://example.com/v1")]
        for model in saved:
            self.assertTrue(bridge.valid_model(model, "custom"), model["id"])  # UI side first
            self.ok(self.save(model))
        items, _pages = self.all_pages("custom")
        self.assertEqual([m["id"] for m in items], ["mine", "cloud-one"])
        for model in items:
            self.assertTrue(bridge.valid_model(model, "custom"), model["id"])

    def test_describe_outputs_are_bridge_models(self):
        for model_id in fx.RECOMMENDED_IDS:
            model = self.describe(model_id)
            self.assertTrue(bridge.valid_model(model, "recommended"), model_id)
        self.ok(self.save(fx.custom("mine")))
        self.assertTrue(bridge.valid_model(self.describe("mine"), "custom"))

    def test_selftest_outputs_are_accepted_for_local_text_only_and_cloud(self):
        out = self.ok(self.models({"action": "selftest"}, ctx=fx.LOCAL_CTX))
        self.assertTrue(bridge.valid_selftest(out), out)
        self.sim.routes["primary"] = fx.Route(self.llama_text)
        out = self.ok(self.models({"action": "selftest"}, ctx=fx.LOCAL_CTX))
        self.assertTrue(bridge.valid_selftest(out), out)
        self.assertEqual(out["features"]["tool_use"], "unsupported")
        self.use_cloud()
        out = self.ok(self.models({"action": "selftest"}, ctx=fx.GOOGLE_CTX))
        self.assertTrue(bridge.valid_selftest(out), out)

    def test_features_outputs_use_the_bridge_vocabulary(self):
        contexts = [None, fx.GOOGLE_CTX, fx.LOCAL_CTX, fx.TEXT_CTX,
                    {"llm": {"provider": "local", "model": "nope"}}]
        self.ok(self.save(fx.custom("text-only-3b", kind="cloud", provider="custom",
                                    model="text-only-3b", custom_url="https://example.com/v1",
                                    features={"streaming": "supported", "tool_use": "unsupported",
                                              "vision": "unknown", "cancel": "unknown",
                                              "context_tokens": None})))
        for ctx in contexts:
            with self.subTest(ctx=ctx):
                out = self.ok(self.models({"action": "features"}, ctx=ctx))
                self.assertEqual(set(out), {"selected", "source", "features"})
                self.assertTrue(bridge.feature_ok(out["features"]), out)
                self.assertIn(out["source"], bridge.CERT_STATES + ("unknown",))
                if out["selected"] is not None:
                    self.assertIn(out["selected"]["provider"], bridge.CONFIG_PROVIDERS)

    def test_features_after_selftest_is_probed_and_accepted(self):
        self.ok(self.models({"action": "selftest"}, ctx=fx.LOCAL_CTX))
        out = self.ok(self.models({"action": "features"}, ctx=fx.LOCAL_CTX))
        self.assertEqual(out["source"], "probed")
        self.assertTrue(bridge.feature_ok(out["features"]), out)

    def test_candidate_entries_are_labelled_candidate_not_certified(self):
        out = self.ok(self.models({"action": "features"}, ctx=fx.LOCAL_CTX))
        self.assertEqual(out["source"], "candidate")
        out = self.ok(self.models({"action": "features"}, ctx=fx.GOOGLE_CTX))
        self.assertEqual(out["source"], "certified")

    # -- the bridge refuses mutated outputs, and the plugin refuses the same Models ----
    def test_bridge_refuses_mutated_list_pages(self):
        self.ok(self.save(fx.custom("mine")))
        self.ok(self.save(fx.custom("other")))
        out = self.list_out("custom", offset=0, limit=6, ctx=fx.LOCAL_CTX)
        self.assertTrue(bridge.valid_models_page(out, "custom", 0))
        self.assertEqual(len(out["items"]), 2)
        mutations = {
            "unknown top-level key": lambda o: o.update(custom_total=1),
            "missing hardware": lambda o: o.pop("hardware"),
            "missing total": lambda o: o.pop("total"),
            "wrong tab echoed": lambda o: o.update(tab="recommended"),
            "wrong offset echoed": lambda o: o.update(offset=1),
            "unknown model key": lambda o: o["items"][0].update(name="x"),
            "bad feature enum": lambda o: o["items"][0]["features"].update(streaming="yes"),
            "bad latency enum": lambda o: o["items"][0].update(latency_hint="fast"),
            "local port out of range": lambda o: o["items"][0].update(local_port=80),
            "local without port": lambda o: o["items"][0].update(local_port=None),
            "gpu outside hardware enum": lambda o: o["hardware"].update(gpu="cuda"),
            "duplicate id in page": lambda o: o["items"].append(dict(o["items"][0])),
            "custom with recommended tier": lambda o: o["items"][0].update(tier="recommended"),
            "more than limit items": lambda o: o.update(items=o["items"] * 4),
            "total below the page end": lambda o: o.update(total=1),
            "items past total": lambda o: o.update(offset=2, total=2),
            "empty page before total": lambda o: o.update(items=[]),
        }
        for label, edit in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(bridge.valid_models_page(edited(out, edit), "custom", 0), label)
        rec_out = self.list_out("recommended")
        self.assertFalse(bridge.valid_models_page(rec_out, "custom", 0))  # wrong tab asked
        self.assertFalse(bridge.valid_models_page(rec_out, "recommended", 1))  # wrong offset asked
        self.assertTrue(bridge.valid_models_page(rec_out, "recommended", 0))

    def test_bridge_refuses_mutated_selftest_outputs(self):
        out = self.ok(self.models({"action": "selftest"}, ctx=fx.LOCAL_CTX))
        mutations = {
            "source declared": lambda o: o.update(source="declared"),
            "extra key": lambda o: o.update(custom_total=1),
            "vision claimed supported": lambda o: o["features"].update(vision="supported"),
            "not ok": lambda o: o.update(ok=False),
            "negative latency": lambda o: o.update(latency_ms=-1),
        }
        for label, edit in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(bridge.valid_selftest(edited(out, edit)), label)

    def test_bridge_and_plugin_refuse_the_same_bad_custom_models(self):
        base = fx.custom("bad")
        bad = {
            "unknown key": dict(base, name="x"),
            "bad feature enum": fx.with_path(base, ("features", "streaming"), "yes"),
            "bad latency enum": fx.with_path(base, ("latency_hint",), "fast"),
            "local port out of range": fx.with_path(base, ("local_port",), 80),
            "local without port": fx.with_path(base, ("local_port",), None),
        }
        for label, model in bad.items():
            with self.subTest(model=label):
                self.assertFalse(bridge.valid_model(model, "custom"), label)
                self.err(self.save(model), "invalid_input")
        self.assertIsNone(self.sim.store)


if __name__ == "__main__":
    unittest.main(verbosity=2)
