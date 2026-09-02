from pathlib import Path

from scripts.validate_release import validate_repository_contract, validate_sha256


def test_sha256_contract() -> None:
    assert validate_sha256("0" * 64)
    assert not validate_sha256("not-a-sha256")
    assert not validate_sha256("A" * 64)


def test_required_release_docs_exist() -> None:
    assert validate_repository_contract(Path(".")) == []
