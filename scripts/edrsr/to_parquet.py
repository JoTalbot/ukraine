"""Convert normalized JSONL records to Parquet when pyarrow is installed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def convert(input_path: str, output_path: str) -> int:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("pyarrow is required: python -m pip install pyarrow") from exc

    rows = []
    with Path(input_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    table = pa.Table.from_pylist(rows)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output_path, compression="zstd")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    print(f"converted={convert(args.input, args.output)}")
