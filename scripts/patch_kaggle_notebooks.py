#!/usr/bin/env python3
"""Patch Kaggle text-only training notebooks for known runtime conflicts."""
from __future__ import annotations

import json
from pathlib import Path


def patch_notebook(path: Path) -> bool:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        text = "".join(cell.get("source", []))
        marker = "!pip -q install tokenizers pyarrow peft striprtf\n"
        if marker not in text:
            continue
        text = text.replace(marker, marker + "!pip -q uninstall -y torchvision || true\n", 1)
        cell["source"] = text.splitlines(keepends=True)
        changed = True
    if not changed:
        raise SystemExit(f"no known installation cell found in {path}")
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


if __name__ == "__main__":
    for name in ("legal_lm_gpu.ipynb", "legal_lm_finetune.ipynb"):
        path = Path("training/kaggle") / name
        if path.is_file():
            patch_notebook(path)
            print("patched", path)
