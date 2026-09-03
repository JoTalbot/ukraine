"""Backward-compatible entry point for the canonical status-index generator."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support both `python -m scripts.generate_status_index` and the CI's
# direct-file invocation (`python scripts/generate_status_index.py`).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.aggregate_status_signals import build_status_index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="artifacts/status/status-index.json")
    args = parser.parse_args()
    root = Path(args.root)
    status_dir = root / "artifacts" / "status"
    payload = build_status_index(
        status_dir / "release-manifest.json",
        status_dir / "signals",
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status index written: {output}")


__all__ = ["build_status_index"]

if __name__ == "__main__":
    main()
