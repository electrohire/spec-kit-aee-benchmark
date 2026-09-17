"""Verify every committed content-addressed offline object after checkout."""
from pathlib import Path
import json
from benchmark_runner.store import sha

objects = list(Path("reports/offline").glob("*/objects/*/*"))
objects += list(Path("reports/local").glob("**/objects/*/*"))
for path in objects:
    if sha(path.read_bytes()) != path.name:
        raise SystemExit(f"Evidence checksum mismatch: {path}")
manifests = list(Path('reports/local').glob('**/files-sha256.json'))
for manifest in manifests:
    for name, expected in json.loads(manifest.read_text(encoding='utf-8')).items():
        path = manifest.parent/name
        if sha(path.read_bytes()) != expected:
            raise SystemExit(f'Evidence manifest mismatch: {path}')
print(f"Verified {len(objects)} immutable evidence objects and {len(manifests)} file manifests")
