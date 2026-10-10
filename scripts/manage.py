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


def main() -> None:
    title = os.environ.get("MANGA_MANAGEMENT_TITLE", "").strip()
    match_owned = re.fullmatch(r"manga-owned: ([1-9][0-9]{0,9}): (0|[1-9][0-9]{0,3})", title)
    match_remove = re.fullmatch(r"manga-remove: ([1-9][0-9]{0,9})", title)
    if not match_owned and not match_remove:
        raise ValueError("Invalid management request")

    sid = (match_owned or match_remove).group(1)
    series_path = ROOT / "series.json"
    series = json.loads(series_path.read_text(encoding="utf-8"))
    if not isinstance(series, list):
        raise ValueError("Invalid series.json format")
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
