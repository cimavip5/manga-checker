import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://bookwalker.jp"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PersonalMangaReleaseChecker/1.0)"}
session = requests.Session()
session.headers.update(HEADERS)


def get_html(url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def volume_number(title):
    # Normalize full-width numerals and distinguish numbered volumes from extras.
    import unicodedata
    normalized = unicodedata.normalize("NFKC", title)
    patterns = [
        r"\((\d+)\)\s*(?:\[[^\]]*\])?\s*$",
        r"【\s*(\d+)\s*】\s*(?:【[^】]*】)?\s*$",
        r"(?:第)?(\d+)\s*巻\s*(?:【[^】]*】)?\s*$",
        r"(?:第)?(\d+)\s*話\s*$",
        r"(?<!\d)(\d+)\s*(?:【[^】]*】)?\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return int(match.group(1))
    return None

def release_date(soup):
    for label in soup.select("dt"):
        if "配信開始日" in label.get_text(" ", strip=True):
            value = label.find_next_sibling("dd")
            if value:
                match = re.search(r"(20\d{2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{1,2})", value.get_text(" ", strip=True))
                if match:
                    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return None


def fetch(series):
    sid = str(series["id"])
    result = {"id": sid, "name": series["name"], "volume": None,
              "title": None, "release_date": None, "url": None, "status": "error"}
    try:
        soup = get_html(f"{BASE}/series/{sid}/list/")
        candidates = []
        for tile in soup.select("li.m-tile"):
            node = tile.select_one(".m-book-item__title")
            anchor = tile.select_one(".m-book-item__title a")
            if not node or not anchor or not anchor.get("href"):
                continue
            title = node.get_text(" ", strip=True)
            if "無料お試し" in title or "試し読み" in title:
                continue
            number = volume_number(title)
            if number is not None:
                candidates.append((number, title, urljoin(BASE, anchor["href"])))
        if not candidates:
            raise ValueError("巻数を判定できる商品がありません")
        number, title, url = max(candidates, key=lambda item: item[0])
        result.update(volume=number, title=title, url=url)
        detail = get_html(url)
        result["release_date"] = release_date(detail)
        result["status"] = "ok" if result["release_date"] else "date_missing"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    return result


def main():
    series = json.loads((ROOT / "series.json").read_text(encoding="utf-8"))
    prior_path = ROOT / "data.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
    old = {str(x["id"]): x for x in prior.get("books", [])}
    books = []
    for item in series:
        current = fetch(item)
        if current["status"] == "error" and str(item["id"]) in old:
            previous = old[str(item["id"])]
            for field in ("volume", "title", "release_date", "url"):
                current[field] = previous.get(field)
            current["status"] = "stale"
        books.append(current)
        time.sleep(1)
    output = {"updated_at": datetime.now(timezone.utc).isoformat(), "books": books}
    prior_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
