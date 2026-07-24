"""Pytest runner that strips the interfering Hermes venv from sys.path."""
import sys
import subprocess
from pathlib import Path

# Remove Hermes paths injected before the project .venv
sys.path = [p for p in sys.path if "hermes-agent" not in p]

root = Path(r"E:\AgenticOsHybrid")
cmd = [
    sys.executable,
    "-m",
    "pytest",
    *sys.argv[1:],
]

result = subprocess.run(cmd, cwd=str(root), capture_output=False)
sys.exit(result.returncode)
