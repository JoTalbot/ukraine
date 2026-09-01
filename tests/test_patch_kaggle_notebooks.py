import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "patch_kaggle_notebooks", ROOT / "scripts" / "patch_kaggle_notebooks.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_patch_notebook_adds_runtime_guards(tmp_path):
    path = tmp_path / "legal_lm_gpu.ipynb"
    source = [
        "!pip -q install tokenizers pyarrow huggingface_hub\n",
        "print('training exit code:', result.returncode)\n",
        "# Очистка тяжёлых промежуточных файлов (output кернела = /kaggle/working)\n",
    ]
    path.write_text(json.dumps({"cells": [{"cell_type": "code", "source": source}], "nbformat": 4, "nbformat_minor": 4}), encoding="utf-8")
    assert m.patch_notebook(path) is True
    notebook = json.loads(path.read_text(encoding="utf-8"))
    patched = "".join(notebook["cells"][0]["source"])
    assert "uninstall -y torchvision" in patched
    assert "raise SystemExit(result.returncode)" in patched
    assert "training produced incomplete artifacts" in patched


def test_patch_notebook_fails_when_marker_missing(tmp_path):
    path = tmp_path / "legal_lm_gpu.ipynb"
    path.write_text(json.dumps({"cells": []}), encoding="utf-8")
    try:
        m.patch_notebook(path)
    except SystemExit as exc:
        assert "no applicable patch found" in str(exc)
    else:
        raise AssertionError("expected SystemExit for an unrecognized notebook")


def test_patch_finetune_adds_exit_guard(tmp_path):
    path = tmp_path / "legal_lm_finetune.ipynb"
    source = [
        "!pip -q install tokenizers pyarrow peft striprtf\n",
        "print('FT exit code:', r.returncode)\n",
        "# Публикация в HF Hub (если в Kaggle добавлен секрет HF_TOKEN)\n",
    ]
    path.write_text(json.dumps({"cells": [{"cell_type": "code", "source": source}], "nbformat": 4, "nbformat_minor": 4}), encoding="utf-8")
    assert m.patch_notebook(path) is True
    patched = "".join(json.loads(path.read_text(encoding="utf-8"))["cells"][0]["source"])
    assert "raise SystemExit(r.returncode)" in patched
    assert "fine-tuning produced incomplete artifacts" in patched
