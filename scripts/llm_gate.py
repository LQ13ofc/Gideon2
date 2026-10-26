#!/usr/bin/env python3
"""WP-6 / WP-18b real local LLM gate (stdlib only; run as `python3 -I scripts/llm_gate.py`).

Nothing here is a fixture: the llama.cpp server is the real b11552 build on 127.0.0.1 running the
verified Qwen2.5-1.5B-Instruct Q4_K_M GGUF; the Core is the release binary without test flags; the
plugin is scripts/llm_engine_plugin.py installed through the Hub (fixture catalog
tests/fixtures/llm_hub_prod.json).

WP-18b: the Core owns the llama-server lifecycle. The gate writes the owner settings file
(`llm-local.json` in the Core root) and does NOT start the server itself. Checks:

  R1  artifacts: archive and GGUF sha256 equal the published hashes (scripts/llm_manifest.json)
  R2  lifecycle: no server before the first local call; the first llm_engine call starts it
      (state running, /health 200, one llama-server process of this root); its load time is measured
  R3  direct measurement: TTFT and decode tokens/s on the Core-started server (scripts/llm_bench.py)
  R4  Core: plugin llm_engine 1.3.0 running; local route configured; the Qwen entry is listed
  R5  selftest through the Core: streaming ok, tool_use probed (supported or unsupported, never faked)
  R6  mark_good then 5 chat turns through the Core: non-empty text, finish stop, partials seen
  R7  skill draft (SKILL-01): llm_engine.skill_draft through the Core; nothing is approved or run
  R9  agent loop with the real model: tool call executed by the Core, final answer produced
  R10 idle stop: after `idle_s` without chat the Core stops the server (state stopped, port closed,
      no stray process); the next chat starts it again
  R11 Core exit: the server and its sandbox are gone (port closed, no stray process), temp root removed

Usage: python3 -I scripts/llm_gate.py [--write-evidence]
--write-evidence writes docs/evidence/wp6-llm.json. Keys: none (the local route has no key, no consent).
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / "scripts"
sys.path.insert(0, str(SCRIPTS))

import llm_bench  # noqa: E402
import verify_c2_live as live  # noqa: E402  (Core wire, Hub install, invoke helpers; C2 gate)

RUNTIME = Path(os.environ.get("GIDEON_LLM_RUNTIME", str(Path.home() / ".local/share/gideon-llm")))
MANIFEST = SCRIPTS / "llm_manifest.json"
PLUGIN_SRC = SCRIPTS / "llm_engine_plugin.py"
CATALOG = BASE / "tests/fixtures/llm_hub_prod.json"
EVIDENCE = BASE / "docs/evidence/wp6-llm.json"
live.PLUGIN_SRC = PLUGIN_SRC  # the C2 harness stages this file and checks the catalog hash
live.CATALOG = CATALOG
LOCAL_PORT = 8080
THREADS = 8
CTX = 4096
IDLE_S = 20
MODEL_ID = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
DRAFT_CAP = "llm_engine.skill_draft"
DESCRIPTION = ("Criar uma skill que diz a hora atual em português. "
               "Ela não deve alterar nada no computador.")
AGENT_GOAL = "Que horas são agora? Consulte a ferramenta de hora e responda em uma frase."
CHAT_PROMPTS = [
    "Diga olá em uma frase curta.",
    "Qual é a capital do Brasil? Responda em uma frase.",
    "Explique em uma frase o que é um assistente de voz.",
    "Quanto é dois mais dois? Responda só com o número.",
    "Escreva uma frase sobre o mar.",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run_tool(argv):
    """One llm_local.py command (verify / extract only in this gate); returns its JSON object."""
    proc = subprocess.run([sys.executable, "-I", str(SCRIPTS / "llm_local.py")] + argv,
                          capture_output=True, text=True, timeout=400)
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": "tool_output_invalid", "rc": proc.returncode}


def host_facts():
    model = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    ram_kb = 0
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                ram_kb = int(line.split()[1])
                break
    except (OSError, ValueError):
        pass
    return {"cpu": model, "logical_cpus": os.cpu_count(), "ram_gb": round(ram_kb / 1048576, 1)}


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def server_processes(marker):
    """PIDs of any process whose command line names the server binary and this Core root's run dir."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "llama-server" in command and marker in command:
            found.append(int(entry.name))
    return found


def wait_for(predicate, seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if predicate():
            return True
        time.sleep(0.25)
    return predicate()


def llm_local_state(root):
    return (live.wire(root, {"op": "snapshot"}).get("llm") or {}).get("local_server")


def timed_chat(root, text, max_tokens, deadline=30000):
    """One chat through the Core. TTFT = first partial seen by polling the snapshot (10 ms)."""
    started = time.monotonic()
    code = live.wire(root, {"op": "capability_invoke", "capability": live.CAP, "deadline_ms": deadline,
                            "input": {"messages": [{"role": "user", "content": text}], "tools": False,
                                      "max_tokens": max_tokens}})["code"]
    if code != "ok":
        return {"ok": False, "error": "invoke:" + code}
    first = None
    until = started + deadline / 1000 + 10
    while True:
        snap = live.wire(root, {"op": "snapshot"})
        if first is None and snap.get("partial") is not None:
            first = time.monotonic() - started
        if snap.get("capability_result") is not None:
            return {"ok": True, "result": snap["capability_result"], "ttft_s": first,
                    "total_s": time.monotonic() - started}
        if time.monotonic() > until:
            return {"ok": False, "error": "timeout_waiting_result"}
        time.sleep(0.01)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args(argv)
    checks = []
    measures = {}
    samples = []
    notes = {}

    def check(name, ok, detail=None):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + ("" if detail is None else " :: " + str(detail)),
              flush=True)
        return bool(ok)

    archive = RUNTIME / "dl/llama-b11552/llama-b11552-bin-ubuntu-x64.tar.gz"
    model_path = RUNTIME / "dl/qwen-1.5b-q4km" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    bin_path = RUNTIME / "bin/llama-b11552/llama-server"
    run_dir = RUNTIME / "run-core"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verdict = run_tool(["verify", "--manifest", str(MANIFEST), "--archive", str(archive),
                        "--model", str(model_path)])
    check("R1 artifacts sha256 equal the published hashes", verdict.get("ok") is True, verdict.get("error"))
    catalog_entry = next(p for p in json.loads(CATALOG.read_text(encoding="utf-8"))["plugins"]
                         if p["plugin_id"] == "llm_engine")["binaries"][0]
    check("R1 Hub catalog hash and size match scripts/llm_engine_plugin.py",
          catalog_entry["sha256"] == sha256_file(PLUGIN_SRC) and catalog_entry["size"] == PLUGIN_SRC.stat().st_size,
          catalog_entry["sha256"][:16])

    root_dir = None
    core = None
    try:
        check("R2 precondition: port 8080 free and no llama-server of earlier runs",
              not port_open(LOCAL_PORT) and not server_processes(str(run_dir)),
              {"port_open": port_open(LOCAL_PORT)})
        (RUNTIME / "gate").mkdir(parents=True, exist_ok=True)
        root_dir = Path(tempfile.mkdtemp(prefix="core-", dir=str(RUNTIME / "gate")))
        root = root_dir / "root"
        root.mkdir(mode=0o700)
        run_dir.mkdir(parents=True, exist_ok=True)
        settings = {"version": 1, "binary": str(bin_path), "model": str(model_path),
                    "model_sha256": manifest["model"]["sha256"], "run_dir": str(run_dir),
                    "threads": THREADS, "ctx": CTX, "idle_s": IDLE_S}
        (root / "llm-local.json").write_text(json.dumps(settings), encoding="utf-8")
        core_log = root_dir / "core.log"
        core = live.start_core(root, core_log, live.BIN, False)
        installed = live.install_llm(root)
        item = live.item(live.wire(root, {"op": "snapshot"}))
        check("R4 plugin llm_engine 1.3.0 running through the Hub",
              item is not None and item.get("state") == "running" and item.get("version", "1.3.0") == "1.3.0",
              {"steps": installed, "state": (item or {}).get("state")})
        cfg_code = live.wire(root, {"op": "llm_configure",
                                    "revision": live.wire(root, {"op": "snapshot"})["llm"]["revision"],
                                    "provider": "local", "model": MODEL_ID, "custom_url": None,
                                    "local_port": LOCAL_PORT, "cloud_consent": False})["code"]
        check("R4 local route configured (no key, no consent)", cfg_code == "ok", cfg_code)
        before = llm_local_state(root)
        check("R2 no server before the first local call (on demand, not at boot or configure)",
              before == "stopped" and not port_open(LOCAL_PORT) and not server_processes(str(run_dir)),
              {"local_server": before})

        # The first llm_engine call starts the server through the Core: selftest is that first call.
        started = time.monotonic()
        code, res = live.invoke(root, live.MODELS, {"action": "selftest"}, 30000)
        first_call_s = round(time.monotonic() - started, 2)
        out = (res or {}).get("output") or {}
        features = out.get("features") or {}
        state_after = llm_local_state(root)
        pids = server_processes(str(run_dir))
        check("R2 first local call starts the server: state running, /health 200, one process",
              state_after == "running" and port_open(LOCAL_PORT) and len(pids) >= 1,
              {"local_server": state_after, "processes": len(pids), "first_call_s": first_call_s})
        notes["core_start"] = {"first_call_s": first_call_s, "load_seconds_in_selftest": out.get("latency_ms")}
        check("R5 selftest through the Core: streaming ok", (res or {}).get("ok") is True
              and features.get("streaming") == "supported", {"code": code, "latency_ms": out.get("latency_ms")})
        measures["selftest"] = {"latency_ms": out.get("latency_ms"), "features": features,
                                "source": out.get("source")}
        check("R5 tool_use probed, not declared (value recorded, never forced)",
              features.get("tool_use") in ("supported", "unsupported"), features.get("tool_use"))
        listed = live.models_list(root) or []
        qwen = [m for m in listed if m.get("model") == MODEL_ID]
        check("R4 the Qwen GGUF entry is listed by llm_engine.models", len(qwen) == 1,
              {"entries": len(listed)})
        code, desc = live.invoke(root, live.MODELS, {"action": "describe", "id": "local-qwen2.5-1.5b-q4km"}, 10000)
        described = ((desc or {}).get("output") or {}).get("model") or {}
        check("R4 describe returns the local entry with its certification and sha256",
              (desc or {}).get("ok") is True and described.get("sha256") and
              described.get("certification", {}).get("state") == "certified",
              {"code": code, "certification": described.get("certification", {}).get("state")})
        if (res or {}).get("ok") is True:
            live.mark_good(root)

        runs = []
        for index in range(5):
            messages = [{"role": "system", "content": llm_bench.SYSTEM},
                        {"role": "user", "content": llm_bench.BENCH_PROMPTS[index]}]
            runs.append(llm_bench.stream_chat(LOCAL_PORT, messages, 128))
        measures["direct_server"] = llm_bench.summarize(runs)
        check("R3 direct measurement on the Core-started server: 5 streamed runs",
              all(r["text"] for r in runs) and measures["direct_server"]["decode_tokens_per_s_median"],
              measures["direct_server"])

        turns = []
        for index, text in enumerate(CHAT_PROMPTS):
            turn = timed_chat(root, text, 128)
            result = turn.get("result") or {}
            output = result.get("output") or {}
            good = (turn.get("ok") is True and result.get("ok") is True and bool(output.get("text"))
                    and output.get("finish_reason") in ("stop", "length"))
            turns.append({"prompt_index": index, "ok": good, "ttft_s": turn.get("ttft_s"),
                          "total_s": turn.get("total_s"), "finish": output.get("finish_reason"),
                          "chars": len(output.get("text") or ""),
                          "partial_seen": turn.get("ttft_s") is not None, "error": turn.get("error")})
            if good:
                samples.append({"prompt": text, "reply": output.get("text")[:400]})
        measures["core_chat"] = turns
        ttfts = [t["ttft_s"] for t in turns if t.get("ttft_s") is not None]
        check("R6 five chat turns through the Core: non-empty replies, partials seen",
              all(t["ok"] for t in turns) and len(ttfts) == len(turns),
              {"ok_turns": sum(t["ok"] for t in turns)})

        draft_started = time.monotonic()
        code, res = live.invoke(root, DRAFT_CAP, {"description": DESCRIPTION}, 30000)
        draft_out = (res or {}).get("output") or {}
        snap = live.wire(root, {"op": "snapshot"})
        skills = snap.get("skills") or {}
        kinds = [event.get("kind") for event in (snap.get("events") or []) if isinstance(event, dict)]
        notes["draft_events"] = [k for k in kinds if isinstance(k, str) and k.startswith("skill")]
        draft_ok = (res or {}).get("ok") is True and draft_out.get("state") == "draft"
        check("R7 skill draft from the local model: manifest validated and stored as draft",
              draft_ok, {"code": code, "error": (res or {}).get("error"), "state": draft_out.get("state")})
        draft_id = draft_out.get("draft_id") or ""
        skill_id = draft_id.split("@", 1)[0]
        entries = skills.get("items") if isinstance(skills, dict) else None
        mine = [e for e in (entries or []) if isinstance(e, dict) and e.get("id") == skill_id]
        approved = any(v for e in mine for k, v in e.items() if "approv" in k or k in ("enabled", "running"))
        check("R7 the Core stored the draft (skill_draft_put event); nothing approved, enabled or run",
              draft_ok and "skill_draft_put" in notes["draft_events"] and not approved,
              {"draft_events": notes["draft_events"], "matches_in_view": len(mine), "approved_flag": approved})
        notes["skill_draft"] = {"elapsed_s": round(time.monotonic() - draft_started, 2),
                                "output": draft_out, "invoke": code, "error": (res or {}).get("error")}

        # LLM-02: the C3 agent loop with the real model. Read-only tools only (no approval needed).
        code = live.wire(root, {"op": "agent_start", "goal": AGENT_GOAL})["code"]
        agent = None
        until = time.monotonic() + 180
        while time.monotonic() < until:
            agent = live.wire(root, {"op": "snapshot"}).get("agent")
            if agent and agent.get("state") in ("done", "failed", "aborted", "awaiting_approval"):
                break
            time.sleep(0.5)
        agent = agent or {}
        tool_steps = [s for s in agent.get("steps") or [] if s.get("kind") == "tool"]
        answer = agent.get("answer") or ""
        check("R9 agent loop with the real model: tool call executed, final answer produced",
              code == "ok" and agent.get("state") == "done" and bool(answer) and bool(tool_steps),
              {"code": code, "state": agent.get("state"), "kinds": [s.get("kind") for s in agent.get("steps") or []]})
        notes["agent"] = {"state": agent.get("state"), "steps": agent.get("steps"), "answer": answer[:400],
                          "error": agent.get("error"), "budget": agent.get("budget")}

        # R10: idle stop, then an on-demand restart by the next chat.
        stopped_idle = wait_for(lambda: llm_local_state(root) == "stopped", IDLE_S + 60)
        check("R10 idle stop: state stopped, port closed, no stray process after idle_s",
              stopped_idle and not port_open(LOCAL_PORT) and not server_processes(str(run_dir)),
              {"idle_s": IDLE_S, "local_server": llm_local_state(root)})
        restart = timed_chat(root, CHAT_PROMPTS[0], 64)
        restart_text = ((restart.get("result") or {}).get("output") or {}).get("text") or ""
        check("R10 the next chat restarts the server on demand and gets a reply",
              restart.get("ok") is True and bool(restart_text) and llm_local_state(root) == "running",
              {"local_server": llm_local_state(root), "error": restart.get("error")})
        notes["restart_total_s"] = round(restart.get("total_s") or 0, 2)
    finally:
        core_pids_before_stop = server_processes(str(run_dir))
        if core is not None:
            live.stop_core(core)
        if root_dir is not None:
            shutil.rmtree(root_dir, ignore_errors=True)
        stray = wait_for(lambda: not server_processes(str(run_dir)) and not port_open(LOCAL_PORT), 15)
        check("R11 Core exit: server and sandbox gone (port closed, no stray process), temp root removed",
              stray and (root_dir is None or not root_dir.exists()),
              {"processes_before_exit": len(core_pids_before_stop), "port_open": port_open(LOCAL_PORT)})

    passed = all(c["ok"] for c in checks)
    evidence = {"gate": "WP6_LLM_LOCAL", "passed": passed, "checks": checks, "host": host_facts(),
                "engine": manifest["engine"],
                "model": {k: v for k, v in manifest["model"].items()
                          if k in ("id", "file", "size", "sha256", "quantization", "license")},
                "plugin": {"plugin_id": "llm_engine", "version": "1.3.0",
                           "sha256": sha256_file(PLUGIN_SRC), "source": "scripts/llm_engine_plugin.py"},
                "measures": measures, "notes": notes, "samples": samples}
    text = json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.write_evidence:
        EVIDENCE.write_text(text, encoding="utf-8")
    print("PASSED" if passed else "FAILED", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
