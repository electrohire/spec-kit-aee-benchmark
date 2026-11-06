#!/usr/bin/env python3
"""Ship the Cycle 5 git bundle (a8df781a..loop/cycle5-drafting-reserve)
to the desktop via one relay command, verify sha256 there, and fetch
the branch into the desktop benchmark-c3r1 tree."""
import base64
import hashlib
import subprocess
import sys
from pathlib import Path

BUNDLE = Path("/tmp/c5.bundle")
data = BUNDLE.read_bytes()
SHA = hashlib.sha256(data).hexdigest()
b64 = base64.b64encode(data).decode()
remote = (
    f"printf %s '{b64}' | base64 -d > /tmp/c5.bundle && "
    f"echo '{SHA}  /tmp/c5.bundle' | sha256sum -c - && "
    "cd ~/needle-campaign/code/benchmark-c3r1 && "
    "git fetch /tmp/c5.bundle loop/cycle5-drafting-reserve:loop/cycle5-drafting-reserve && "
    "git log --oneline -2 loop/cycle5-drafting-reserve && echo BUNDLE_C5_OK"
)
proc = subprocess.run(
    [str(Path.home() / "workspace/desktop-relay/muse-relay.sh"),
     "--channel", "c5work", "run", "--timeout", "180", "--", remote],
    capture_output=True, text=True)
print(proc.stdout)
print(proc.stderr, file=sys.stderr)
print("BUNDLE_SHA256", SHA, "bytes", len(data))
sys.exit(proc.returncode)
