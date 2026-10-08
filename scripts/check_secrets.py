"""Scan tracked and source files only; never reads private environment/key directories."""

from pathlib import Path
import re
import sys

roots = [Path("backend"), Path("frontend/src"), Path("config"), Path("scripts"), Path("docs")]
paths = [p for root in roots for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
paths += [Path("README.md"), Path(".env.example"), Path("AGENTS.md")]
patterns = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r'(?:api[-_]?key|private[-_]?key|seed[-_]?phrase)\s*[=:]\s*["\x27]?[A-Za-z0-9_-]{24,}', re.I),
]
failures = []
for path in paths:
    content = path.read_text(errors="ignore")
    for i, line in enumerate(content.splitlines(), 1):
        if any(p.search(line) for p in patterns):
            failures.append(f"{path}:{i}: possible secret (content suppressed)")
if failures:
    print("\n".join(failures))
    sys.exit(1)
print(f"Basic secret scan passed ({len(paths)} source/document files).")
