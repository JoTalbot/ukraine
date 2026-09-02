import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_dashboard", ROOT / "scripts" / "build_dashboard.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_dashboard_builds_from_repo_files(tmp_path):
    m.build(ROOT, tmp_path)
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Ukraine Open Legal" in page
    assert "ua-legal-lm-ft" in page
    assert "ua-legal-lm-gpu" in page
    assert "ua-open-data" in page
    assert "<style>" in page
    # никаких внешних ассетов — страница полностью self-contained
    assert "https://fonts." not in page and "cdn." not in page


def test_dashboard_tolerates_missing_manifests(tmp_path):
    out = tmp_path / "out"
    m.build(tmp_path, out)  ## пустой root — страница всё равно строится
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "unknown" in page or "не найден" in page or "—" in page
