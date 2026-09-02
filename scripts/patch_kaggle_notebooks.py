#!/usr/bin/env python3
"""Patch Kaggle training notebooks for known runtime conflicts and fail-fast checks."""
from __future__ import annotations

import json
from pathlib import Path


INSTALL_MARKERS = {
    "legal_lm_gpu.ipynb": "!pip -q install tokenizers pyarrow huggingface_hub\n",
    "legal_lm_finetune.ipynb": "!pip -q install tokenizers pyarrow peft striprtf\n",
}

# Kaggle's preinstalled transformers/peft stack can drift independently.  The
# FT notebook imports PEFT before training, so keep a known-compatible pair and
# remove torchvision, which can break transformers' lazy vision imports on the
# Kaggle torch build.  Use subprocess with check=True because an IPython `!pip`
# failure can otherwise leave the cell running with the broken package intact.
FT_INSTALL = (
    "import subprocess\n"
    "subprocess.run(['pip', 'uninstall', '-y', 'torchvision'], check=True)\n"
    "subprocess.run(['pip', '-q', 'install', 'tokenizers', 'pyarrow', 'striprtf', "
    "'transformers==4.57.1', 'peft==0.17.1'], check=True)\n"
)


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _ensure_ft_dependencies(text: str, marker: str, name: str) -> str:
    if name != "legal_lm_finetune.ipynb" or marker not in text:
        return text
    if "transformers==4.57.1" in text and "peft==0.17.1" in text and "uninstall -y torchvision" in text:
        return text
    return text.replace(marker, FT_INSTALL, 1)


def _ensure_torchvision_removed(text: str, marker: str) -> str:
    """Keep GPU notebook safe from a broken preinstalled torchvision."""
    if "pip" not in text or marker not in text:
        return text
    if "pip -q uninstall -y torchvision" in text or "pip uninstall -y torchvision" in text:
        return text
    replacement = "!pip -q uninstall -y torchvision\n" + marker
    return text.replace(marker, replacement, 1)


def patch_notebook(path: Path) -> bool:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    name = path.name

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        original = "".join(cell.get("source", []))
        text = original

        marker = INSTALL_MARKERS.get(name)
        if marker:
            text = _ensure_ft_dependencies(text, marker, name)
            if name != "legal_lm_finetune.ipynb":
                text = _ensure_torchvision_removed(text, marker)

        if "print('training exit code:', result.returncode)" in text and "raise SystemExit(result.returncode)" not in text:
            needle = "print('training exit code:', result.returncode)\n"
            text = text.replace(needle, needle + "if result.returncode != 0:\n    raise SystemExit(result.returncode)\n", 1)

        if "print('FT exit code:', r.returncode)" in text and "raise SystemExit(r.returncode)" not in text:
            needle = "print('FT exit code:', r.returncode)\n"
            text = text.replace(needle, needle + "if r.returncode != 0:\n    raise SystemExit(r.returncode)\n", 1)

        if "# Очистка тяжёлых промежуточных файлов" in text and "training produced incomplete artifacts" not in text:
            needle = "# Очистка тяжёлых промежуточных файлов (output кернела = /kaggle/working)\n"
            guard = (
                needle
                + "from pathlib import Path\n"
                + "required = [Path('model/model.pt'), Path('model/tokenizer.json'), Path('model/metrics.jsonl'), Path('model/samples.txt')]\n"
                + "missing = [str(p) for p in required if not p.is_file()]\n"
                + "if missing:\n"
                + "    raise RuntimeError('training produced incomplete artifacts: ' + ', '.join(missing))\n"
            )
            if needle in text:
                text = text.replace(needle, guard, 1)

        publish_marker = "# Публикация в HF Hub (если в Kaggle добавлен секрет HF_TOKEN)\n"
        if publish_marker in text and "fine-tuning produced incomplete artifacts" not in text:
            guard = (
                publish_marker
                + "from pathlib import Path\n"
                + "required = [Path('model-ft/final'), Path('model-ft/metrics.jsonl'), Path('model-ft/samples.txt')]\n"
                + "missing = [str(p) for p in required if not p.exists()]\n"
                + "if missing:\n"
                + "    raise RuntimeError('fine-tuning produced incomplete artifacts: ' + ', '.join(missing))\n"
            )
            text = text.replace(publish_marker, guard, 1)

        if text != original:
            cell["source"] = _lines(text)
            changed = True

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
