import json
from pathlib import Path
import pytest
from scripts.production_hardening import drift, compat, promote, registry


def write(p: Path, x): p.write_text(json.dumps(x), encoding="utf-8")


def test_drift_green_and_red(tmp_path):
    base={"schema_version":1,"schema_hash":"s","row_count":100,"field_distributions":{"a":{"x":1}},"source_available":True}
    write(tmp_path/"b.json",base); write(tmp_path/"c.json",base)
    assert drift(tmp_path/"b.json",tmp_path/"c.json",tmp_path/"r.json")==0
    bad=dict(base); bad["row_count"]=140; write(tmp_path/"c.json",bad)
    assert drift(tmp_path/"b.json",tmp_path/"c.json",tmp_path/"r.json")==1


def test_registry_is_immutable(tmp_path):
    model=tmp_path/"model.bin"; model.write_bytes(b"model")
    out=tmp_path/"registry.json"
    assert registry(model,"m1","d1","s1",out)==0
    assert registry(model,"m1","d1","s1",out)==0
    with pytest.raises(SystemExit): registry(model,"m1","d2","s1",out)


def test_compatibility(tmp_path):
    m,d,r=tmp_path/"m.json",tmp_path/"d.json",tmp_path/"r.json"
    write(m,{"dataset_revision":"d1","schema_hash":"s1"}); write(d,{"revision":"d1","schema_hash":"s1"})
    assert compat(m,d,r)==0
    write(d,{"revision":"d2","schema_hash":"s1"})
    assert compat(m,d,r)==1


def test_promotion_requires_gates(tmp_path):
    gates=tmp_path/"g.json"; out=tmp_path/"p.json"
    write(gates,{"compatibility":"green","evaluation":"green","readiness":"green"})
    assert promote("dev","validated",gates,out)==0
    assert promote("validated","candidate",gates,out)==0
    assert promote("candidate","production",gates,out)==0
