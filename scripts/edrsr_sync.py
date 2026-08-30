"""Download the official EDRSR open-data archive and publish Parquet-ready records.

The source is the official Data.gov.ua open-data publication maintained by the
State Judicial Administration of Ukraine. The archive is downloaded to CI's
ephemeral storage and never committed to Git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq

DATASET_SEARCH_URL = "https://data.gov.ua/api/3/action/package_search"
DATASET_FALLBACK_2026 = "16ab7f06-7414-405f-8354-0a492475272d"
DOWNLOAD_TIMEOUT = 300
CHUNK_SIZE = 10_000
PART_ROWS = 250_000
USER_AGENT = "JoTalbot/ukraine-edrsr-pipeline"


def http_json(url: str) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def find_dataset_id(year: int) -> str:
    query = f"Єдиний державний реєстр судових рішень за {year} рік"
    url = DATASET_SEARCH_URL + "?q=" + quote(query)
    try:
        payload = http_json(url)
        results = payload.get("result", {}).get("results", [])
        for item in results:
            title = item.get("title", "")
            if str(year) in title and "Єдиний державний реєстр судових рішень" in title:
                return str(item["id"])
    except Exception as exc:
        print(f"Data.gov.ua API discovery failed: {exc}")
    if year == 2026:
        return DATASET_FALLBACK_2026
    raise RuntimeError(f"Could not discover Data.gov.ua dataset for EDRSR year {year}")


def discover_download_url(year: int) -> tuple[str, str]:
    dataset_id = find_dataset_id(year)
    url = f"https://data.gov.ua/api/3/action/package_show?id={dataset_id}"
    payload = http_json(url)
    resources = payload.get("result", {}).get("resources", [])
    wanted = f"edrsr_data_{year}.zip".lower()
    for resource in resources:
        name = str(resource.get("name", "")).lower()
        fmt = str(resource.get("format", "")).lower()
        if name == wanted or ("edrsr_data" in name and fmt == "zip"):
            download = resource.get("url") or resource.get("download_url")
            if download:
                return str(download), dataset_id
    raise RuntimeError(f"No EDRSR ZIP resource found in Data.gov.ua dataset {dataset_id}")


def remote_change_tag(url: str) -> str | None:
    """Best-effort change indicator (ETag, or Last-Modified) for the archive."""
    req = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=60) as response:
            return response.headers.get("ETag") or response.headers.get("Last-Modified")
    except Exception:
        return None


def download(url: str, target: Path) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    with urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response, target.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(zf: zipfile.ZipFile, root: Path) -> None:
    root_resolved = root.resolve()
    for member in zf.infolist():
        destination = (root / member.filename).resolve()
        if destination != root_resolved and root_resolved not in destination.parents:
            raise RuntimeError(f"Unsafe ZIP member path: {member.filename}")
    zf.extractall(root)


def strip_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def xml_to_dict(element: ET.Element) -> dict[str, Any]:
    children = list(element)
    if not children:
        return {strip_tag(element.tag): (element.text or "").strip()}
    result: dict[str, Any] = {}
    for child in children:
        key = strip_tag(child.tag)
        if list(child):
            value: Any = xml_to_dict(child)
            # Collapse one-level wrappers where useful.
            if len(value) == 1 and key not in value:
                value = next(iter(value.values()))
        else:
            value = (child.text or "").strip()
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def iter_xml_records(path: Path) -> Iterator[dict[str, Any]]:
    # The official archive is XML-oriented, but roots can vary between releases.
    # Treat each top-level child as a record when possible.
    root = ET.parse(path).getroot()
    children = list(root)
    if children:
        for child in children:
            record = xml_to_dict(child)
            if record:
                yield record
    else:
        yield xml_to_dict(root)


def iter_records(root: Path) -> Iterator[tuple[dict[str, Any], str]]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rel = path.relative_to(root).as_posix()
        if suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except UnicodeDecodeError:
                data = json.loads(path.read_text(encoding="cp1251"))
            if isinstance(data, list):
                for record in data:
                    if isinstance(record, dict):
                        yield record, rel
            elif isinstance(data, dict):
                yield data, rel
        elif suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for record in csv.DictReader(fh):
                    yield dict(record), rel
        elif suffix in {".xml", ".xhtml"}:
            for record in iter_xml_records(path):
                yield record, rel


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    value = str(value).strip()
    return value or None


def pick(raw: dict[str, Any], *names: str) -> Any:
    normalized = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in raw.items()}
    for name in names:
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in normalized:
            return normalized[key]
    return None


def normalize(raw: dict[str, Any], source_file: str, source_sha256: str, dataset_id: str) -> dict[str, Any]:
    text = text_value(pick(raw, "text", "body", "content", "document_text", "tekst", "fulltext"))
    case_number = text_value(pick(raw, "case_number", "caseNo", "nomer_spravy", "caseNum", "case"))
    document_id = text_value(pick(raw, "document_id", "id", "doc_id", "id_doc", "document"))
    result = {
        "case_number": case_number,
        "document_id": document_id,
        "court": text_value(pick(raw, "court", "court_name", "sud")),
        "court_instance": text_value(pick(raw, "court_instance", "instance", "instanciya")),
        "document_type": text_value(pick(raw, "document_type", "decision_type", "type")),
        "decision_date": text_value(pick(raw, "decision_date", "date_decision", "date", "data")),
        "publication_date": text_value(pick(raw, "publication_date", "published_at")),
        "category": text_value(pick(raw, "category", "category_name", "kategoriya")),
        "text": text,
        "source_url": text_value(pick(raw, "source_url", "url", "reyestr_url")),
        "source_dataset": f"https://data.gov.ua/dataset/{dataset_id}",
        "source_sha256": source_sha256,
        "source_file": source_file,
        "extra": json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
    }
    return result


def write_parquet(
    records: Iterator[tuple[dict[str, Any], str]],
    output: Path,
    source_sha256: str,
    dataset_id: str,
    change_tag: str | None = None,
) -> int:
    """Write normalized records as several Parquet parts instead of one huge file."""
    output.mkdir(parents=True, exist_ok=True)
    total = 0
    part_no = 0
    rows_in_part = 0
    parts: list[dict[str, Any]] = []
    writer: pq.ParquetWriter | None = None
    part_path = output / f"part-{part_no:05d}.parquet"
    buffer: list[dict[str, Any]] = []

    def write_buffer() -> None:
        nonlocal writer, rows_in_part, total, buffer
        table = pa.Table.from_pylist(buffer)
        if writer is None:
            writer = pq.ParquetWriter(part_path, table.schema, compression="zstd")
        writer.write_table(table)
        rows_in_part += len(buffer)
        total += len(buffer)
        buffer = []

    def rotate_part() -> None:
        nonlocal writer, rows_in_part, part_no, part_path
        if writer is not None:
            writer.close()
            parts.append({"file": part_path.name, "rows": rows_in_part})
            writer = None
        rows_in_part = 0
        part_no += 1
        part_path = output / f"part-{part_no:05d}.parquet"

    try:
        for raw, source_file in records:
            buffer.append(normalize(raw, source_file, source_sha256, dataset_id))
            if len(buffer) >= CHUNK_SIZE:
                write_buffer()
                if rows_in_part >= PART_ROWS:
                    rotate_part()
        if buffer:
            write_buffer()
        rotate_part()
    except BaseException:
        if writer is not None:
            writer.close()
        raise

    if total == 0:
        raise RuntimeError("No XML/JSON/CSV records were found in the EDRSR archive")
    manifest = {
        "records": total,
        "sha256": source_sha256,
        "dataset_id": dataset_id,
        "remote_change_tag": change_tag,
        "parquet_parts": parts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--skip-if-tag",
        default="",
        help="Skip processing when the remote ETag/Last-Modified equals this tag",
    )
    args = parser.parse_args()

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    download_url, dataset_id = discover_download_url(args.year)
    print(f"EDRSR dataset discovered: {dataset_id}")
    print(f"Source: {download_url}")

    change_tag = remote_change_tag(download_url)
    if args.skip_if_tag and change_tag and args.skip_if_tag == change_tag:
        manifest = {
            "skipped": True,
            "remote_change_tag": change_tag,
            "year": args.year,
            "dataset_id": dataset_id,
            "source_url": download_url,
        }
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Remote archive unchanged since the previous run; skipping.")
        return 0

    with tempfile.TemporaryDirectory(prefix="edrsr-") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / f"edrsr_data_{args.year}.zip"
        source_sha256 = download(download_url, archive)
        print(f"Downloaded archive SHA-256: {source_sha256}")
        extracted = tmp_path / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as zf:
            bad = zf.testzip()
            if bad:
                raise RuntimeError(f"Corrupt ZIP member: {bad}")
            safe_extract(zf, extracted)
        count = write_parquet(iter_records(extracted), output, source_sha256, dataset_id, change_tag)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        manifest["year"] = args.year
        manifest["source_url"] = download_url
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"EDRSR pipeline completed: {count} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
