#!/usr/bin/env python3
"""Generate a self-contained static dashboard (index.html) for GitHub Pages.

Reads only files already tracked in this repository plus a generated release
manifest when present. The output has inline styles and zero external assets.
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

KERNELS = [
    ("ua-legal-lm-ft", "Fine-tune Qwen2.5-0.5B (LoRA)", "https://huggingface.co/JoTalbot/ua-legal-lm-ft"),
    ("ua-legal-lm-gpu", "From-scratch ~29M GPT", "https://huggingface.co/JoTalbot/ua-legal-lm-gpu"),
]
CPU_LM = ("legal-lm", "CPU legal-LM (GitHub Actions)", "https://huggingface.co/JoTalbot/ua-legal-lm")


def esc(value) -> str:
    return html.escape(str(value))


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def read_metrics(path: Path) -> list[dict]:
    metrics = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    metrics.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return metrics


def release_row(root: Path) -> str:
    manifest = read_json(root / "artifacts" / "status" / "release-manifest.json")
    if not manifest:
        return "<tr><td colspan='4'><span class='pill mute'>нет manifest</span></td></tr>"
    commit = manifest.get("git_commit", "unknown")
    branch = manifest.get("git_branch", "unknown")
    generated = manifest.get("generated_at_utc", "unknown")
    count = len(manifest.get("files", []))
    return (
        f"<tr><td><code>{esc(commit)}</code></td><td>{esc(branch)}</td>"
        f"<td>{esc(generated)}</td><td>{esc(count)}</td></tr>"
    )


def kernel_row(root: Path, slug: str, title: str, link: str) -> str:
    directory = root / ".training-manifests" / slug
    status = read_text(directory / "status.txt") or "unknown"
    version = read_text(directory / "kernel-version.txt")
    processed = read_text(directory / "processed-version.txt")
    metrics = read_metrics(directory / "metrics.jsonl")
    val = [m["val_loss"] for m in metrics if "val_loss" in m]
    last_step = max((m.get("step", 0) for m in metrics), default=None)
    quality = {"complete": "ok", "running": "run", "queued": "run"}.get(status, "bad" if status in ("error", "failed") else "mute")
    verdict = "up-to-date" if version and version == processed else ("pending" if status == "complete" else "training")
    return (
        f"<tr><td><a href='{esc(link)}'>{esc(title)}</a><div class='muted'>{esc(slug)}</div></td>"
        f"<td><span class='pill {quality}'>{esc(status)}</span></td>"
        f"<td>{esc(version or '—')}</td><td>{esc(verdict)}</td>"
        f"<td>{esc(last_step if last_step is not None else '—')}</td>"
        f"<td>{esc(val[-1] if val else '—')}</td>"
        f"<td>{esc(min(val) if val else '—')}</td></tr>"
    )


def dataset_rows(root: Path) -> str:
    catalog = root / "config" / "ukraine_open_data_catalog.json"
    data = read_json(catalog)
    if not data:
        return "<tr><td colspan='3'>каталог не найден</td></tr>"
    rows = []
    for item in sorted(data.get("datasets", []), key=lambda x: x.get("priority", 99)):
        if not item.get("enabled", True):
            continue
        rows.append(
            f"<tr><td><a href='https://huggingface.co/datasets/JoTalbot/ua-open-data'>{esc(item.get('id'))}</a></td>"
            f"<td>{esc(item.get('title', ''))}</td><td>{esc(item.get('priority', ''))}</td></tr>"
        )
    return "".join(rows) or "<tr><td colspan='3'>пусто</td></tr>"


def discovery_count(root: Path) -> str:
    data = read_json(root / "artifacts" / "discovery" / "data_gov_ua_catalog.json")
    return str(len(data.get("datasets", []))) if data else "—"


CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font: 15px/1.55 -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #0d1117; color: #e6edf3; }
header { background: #161b22; border-bottom: 3px solid #f0b429; padding: 28px 24px; }
header h1 { margin: 0 0 6px; font-size: 24px; }
header p { margin: 0; color: #9da7b3; }
main { max-width: 1060px; margin: 0 auto; padding: 24px; }
h2 { font-size: 18px; border-left: 4px solid #f0b429; padding-left: 10px; margin-top: 36px; }
table { border-collapse: collapse; width: 100%; margin-top: 12px; background: #161b22; }
th, td { border: 1px solid #30363d; padding: 8px 10px; text-align: left; vertical-align: top; }
th { background: #1c2129; }
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
.muted { color: #9da7b3; font-size: 12px; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.pill.ok { background: #12381f; color: #3fb950; }
.pill.run { background: #0d2d4d; color: #58a6ff; }
.pill.bad { background: #4d1520; color: #f85149; }
.pill.mute { background: #2d333b; color: #9da7b3; }
code { font-size: 12px; }
footer { color: #9da7b3; font-size: 13px; text-align: center; padding: 30px 0; }
"""

PAGE = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ukraine Open Legal & Public Data — статус</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>Ukraine Open Legal & Public Data</h1>
  <p>Serverless pipeline: data.gov.ua → GitHub Actions → Hugging Face · обновлено {generated} UTC</p>
</header>
<main>
  <h2>Release identity</h2>
  <table>
    <tr><th>commit</th><th>branch</th><th>manifest UTC</th><th>files</th></tr>
    {release_row}
  </table>

  <h2>Модели (Kaggle GPU + CPU CI)</h2>
  <table>
    <tr><th>модель</th><th>статус</th><th>версия кернела</th><th>конвейер</th><th>steps</th><th>val_loss (last)</th><th>val_loss (best)</th></tr>
    {model_rows}
  </table>

  <h2>Зеркалируемые наборы data.gov.ua</h2>
  <p class="muted">Каталог: <a href="https://huggingface.co/datasets/JoTalbot/ua-open-data">ua-open-data</a> ·
  ЄДРСР 2006–2026: <a href="https://huggingface.co/datasets/JoTalbot/ua-edrsr">ua-edrsr</a> ·
  discovery нашёл <b>{discovered}</b> наборов.</p>
  <table>
    <tr><th>id</th><th>назва</th><th>пріоритет</th></tr>
    {dataset_rows}
  </table>

  <h2>Ссылки</h2>
  <p>
    <a href="https://github.com/JoTalbot/ukraine">Репозиторий</a> ·
    <a href="https://github.com/JoTalbot/ukraine/actions">GitHub Actions</a> ·
    <a href="https://huggingface.co/JoTalbot">Hugging Face</a>
  </p>
</main>
<footer>Страница сгенерирована scripts/build_dashboard.py — без сервера, только GitHub.</footer>
</body>
</html>
"""


def build(root: Path, output: Path) -> None:
    model_rows = "".join(kernel_row(root, slug, title, link) for slug, title, link in KERNELS)
    slug, title, link = CPU_LM
    model_rows += kernel_row(root, slug, title, link)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    page = PAGE.format(
        css=CSS,
        generated=generated,
        release_row=release_row(root),
        model_rows=model_rows,
        dataset_rows=dataset_rows(root),
        discovered=discovery_count(root),
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(page, encoding="utf-8")
    print(f"dashboard written: {output / 'index.html'} ({len(page)} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repository root to read manifests from")
    ap.add_argument("--output", default="dashboard", help="output directory for index.html")
    args = ap.parse_args()
    build(Path(args.root), Path(args.output))


if __name__ == "__main__":
    main()
