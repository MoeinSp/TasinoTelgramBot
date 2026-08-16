"""Check migration graphs without full Django setup."""
from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_app_migrations(mig_dir: Path) -> dict[str, list[tuple[str, str]]]:
    nodes: dict[str, list[tuple[str, str]]] = {}
    for f in sorted(mig_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        name = f.stem
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        deps: list[tuple[str, str]] = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name != "Migration":
                continue
            for item in node.body:
                if not isinstance(item, ast.Assign):
                    continue
                for t in item.targets:
                    if isinstance(t, ast.Name) and t.id == "dependencies":
                        raw = ast.literal_eval(item.value)
                        for d in raw:
                            if isinstance(d, (list, tuple)) and len(d) == 2:
                                deps.append((str(d[0]), str(d[1])))
        nodes[name] = deps
    return nodes


def main() -> int:
    bad = 0
    for mig_dir in sorted(ROOT.glob("*/migrations")):
        app = mig_dir.parent.name
        nodes = load_app_migrations(mig_dir)
        if not nodes:
            continue
        depended_on: set[str] = set()
        missing: list[tuple[str, str]] = []
        for name, deps in nodes.items():
            for dapp, dname in deps:
                if dapp == app:
                    depended_on.add(dname)
                    if dname not in nodes:
                        missing.append((name, dname))
        leaves = sorted(set(nodes) - depended_on)
        nums: dict[str, list[str]] = defaultdict(list)
        for n in nodes:
            m = re.match(r"^(\d+)_", n)
            if m:
                nums[m.group(1)].append(n)
        dups = {k: v for k, v in nums.items() if len(v) > 1}

        print(f"=== {app}: {len(nodes)} migrations")
        print(f"    leaves: {leaves}")
        if dups:
            print(f"    WARN dup numbers (ok if merged): {dict(dups)}")
        if len(leaves) > 1:
            print("    CONFLICT: multiple leaf nodes")
            bad += 1
        elif missing:
            pass
        if missing:
            print(f"    MISSING deps: {missing}")
            bad += 1
    return bad


if __name__ == "__main__":
    sys.exit(main())
