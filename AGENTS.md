# Gideon reconstruction
Follow docs/sources and the user's instructions. One vertical line A0→A5 then S2→S5.
Never modify Gideon-Project-Old or its worktrees/caches. No imported legacy code.
Rust Core; no LLM/Model Manager in Base. No personal devices/session/network runtime.
Run fmt, check, test, clippy -D warnings, release and process regression before gate approval.
Use private isolated HOME/XDG for runtime; no push/deploy without authorization.
Commit small local checkpoints and maintain docs/AGENT_STATE.md. No human intermediate tests.

Graph navigation: use `python3 scripts/graph.py query "..." --budget 1000`, path or explain before broad source reads. Verify findings against source. Refresh after code edits with `python3 scripts/graph.py` (AST only, no LLM/network; index ignored by Git). CLI lives in target/graphify-venv; pins in scripts/requirements-graphify.txt. Never index the legacy or alter global assistant settings.
