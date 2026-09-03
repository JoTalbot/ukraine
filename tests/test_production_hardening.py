import json
from pathlib import Path

import pytest

from scripts.production_hardening import compat, drift, promote, registry


def write(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_drift_green_and_red(tmp_path):
    base = {
        "schema_version": 1,
        "schema_hash": "s",
        "row_count": 100,
        "field_distributions": {"a": {"x": 1}},
        "source_available": True,
    }
    write(tmp_path / "b.json", base)
    write(tmp_path / "c.json", base)
    assert drift(tmp_path / "b.json", tmp_path / "c.json", tmp_path / "r.json") == 0
    bad = dict(base)
    bad["row_count"] = 140
    write(tmp_path / "c.json", bad)
    assert drift(tmp_path / "b.json", tmp_path / "c.json", tmp_path / "r.json") == 1


def test_registry_is_immutable(tmp_path):
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    output = tmp_path / "registry.json"
    assert registry(model, "m1", "d1", "s1", output) == 0
    assert registry(model, "m1", "d1", "s1", output) == 0
    with pytest.raises(SystemExit):
        registry(model, "m1", "d2", "s1", output)


def test_compatibility(tmp_path):
    model_meta = tmp_path / "m.json"
    dataset_meta = tmp_path / "d.json"
    result = tmp_path / "r.json"
    write(model_meta, {"dataset_revision": "d1", "schema_hash": "s1"})
    write(dataset_meta, {"revision": "d1", "schema_hash": "s1"})
    assert compat(model_meta, dataset_meta, result) == 0
    write(dataset_meta, {"revision": "d2", "schema_hash": "s1"})
    assert compat(model_meta, dataset_meta, result) == 1


def test_promotion_requires_gates(tmp_path):
    gates = tmp_path / "g.json"
    output = tmp_path / "p.json"
    write(gates, {"compatibility": "green", "evaluation": "green", "readiness": "green"})
    assert promote("dev", "validated", gates, output) == 0
    assert promote("validated", "candidate", gates, output) == 0
    assert promote("candidate", "production", gates, output) == 0
