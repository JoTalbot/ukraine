#!/usr/bin/env python3
"""Patch Kaggle training notebooks for known runtime conflicts and fail-fast checks."""
from __future__ import annotations

import json
from pathlib import Path


INSTALL_MARKERS = {
    "legal_lm_gpu.ipynb": "!pip -q install tokenizers pyarrow huggingface_hub\n",
    "legal_lm_finetune.ipynb": "!pip -q install tokenizers pyarrow peft striprtf\n",
}


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def patch_notebook(path: Path) -> bool:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    name = path.name

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        text = "".join(cell.get("source", []))

        # Known transformers/torchvision conflict on older Kaggle Pascal images.
        marker = INSTALL_MARKERS.get(name)
        if marker and marker in text and "uninstall -y torchvision" not in text:
            text = text.replace(marker, marker + "!pip -q uninstall -y torchvision || true\n", 1)
            changed = True

        # Never allow a failed subprocess training run to look like a successful notebook.
        if "print('training exit code:', result.returncode)" in text and "raise SystemExit(result.returncode)" not in text:
            needle = "print('training exit code:', result.returncode)\n"
            replacement = needle + "if result.returncode != 0:\n    raise SystemExit(result.returncode)\n"
            text = text.replace(needle, replacement, 1)
            changed = True

        if "print('FT exit code:', r.returncode)" in text and "raise SystemExit(r.returncode)" not in text:
            needle = "print('FT exit code:', r.returncode)\n"
            replacement = needle + "if r.returncode != 0:\n    raise SystemExit(r.returncode)\n"
            text = text.replace(needle, replacement, 1)
            changed = True

        # The result collector relies on these files. Fail before cleanup if they are absent.
        if "# Очистка тяжёлых промежуточных файлов" in text and "metrics.jsonl" not in text:
            needle = "# Очистка тяжёлых промежуточных файлов (output кернела = /kaggle/working)\n"
            replacement = (
                needle
                + "from pathlib import Path\n"
                + "required = [Path('model/model.pt'), Path('model/tokenizer.json'), Path('model/metrics.jsonl'), Path('model/samples.txt')]\n"
                + "missing = [str(p) for p in required if not p.is_file()]\n"
                + "if missing:\n"
                + "    raise RuntimeError('training produced incomplete artifacts: ' + ', '.join(missing))\n"
            )
            text = text.replace(needle, replacement, 1)
            changed = True

        if "# Публикация в HF Hub (если в Kaggle добавлен секрет HF_TOKEN)" in text and "model-ft/final" in text:
            needle = "# Публикация в HF Hub (если в Kaggle добавлен секрет HF_TOKEN)\n"
            if "model-ft/metrics.jsonl" not in text.split(needle, 1)[0]:
                replacement = (
                    needle
                    + "from pathlib import Path\n"
                    + "required = [Path('model-ft/final'), Path('model-ft/metrics.jsonl'), Path('model-ft/samples.txt')]\n"
                    + "missing = [str(p) for p in required if not p.exists()]\n"
                    + "if missing:\n"
                    + "    raise RuntimeError('fine-tuning produced incomplete artifacts: ' + ', '.join(missing))\n"
                )
                text = text.replace(needle, replacement, 1)
                changed = True

        if text != "".join(cell.get("source", [])):
            cell["source"] = _lines(text)

    if not changed:
        raise SystemExit(f"no applicable patch found in {path}")
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


if __name__ == "__main__":
    for name in INSTALL_MARKERS:
        path = Path("training/kaggle") / name
        if path.is_file():
            patch_notebook(path)
            print("patched", path)
