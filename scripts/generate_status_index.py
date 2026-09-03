"""Backward-compatible entry point for the canonical status-index generator."""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.aggregate_status_signals import build_status_index


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
    import json
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status index written: {output}")


__all__ = ["build_status_index"]

if __name__ == "__main__":
    main()
