#!/usr/bin/env python3
"""Patch Kaggle training notebooks for known runtime conflicts and fail-fast checks."""
from __future__ import annotations

import json
import re
from pathlib import Path

INSTALL_MARKERS = {
    "legal_lm_gpu.ipynb": "!pip -q install tokenizers pyarrow huggingface_hub\n",
    "legal_lm_finetune.ipynb": "!pip -q install tokenizers pyarrow peft striprtf\n",
}

# Kaggle P100 is Pascal (sm_60). Keep the runtime deterministic and avoid
# installing unnecessary audio/vision wheels that consume hundreds of MB and
# can destabilize the preconfigured notebook environment.
FT_INSTALL = (
    "import subprocess\n"
    "subprocess.run(['pip', 'uninstall', '-y', 'torch', 'torchvision', 'torchaudio'], check=True)\n"
    "subprocess.run(['pip', '-q', 'install', '--no-cache-dir', 'torch==2.5.1', '--index-url', 'https://download.pytorch.org/whl/cu118'], check=True)\n"
    "subprocess.run(['pip', '-q', 'install', '--no-cache-dir', 'tokenizers', 'pyarrow', 'striprtf', 'transformers==4.57.1', 'peft==0.17.1'], check=True)\n"
    "import torch\n"
    "assert torch.cuda.is_available(), 'CUDA is unavailable after deterministic torch install'\n"
    "assert torch.cuda.get_device_capability(0)[0] < 7, 'Unexpected non-Pascal GPU for this FT runtime'\n"
    "print('FT runtime:', torch.__version__, '| GPU:', torch.cuda.get_device_name(0), '| capability:', torch.cuda.get_device_capability(0))\n"
)


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _ensure_ft_dependencies(text: str, marker: str, name: str) -> str:
    if name != "legal_lm_finetune.ipynb" or marker not in text:
        return text
    if "torch==2.5.1" in text and "transformers==4.57.1" in text and "peft==0.17.1" in text and "--no-cache-dir" in text and "torchaudio" in text:
        return text
    return text.replace(marker, FT_INSTALL, 1)


VISION_AUDIO_PINS = re.compile(r"['\"]torch(?:vision|audio)==[^'\"]*['\"],?\s*")


def _drop_vision_audio_pins(text: str) -> str:
    """Убрать пины torchvision/torchaudio из install-команд ноутбука.

    Kaggle P100 (sm_60) не должен тянуть vision/audio-колёса: предустановленный
    torchvision несовместим с пересобранным torch и роняет рантайм.
    """
    if "torchvision==" not in text and "torchaudio==" not in text:
        return text
    patched_lines = []
    for line in text.splitlines(keepends=True):
        if "install" in line and ("torchvision==" in line or "torchaudio==" in line):
            line = VISION_AUDIO_PINS.sub("", line)
        patched_lines.append(line)
    return "".join(patched_lines)


TORCHVISION_UNINSTALL = "subprocess.run(['pip', 'uninstall', '-y', 'torchvision'], check=True)\n"


def _ensure_torchvision_uninstall(text: str) -> str:
    """Гарантировать удаление предустановленного torchvision после сборки torch.

    Wheel'ы torchvision из образа Kaggle собраны под другой torch и на P100
    ломают импорт; убираем их python-командой, а не shell-префиксом ``!pip``.
    """
    if "uninstall', '-y', 'torchvision'" in text:
        return text
    anchors = (
        "subprocess.run(['pip', '-q', 'install', '--no-cache-dir', 'torch==2.5.1', '--index-url', 'https://download.pytorch.org/whl/cu118'], check=True)\n",
        "subprocess.run(['pip', 'uninstall', '-y', 'torch', 'torchvision', 'torchaudio'], check=True)\n",
    )
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + TORCHVISION_UNINSTALL, 1)
    return text


def _ensure_torchvision_removed(text: str, marker: str) -> str:
    """Keep GPU notebook safe from a broken preinstalled torchvision."""
    if "pip" not in text or marker not in text:
        return text
    if "pip -q uninstall -y torchvision" in text or "pip uninstall -y torchvision" in text:
        return text
    replacement = "!pip -q uninstall -y torchvision\n" + marker
    return text.replace(marker, replacement, 1)


def _ensure_hf_publish_is_nonfatal(text: str) -> str:
    """Do not turn a successful Kaggle training run into KernelWorkerStatus.ERROR."""
    marker = "if token and os.path.isdir('model-ft/final'):\n"
    if marker not in text or "HF publication failure is non-fatal" in text:
        return text
    prefix, publish = text.split(marker, 1)
    wrapped = [
        "# HF publication failure is non-fatal: GitHub performs the authoritative publication.\n",
        "try:\n",
        "    if token and os.path.isdir('model-ft/final'):\n",
    ]
    for line in publish.splitlines(keepends=True):
        wrapped.append("    " + line)
    wrapped.extend([
        "except Exception as exc:\n",
        "    from pathlib import Path\n",
        "    Path('model-ft/hf-publish-error.txt').write_text(str(exc), encoding='utf-8')\n",
        "    print('HF publication skipped after error:', repr(exc))\n",
    ])
    return prefix + "".join(wrapped)


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
            if name == "legal_lm_finetune.ipynb":
                text = _drop_vision_audio_pins(text)
                text = _ensure_torchvision_uninstall(text)
            else:
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

        if name == "legal_lm_finetune.ipynb":
            text = _ensure_hf_publish_is_nonfatal(text)

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

# Trigger Kaggle training after patch changes are committed.
