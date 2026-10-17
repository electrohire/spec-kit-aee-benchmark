"""Synthetic teaching thresholds; not a validated maintenance or safety system."""
import argparse
import csv
import json
import math
import os
import sys
import tempfile
from pathlib import Path


def transform(source):
    assets = {}
    required = {"asset_id", "vibration_mm_s", "temperature_c"}
    with Path(source).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or set(reader.fieldnames) != required or len(reader.fieldnames) != 3:
            raise ValueError("CSV requires exactly asset_id,vibration_mm_s,temperature_c")
        for line, row in enumerate(reader, 2):
            if None in row or any(v is None or not v.strip() for v in row.values()):
                raise ValueError(f"line {line}: missing or extra fields")
            asset = row["asset_id"].strip()
            if asset in assets:
                raise ValueError(f"line {line}: duplicate asset ID {asset!r}")
            try:
                vibration, temperature = float(row["vibration_mm_s"]), float(row["temperature_c"])
            except ValueError as e:
                raise ValueError(f"line {line}: measurements must be numeric") from e
            if not math.isfinite(vibration) or not math.isfinite(temperature):
                raise ValueError(f"line {line}: measurements must be finite")
            if vibration < 0:
                raise ValueError(f"line {line}: vibration must be nonnegative")
            reasons = []
            if vibration >= 7.1:
                reasons.append("vibration_mm_s >= 7.1")
            if temperature >= 80:
                reasons.append("temperature_c >= 80")
            assets[asset] = dict(asset_id=asset, flagged=bool(reasons), reasons=reasons)
    return [assets[k] for k in sorted(assets)]


def run(source, target):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve() or (target.exists() and os.path.samefile(source, target)):
        raise ValueError("input and output must be different files")
    result = transform(source)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, delete=False) as f:
            temporary = f.name
            json.dump(result, f, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.input, args.output)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0
