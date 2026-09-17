"""Verify every committed content-addressed offline object after checkout."""
from pathlib import Path
from benchmark_runner.store import sha

objects = list(Path("reports/offline").glob("*/objects/*/*"))
for path in objects:
    if sha(path.read_bytes()) != path.name:
        raise SystemExit(f"Evidence checksum mismatch: {path}")
print(f"Verified {len(objects)} immutable offline evidence objects")
