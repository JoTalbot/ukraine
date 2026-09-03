"""Validate a candidate model metric against the currently published baseline."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def last_val_loss(path: Path) -> float | None:
    if not path.is_file():
        return None
    values: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            value = row.get("val_loss")
            if value is not None:
                values.append(float(value))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return values[-1] if values else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--tolerance", type=float, default=1.02)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    candidate = last_val_loss(args.candidate)
    baseline = last_val_loss(args.baseline) if args.baseline else None
    if candidate is None or not math.isfinite(candidate):
        raise SystemExit("Model quality gate failed: candidate val_loss is missing or invalid")
    if baseline is not None and (not math.isfinite(baseline) or baseline <= 0):
        raise SystemExit("Model quality gate failed: published baseline val_loss is invalid")

    allowed = baseline * args.tolerance if baseline is not None else None
    passed = allowed is None or candidate <= allowed
    result = {
        "schema_version": 1,
        "candidate_val_loss": candidate,
        "baseline_val_loss": baseline,
        "tolerance": args.tolerance,
        "allowed_max_val_loss": allowed,
        "state": "green" if passed else "red",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if baseline is None:
        print(f"Model quality gate: PASS (initial publication, val_loss={candidate:.6f})")
    elif passed:
        print(
            "Model quality gate: PASS "
            f"(candidate={candidate:.6f}, baseline={baseline:.6f}, max={allowed:.6f})"
        )
    else:
        print(
            "Model quality gate: BLOCK "
            f"(candidate={candidate:.6f}, baseline={baseline:.6f}, max={allowed:.6f})"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
