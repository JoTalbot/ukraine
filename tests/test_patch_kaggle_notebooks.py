import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "patch_kaggle_notebooks", ROOT / "scripts" / "patch_kaggle_notebooks.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_patch_notebook_adds_torchvision_removal(tmp_path):
    path = tmp_path / "kernel.ipynb"
    path.write_text(
        json.dumps({
            "cells": [{
                "cell_type": "code",
                "source": ["!pip -q install tokenizers pyarrow peft striprtf\n"],
            }],
            "nbformat": 4,
            "nbformat_minor": 4,
        }),
        encoding="utf-8",
    )
    assert m.patch_notebook(path) is True
    notebook = json.loads(path.read_text(encoding="utf-8"))
    source = "".join(notebook["cells"][0]["source"])
    assert "uninstall -y torchvision" in source


def test_patch_notebook_fails_when_marker_missing(tmp_path):
    path = tmp_path / "kernel.ipynb"
    path.write_text(json.dumps({"cells": []}), encoding="utf-8")
    try:
        m.patch_notebook(path)
    except SystemExit as exc:
        assert "no known installation cell" in str(exc)
    else:
        raise AssertionError("expected SystemExit for an unrecognized notebook")
