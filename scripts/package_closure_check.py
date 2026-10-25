#!/usr/bin/env python3
"""Fail if a built package lacks a script that its own Core or workers need.

Usage: package_closure_check.py PACKAGE_DIR

1. Every `scripts/<name>.py` string embedded in bin/gideon-base must exist in PACKAGE_DIR/scripts
   (the Core resolves workers by that path at runtime).
2. Every top-level `import x` / `from x import y` in a packaged script whose module name matches a
   file of the repository's scripts/ directory must also be packaged (workers run with -I and see
   only their own directory).
Exit 0 when closed, 1 with the list of missing files otherwise.
"""
import ast
import re
import sys
from pathlib import Path


def referenced_by_core(package: Path):
    data = (package / "bin" / "gideon-base").read_bytes()
    found = set(re.findall(rb"scripts/([A-Za-z0-9_]+\.py)", data))
    return {name.decode() for name in found}


def local_imports(path: Path, repo_scripts: set):
    names = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods = [node.module.split(".")[0]]
        else:
            continue
        for mod in mods:
            if f"{mod}.py" in repo_scripts:
                names.add(f"{mod}.py")
    return names


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    package = Path(argv[1])
    repo_scripts = {p.name for p in (Path(__file__).resolve().parent).glob("*.py")}
    packaged = {p.name for p in (package / "scripts").glob("*.py")}
    missing = set()
    # Names the Core mentions only inside tests/diagnostics (not runtime) are listed here on purpose.
    optional = {"verify_e1_connections.py", "namespace_probe.py"}
    for name in referenced_by_core(package):
        if name not in packaged and name not in optional and name in repo_scripts:
            missing.add(f"{name} (referenced by gideon-base)")
    queue = sorted(packaged)
    seen = set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        for dep in local_imports(package / "scripts" / name, repo_scripts):
            if dep not in packaged:
                missing.add(f"{dep} (imported by {name})")
            elif dep not in seen:
                queue.append(dep)
    if missing:
        print("package closure FAILED, missing:")
        for item in sorted(missing):
            print("  -", item)
        return 1
    print(f"package closure OK ({len(packaged)} scripts)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
