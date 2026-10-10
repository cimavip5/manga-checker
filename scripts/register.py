"""Register BOOK☆WALKER series from an owner-created GitHub Issue.

Supported issue titles:
  manga-register: <numeric-series-id>  (existing single-series format)
  manga-register: bulk                 (one series ID per issue-body line)

The workflow must verify the issue author's identity before invoking this script.
"""
import json
import os
import re
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from update import ROOT, BASE, get_html

MAX_BATCH_LINES = 30
SERIES_ID_PATTERN = re.compile(r"[1-9][0-9]{0,9}")


def normalize_series_name(soup: BeautifulSoup) -> str:
    """Extract the series name without BOOK☆WALKER's SEO suffix."""
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = re.split(
        r"(?:[(（](?:マンガ|小説)|の電子書籍|[|｜]\s*BOOK☆WALKER)",
        title,
        maxsplit=1,
    )[0].strip(" 　-–｜|")
    if not title or "BOOK☆WALKER" in title or len(title) > 160:
        raise ValueError("シリーズ名を判定できません。作品ページの表記を確認してください")
    return title


def registration_ids(title: str, body: str) -> list[str]:
    """Keep the original single-ID title while allowing a batch issue body."""
    match = re.fullmatch(r"manga-register:\s*([1-9][0-9]{0,9}|bulk)", title)
    if not match:
        raise ValueError("登録指示が不正です。形式: manga-register: 123456 または manga-register: bulk")

    if match.group(1) != "bulk":
        return [match.group(1)]

    entries = [line.strip() for line in body.splitlines() if line.strip()]
    if not entries:
        raise ValueError("一括登録のIssue本文にシリーズIDを1行ずつ入力してください")
    if len(entries) > MAX_BATCH_LINES:
        raise ValueError(f"一括登録は最大{MAX_BATCH_LINES}行です（入力: {len(entries)}行）")
    return entries


def fetch_series_name(series_id: str) -> str:
    soup = get_html(f"{BASE}/series/{series_id}/list/")
    name = normalize_series_name(soup)
    if not soup.select("li.m-tile .m-book-item__title"):
        raise ValueError(f"作品が見つかりません: {series_id} ({name})")
    return name


def save_series_atomically(path: Path, registered: list) -> None:
    """Avoid replacing the existing series list with a partly written file."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".series-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(registered, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def format_report(new: list, existing: list, duplicates: list, failed: list) -> str:
    lines = [
        "## 漫画シリーズ登録結果",
        "",
        f"- 新規登録: {len(new)}件",
        f"- 登録済み: {len(existing)}件",
        f"- 入力内重複: {len(duplicates)}件",
        f"- 取得・入力失敗: {len(failed)}件",
    ]

    def safe(value) -> str:
        return str(value).replace("\n", " ").replace("\r", " ").replace("|", "｜").replace(chr(96), "'")[:200]

    if new:
        lines.extend(["", "### 新規登録"])
        lines.extend(f"- {safe(sid)}: {safe(name)}" for sid, name in new)
    if existing:
        lines.extend(["", "### 登録済み（スキップ）"])
        lines.extend(f"- {safe(sid)}" for sid in existing)
    if duplicates:
        lines.extend(["", "### 入力内重複（スキップ）"])
        lines.extend(f"- {safe(sid)}" for sid in duplicates)
    if failed:
        lines.extend(["", "### 取得・入力失敗"])
        lines.extend(f"- {safe(sid)}: {safe(reason)}" for sid, reason in failed)
    return "\n".join(lines) + "\n"


def write_report(report: str) -> None:
    print(report)
    report_path = os.environ.get("MANGA_REGISTRATION_REPORT_PATH")
    if report_path:
        Path(report_path).write_text(report, encoding="utf-8")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")


def main() -> None:
    title = os.environ.get("MANGA_REGISTRATION_TITLE", "").strip()
    body = os.environ.get("MANGA_REGISTRATION_BODY", "")
    entries = registration_ids(title, body)

    path = ROOT / "series.json"
    registered = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(registered, list):
        raise ValueError("series.jsonは配列である必要があります")

    known_ids = {str(item["id"]) for item in registered}
    seen_ids = set()
    new, existing, duplicates, failed = [], [], [], []

    for raw_id in entries:
        if not SERIES_ID_PATTERN.fullmatch(raw_id):
            failed.append((raw_id, "シリーズIDは1～10桁の数字（先頭0を除く）で指定してください"))
            continue
        if raw_id in seen_ids:
            duplicates.append(raw_id)
            continue
        seen_ids.add(raw_id)
        if raw_id in known_ids:
            existing.append(raw_id)
            continue

        try:
            name = fetch_series_name(raw_id)
        except Exception as exc:
            failed.append((raw_id, str(exc)))
            continue

        registered.append({"id": raw_id, "name": name})
        known_ids.add(raw_id)
        new.append((raw_id, name))

    if new:
        save_series_atomically(path, registered)
    write_report(format_report(new, existing, duplicates, failed))


if __name__ == "__main__":
    main()
