import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "patch_kaggle_notebooks", ROOT / "scripts" / "patch_kaggle_notebooks.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _patch(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(
        json.dumps({
            "cells": [{"cell_type": "code", "source": source.splitlines(keepends=True)}],
            "nbformat": 4,
            "nbformat_minor": 4,
        }),
        encoding="utf-8",
    )
    assert m.patch_notebook(path) is True
    return "".join(json.loads(path.read_text(encoding="utf-8"))["cells"][0]["source"])


def test_patch_gpu_adds_runtime_and_artifact_guards(tmp_path):
    source = (
        "!pip -q install tokenizers pyarrow huggingface_hub\n"
        "print('training exit code:', result.returncode)\n"
        "# Очистка тяжёлых промежуточных файлов (output кернела = /kaggle/working)\n"
    )
    patched = _patch(tmp_path, "legal_lm_gpu.ipynb", source)
    assert "uninstall -y torchvision" in patched
    assert "raise SystemExit(result.returncode)" in patched
    assert "model/model.pt" in patched
    assert "model/metrics.jsonl" in patched


def test_patch_finetune_adds_runtime_and_artifact_guards(tmp_path):
    source = (
        "!pip -q install tokenizers pyarrow peft striprtf\n"
        "print('FT exit code:', r.returncode)\n"
        "# Публикация в HF Hub (если в Kaggle добавлен секрет HF_TOKEN)\n"
        "from pathlib import Path\n"
        "required = [Path('model-ft/final'), Path('model-ft/metrics.jsonl'), Path('model-ft/samples.txt')]\n"
        "if missing:\n"
        "    raise RuntimeError('fine-tuning produced incomplete artifacts')\n"
        "if token and os.path.isdir('model-ft/final'):\n"
        "    api.upload_folder(folder_path='model-ft/final', repo_id=HF_MODEL_REPO, repo_type='model')\n"
    )
    patched = _patch(tmp_path, "legal_lm_finetune.ipynb", source)
    assert "subprocess.run(['pip', 'uninstall', '-y', 'torch', 'torchvision', 'torchaudio'], check=True)" in patched
    assert "subprocess.run(['pip', '-q', 'uninstall', '-y', 'torchvision'], check=False)" in patched
    assert "torch==2.5.1" in patched
    assert "torchvision==0.20.1" not in patched
    assert "--index-url', 'https://download.pytorch.org/whl/cu118'" in patched
    assert "transformers==4.57.1" in patched
    assert "peft==0.17.1" in patched
    assert "raise SystemExit(r.returncode)" in patched
    assert "model-ft/metrics.jsonl" in patched
    assert "fine-tuning produced incomplete artifacts" in patched
    assert "# HF publication failure is non-fatal" in patched
    assert "try:\nif token" not in patched
    assert "try:\n    if token and os.path.isdir('model-ft/final'):" in patched


def test_patch_repairs_existing_pinned_p100_install(tmp_path):
    source = (
        "!pip -q install tokenizers pyarrow peft striprtf\n"
        "import subprocess\n"
        "subprocess.run(['pip', 'uninstall', '-y', 'torch', 'torchvision', 'torchaudio'], check=True)\n"
        "subprocess.run(['pip', '-q', 'install', 'torch==2.5.1', 'torchvision==0.20.1', 'torchaudio==2.5.1', '--index-url', 'https://download.pytorch.org/whl/cu118'], check=True)\n"
        "subprocess.run(['pip', '-q', 'install', 'tokenizers', 'pyarrow', 'striprtf', 'transformers==4.57.1', 'peft==0.17.1'], check=True)\n"
    )
    patched = _patch(tmp_path, "legal_lm_finetune.ipynb", source)
    assert "torchvision==0.20.1" not in patched
    assert "uninstall', '-y', 'torchvision'" in patched


def test_patch_is_strict_when_not_applicable(tmp_path):
    path = tmp_path / "kernel.ipynb"
    path.write_text(json.dumps({"cells": []}), encoding="utf-8")
    try:
        m.patch_notebook(path)
    except SystemExit as exc:
        assert "no applicable patch" in str(exc)
    else:
        raise AssertionError("expected SystemExit for an unrecognized notebook")
