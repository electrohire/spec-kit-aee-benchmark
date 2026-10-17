"""Render the prominent historical table from committed measured artifacts."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- historical-results:start -->"
END = "<!-- historical-results:end -->"


def table():
    rows = json.loads((ROOT/"reports/local/gpu-20260917/repair/summary.json").read_text())
    long = json.loads((ROOT/"reports/local/long-horizon-03/summary.json").read_text())
    text = "\n\n| Historical local run | Agent alone | Spec Kit (adapted) | Spec Kit + AEE (adapted) |\n|---|---:|---:|---:|\n"
    text += "| Six-task primary passes | " + " | ".join(f"{v['original_passed']}/{v['attempts']}" for v in rows) + " |\n"
    text += "| After same-test repairs | " + " | ".join(f"{v['final_passed']}/{v['attempts']}" for v in rows) + " |\n"
    text += "| Tokens including repairs | " + " | ".join(f"{v['cumulative_total_tokens']:,}" for v in rows) + " |\n"
    text += "| Tokens per repaired-suite pass | " + " | ".join(f"{v['cumulative_tokens_per_correct_answer']:,.2f}" for v in rows) + " |\n"
    arms = [long["arms"][a] for a in ("baseline", "spec_kit", "spec_kit_aee")]
    text += "| TinyDB hidden milestones accepted | " + " | ".join(f"{v['hidden_final_passes']}/3" for v in arms) + " |\n"
    text += "| TinyDB tokens, lower bound | " + " | ".join(f"≥{v['known_total_tokens']:,}" for v in arms) + " |\n"
    text += "| TinyDB unknown token calls | " + " | ".join(str(v['unknown_calls']) for v in arms) + " |\n\n"
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    path = ROOT/"README.md"
    text = path.read_text(encoding="utf-8")
    before, rest = text.split(START)
    _, after = rest.split(END)
    updated = before + START + table() + END + after
    if args.check:
        if updated != text:
            raise SystemExit("README results differ from measured artifacts")
        print("README results match committed measurements")
    else:
        path.write_text(updated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
