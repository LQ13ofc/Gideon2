#!/usr/bin/env python3
"""Project-local Graphify CLI. Deterministic extraction only; no global settings."""
import os
from pathlib import Path
import subprocess
import sys

base = Path(__file__).resolve().parents[1]
home = base/'target/graphify-home'
home.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home/'config'), XDG_CACHE_HOME=str(home/'cache'), GRAPHIFY_QUERY_LOG_ENABLE='0')
for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY'):
    env.pop(key,None)
args = sys.argv[1:]
if not args: args = ['update', '.', '--no-cluster']
if args[0] not in ('update','query','path','explain','affected','--version'):
    raise SystemExit('Only deterministic local navigation commands are enabled')
if args[0]=='update' and '--no-cluster' not in args:args.append('--no-cluster')
raise SystemExit(subprocess.run([str(base/'target/graphify-venv/bin/graphify'),*args],cwd=base,env=env).returncode)
