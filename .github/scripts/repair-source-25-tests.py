#!/usr/bin/env python3
from pathlib import Path
import re
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "buildsrc")
tests = root / "tests"
changed = False
for p in tests.rglob("*.py"):
    source = p.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    output = []
    file_changed = False
    for line in lines:
        updated = line
        # Version assertions must follow the incremented Android app metadata.
        if "versionCode" in updated and "24" in updated:
            updated = re.sub(r"(?<!\d)24(?!\d)", "25", updated)
        if ("versionName" in updated or "0.10.2" in updated) and "0.10.2" in updated:
            updated = updated.replace("0.10.2", "0.10.3")
        if updated != line:
            file_changed = True
        output.append(updated)
    if file_changed:
        p.write_text("".join(output), encoding="utf-8")
        print(f"Updated stale version assertions in {p.relative_to(root)}")
        changed = True
if changed:
    (root / ".source25-test-repair-changed").write_text("changed\n", encoding="utf-8")
print("Version-test repair:", "changed" if changed else "already current")
