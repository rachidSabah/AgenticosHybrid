"""Verify all Python files parse cleanly."""

import ast, os, sys

errors = []
total = 0
skip_dirs = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".mypy_cache",
}

for root, dirs, files in os.walk("."):
    root_parts = set(root.replace(os.sep, "/").split("/"))
    if root_parts & skip_dirs:
        continue
    for f in files:
        if f.endswith(".py"):
            total += 1
            p = os.path.join(root, f)
            try:
                with open(p, encoding="utf-8") as fh:
                    ast.parse(fh.read())
            except SyntaxError as e:
                errors.append((p, str(e)))

print(f"Total .py files: {total}")
print(f"Syntax errors: {len(errors)}")
for p, e in errors:
    print(f"  FAIL: {p} -> {e}")

sys.exit(1 if errors else 0)
