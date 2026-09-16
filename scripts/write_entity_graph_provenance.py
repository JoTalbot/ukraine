"""Create a deterministic provenance manifest for an entity-graph build.

The manifest binds local graph inputs to their source URLs, byte sizes and
SHA-256 digests.  It is intentionally independent from the graph builder so
provenance failures cannot silently alter graph semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_source(value: str) -> tuple[str, Path]:
    """Parse ``URL=PATH`` command-line entries."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("source must be URL=PATH")
    url, raw_path = value.split("=", 1)
    if not url or not raw_path:
        raise argparse.ArgumentTypeError("source must be URL=PATH")
    return url, Path(raw_path)


def read_sources_file(path: Path) -> list[tuple[str, Path]]:
    """Read newline-delimited ``URL=PATH`` entries emitted by a workflow."""
    sources: list[tuple[str, Path]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        try:
            sources.append(parse_source(value))
        except argparse.ArgumentTypeError as exc:
            raise ValueError(f"invalid provenance source at {path}:{line_no}: {exc}") from exc
    return sources


def build_manifest(root: Path, sources: Iterable[tuple[str, Path]], metadata: dict) -> dict:
    inputs = []
    seen_paths: set[str] = set()
    for url, relative in sorted(sources, key=lambda item: item[1].as_posix()):
        key = relative.as_posix()
        if key in seen_paths:
            raise ValueError(f"duplicate provenance input path: {key}")
        seen_paths.add(key)
        path = (root / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"provenance input is missing: {relative}")
        stat = path.stat()
        inputs.append({
            "path": key,
            "source_url": url,
            "bytes": stat.st_size,
            "sha256": sha256(path),
        })

    if not inputs:
        raise ValueError("provenance manifest must contain at least one input")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "inputs": inputs,
        "build": metadata,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="graph_provenance.json")
    parser.add_argument("--source", action="append", default=[], type=parse_source,
                        help="source URL and local path as URL=PATH")
    parser.add_argument("--sources-file", help="newline-delimited URL=PATH entries")
    parser.add_argument("--years", default="2024,2025,2026")
    parser.add_argument("--parts-per-year", type=int, default=4)
    parser.add_argument("--workflow-script", default=".github/workflows/entity-graph.yml")
    args = parser.parse_args()

    if args.parts_per_year < 1:
        parser.error("--parts-per-year must be positive")

    sources = list(args.source)
    if args.sources_file:
        sources.extend(read_sources_file(Path(args.sources_file)))
    if not sources:
        parser.error("at least one --source or --sources-file is required")

    root = Path(args.root).resolve()
    metadata = {
        "years": [year for year in args.years.split(",") if year],
        "parts_per_year": args.parts_per_year,
        "workflow_script": args.workflow_script,
    }
    manifest = build_manifest(root, sources, metadata)
    output = root / args.output
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
