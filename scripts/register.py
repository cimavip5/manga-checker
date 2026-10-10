"""Register a BOOK☆WALKER series from an owner-created GitHub Issue.

Expected issue title: manga-register: <numeric-series-id>
The workflow checks the issue author's identity before running this script.
"""
import json
import os
import re

from bs4 import BeautifulSoup

from update import ROOT, BASE, get_html


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


def main():
    issue_title = os.environ.get("MANGA_REGISTRATION_TITLE", "").strip()
    match = re.fullmatch(r"manga-register:\s*([1-9][0-9]{0,9})", issue_title)
    if not match:
        raise ValueError("登録指示が不正です。形式: manga-register: 123456")

    series_id = match.group(1)
    path = ROOT / "series.json"
    registered = json.loads(path.read_text(encoding="utf-8"))
    if any(str(item["id"]) == series_id for item in registered):
        print(f"Already registered: {series_id}")
        return

    soup = get_html(f"{BASE}/series/{series_id}/list/")
    name = normalize_series_name(soup)
    if not soup.select("li.m-tile .m-book-item__title"):
        raise ValueError(f"作品が見つかりません: {series_id} ({name})")

    registered.append({"id": series_id, "name": name})
    path.write_text(
        json.dumps(registered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Registered {series_id}: {name}")


if __name__ == "__main__":
    main()
