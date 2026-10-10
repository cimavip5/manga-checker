"""Apply owner-approved manga owned-volume updates and series removals."""
import json
import os
import re
import tempfile
from pathlib import Path

from update import ROOT


def save_json(path: Path, data) -> None:
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent,
            prefix=".manga-", suffix=".tmp", delete=False
        ) as handle:
            tmp = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)



MAX_BULK_OWNED = 100


def parse_owned_batch(body: str) -> dict[str, int]:
    """Validate all requested changes before allowing any write."""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not 1 <= len(lines) <= MAX_BULK_OWNED:
        raise ValueError(f"一括更新は1～{MAX_BULK_OWNED}行で指定してください")
    changes = {}
    for index, line in enumerate(lines, 1):
        match = re.fullmatch(r"([1-9][0-9]{0,9}):\s*(0|[1-9][0-9]{0,3})", line)
        if not match:
            raise ValueError(f"{index}行目の形式が不正です（ID: 巻数）")
        sid = match.group(1)
        if sid in changes:
            raise ValueError(f"入力内のシリーズIDが重複しています: {sid}")
        changes[sid] = int(match.group(2))
    return changes


def apply_owned_batch(series: list, changes: dict[str, int]) -> list[tuple[str, str, int]]:
    """Apply only validated changes; missing or ambiguous IDs fail as a group."""
    registered = {}
    for item in series:
        sid = str(item["id"])
        if sid in registered:
            raise ValueError(f"登録データ内に重複IDがあります: {sid}")
        registered[sid] = item
    missing = [sid for sid in changes if sid not in registered]
    if missing:
        raise ValueError("未登録のシリーズID: " + ", ".join(missing))

    updated = []
    for sid, volume in changes.items():
        item = registered[sid]
        if item.get("owned_volume") != volume:
            item["owned_volume"] = volume
            updated.append((sid, item["name"], volume))
    return updated


def main() -> None:
    title = os.environ.get("MANGA_MANAGEMENT_TITLE", "").strip()
    bulk_owned = title == "manga-owned: bulk"
    match_owned = re.fullmatch(r"manga-owned: ([1-9][0-9]{0,9}): (0|[1-9][0-9]{0,3})", title)
    match_remove = re.fullmatch(r"manga-remove: ([1-9][0-9]{0,9})", title)
    if not bulk_owned and not match_owned and not match_remove:
        raise ValueError("Invalid management request")

    series_path = ROOT / "series.json"
    series = json.loads(series_path.read_text(encoding="utf-8"))
    if not isinstance(series, list):
        raise ValueError("Invalid series.json format")
    if bulk_owned:
        changes = parse_owned_batch(os.environ.get("MANGA_MANAGEMENT_BODY", ""))
        updated = apply_owned_batch(series, changes)
        if updated:
            save_json(series_path, series)
        print(f"所持巻の一括更新: {len(updated)}件変更 / {len(changes) - len(updated)}件変更なし")
        for sid, name, volume in updated:
            print(f"- {sid}: {name} → {volume}巻")
        return

    sid = (match_owned or match_remove).group(1)
    matching = [item for item in series if str(item["id"]) == sid]
    if len(matching) != 1:
        raise ValueError(f"対象シリーズが一意に見つかりません: {sid}")
    selected = matching[0]
    if match_owned:
        volume = int(match_owned.group(2))
        if selected.get("owned_volume") == volume:
            print(f"変更なし: {selected['name']} 所持巻 {volume}")
            return
        selected["owned_volume"] = volume
        save_json(series_path, series)
        print(f"所持巻を更新: {selected['name']} / {volume}巻 (ID {sid})")
    else:
        series = [item for item in series if str(item["id"]) != sid]
        save_json(series_path, series)
        data_path = ROOT / "data.json"
        if data_path.exists():
            data = json.loads(data_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("books"), list):
                raise ValueError("Invalid data.json format")
            data["books"] = [book for book in data["books"] if str(book.get("id")) != sid]
            save_json(data_path, data)
        print(f"登録解除: {selected['name']} (ID {sid})")


if __name__ == "__main__":
    main()
