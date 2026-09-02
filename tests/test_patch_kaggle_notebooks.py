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
        "if token and os.path.isdir('model-ft/final'):\n"
    )
    patched = _patch(tmp_path, "legal_lm_finetune.ipynb", source)
    assert "subprocess.run(['pip', 'uninstall', '-y', 'torchvision'], check=True)" in patched
    assert "subprocess.run(['pip', '-q', 'install'" in patched
    assert "transformers==4.57.1" in patched
    assert "peft==0.17.1" in patched
    assert "raise SystemExit(r.returncode)" in patched
    assert "model-ft/metrics.jsonl" in patched
    assert "fine-tuning produced incomplete artifacts" in patched


def test_patch_is_strict_when_not_applicable(tmp_path):
    path = tmp_path / "kernel.ipynb"
    path.write_text(json.dumps({"cells": []}), encoding="utf-8")
    try:
        m.patch_notebook(path)
    except SystemExit as exc:
        assert "no applicable patch" in str(exc)
    else:
        raise AssertionError("expected SystemExit for an unrecognized notebook")
