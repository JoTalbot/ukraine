"""Generate a dependency SBOM from the active Python environment."""
from __future__ import annotations

import argparse
import json
import platform
import uuid
from importlib.metadata import distributions
from pathlib import Path

NAMESPACE = uuid.UUID("4b4f5c0b-0c4d-4b1e-9c16-0f1b3b5f2c6d")


def build_sbom() -> dict:
    components = []
    for dist in sorted(distributions(), key=lambda d: (d.metadata.get("Name") or "").lower()):
        name = dist.metadata.get("Name")
        version = dist.version
        if not name or not version:
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
            }
        )
    serial = f"urn:uuid:{uuid.uuid5(NAMESPACE, platform.python_version())}"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": serial,
        "version": 1,
        "metadata": {
            "tools": [{"vendor": "ukraine", "name": "generate_sbom.py"}],
            "properties": [{"name": "python.version", "value": platform.python_version()}],
        },
        "components": components,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/status/sbom.cdx.json")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_sbom(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SBOM written: {output}")


if __name__ == "__main__":
    main()
