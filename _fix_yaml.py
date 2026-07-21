"""Fix indentation issues in release.yml."""
with open(".github/workflows/release.yml", "r") as f:
    lines = f.readlines()

# Lines 185-188: @echo off block (0-indexed: 184-187)
fix_targets = ["@echo off", "echo Starting", 'start ""', "        '@"]

for i in range(184, min(188, len(lines))):
    stripped = lines[i].lstrip()
    # If the content starts with one of our targets and has 8-space indent, fix it
    current_indent = len(lines[i]) - len(stripped)
    if current_indent == 8 and any(stripped.startswith(t) for t in fix_targets):
        lines[i] = "          " + stripped

# Lines 191-193: Write-Host block
for i in range(190, min(193, len(lines))):
    stripped = lines[i].lstrip()
    current_indent = len(lines[i]) - len(stripped)
    if current_indent == 8 and (stripped.startswith("Write") or stripped.startswith("Start") or stripped.startswith("'@")):
        lines[i] = "          " + stripped

# Lines ~344-375: release manifest JSON
for i in range(343, min(400, len(lines))):
    stripped = lines[i].lstrip()
    current_indent = len(lines[i]) - len(stripped)
    if current_indent == 8 and (stripped.startswith("{") or stripped.startswith('"version"') or stripped.startswith('"releaseDate"') or stripped.startswith('"commit"') or stripped.startswith('"platforms"') or stripped.startswith('"windows"') or stripped.startswith('"os"') or stripped.startswith('"arch"') or stripped.startswith('"installers"') or stripped.startswith('}')):
        if not stripped.startswith("}") or stripped.startswith("}"):
            lines[i] = "          " + stripped

with open(".github/workflows/release.yml", "w") as f:
    f.writelines(lines)

print("Fixed release.yml indent issues")
