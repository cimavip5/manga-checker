"""Apply an owner-approved mixed batch of manga registrations, volumes, and removals.

Issue title: manga-batch: apply
Issue body: one command per line, for example::

    add 123456 8
    owned 114834 24
    remove 355456

An add volume is optional. Every requested operation is validated before
changing either JSON file. The GitHub Actions workflow must independently
restrict requests to the repository owner.
"""

import json
import os
import re
from pathlib import Path

from manage import save_json
from register import fetch_series_name
from update import ROOT

MAX_OPERATIONS = 100
MAX_REGISTRATIONS = 30
COMMAND_PATTERN = re.compile(
    r"(add|owned|remove)\s+([1-9][0-9]{0,9})(?:\s+(0|[1-9][0-9]{0,3}))?",
    re.IGNORECASE,
)


def parse_operations(body: str) -> list[tuple[str, str, int | None]]:
    """Reject malformed lines, duplicate IDs, and conflicting operations."""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not 1 <= len(lines) <= MAX_OPERATIONS:
        raise ValueError(f"一括更新は1～{MAX_OPERATIONS}件で指定してください")

    operations = []
    seen = set()
    registrations = 0
    for number, line in enumerate(lines, 1):
        match = COMMAND_PATTERN.fullmatch(line)
        if not match:
            raise ValueError(f"{number}行目の形式が不正です: {line[:100]}")
        action, sid, volume_text = match.groups()
        action = action.lower()
        if action == "owned" and volume_text is None:
            raise ValueError(f"{number}行目: 所持巻変更には巻数が必要です")
        if action == "remove" and volume_text is not None:
            raise ValueError(f"{number}行目: 登録解除に巻数は指定できません")
        if sid in seen:
            raise ValueError(f"シリーズID {sid} に複数の操作が指定されています")
        seen.add(sid)
        if action == "add":
            registrations += 1
        operations.append((action, sid, int(volume_text) if volume_text is not None else None))

    if registrations > MAX_REGISTRATIONS:
        raise ValueError(f"作品登録は一度に最大{MAX_REGISTRATIONS}作品です")
    return operations


def prepare_changes(
    series: list,
    data: dict | None,
    operations: list[tuple[str, str, int | None]],
    fetch_name=fetch_series_name,
) -> tuple[list, dict | None, list[str]]:
    """Prepare all changes in memory before any file is written."""
    if not isinstance(series, list):
        raise ValueError("series.jsonの形式が不正です")
    existing = {}
    for item in series:
        if not isinstance(item, dict) or "id" not in item or "name" not in item:
            raise ValueError("series.jsonに不正な作品データがあります")
        sid = str(item["id"])
        if sid in existing:
            raise ValueError(f"series.jsonに重複IDがあります: {sid}")
        existing[sid] = item

    if data is not None and (
        not isinstance(data, dict) or not isinstance(data.get("books"), list)
    ):
        raise ValueError("data.jsonの形式が不正です")

    # Validate existence and conflicts before any network requests.
    for action, sid, _ in operations:
        if action == "add" and sid in existing:
            raise ValueError(f"登録済みのシリーズIDです: {sid}")
        if action in ("owned", "remove") and sid not in existing:
            raise ValueError(f"未登録のシリーズIDです: {sid}")

    prepared = [dict(item) for item in series]
    by_id = {str(item["id"]): item for item in prepared}
    removed_ids = set()
    report = []
    for action, sid, volume in operations:
        if action == "add":
            try:
                name = fetch_name(sid)
            except Exception as exc:
                raise ValueError(f"作品名を取得できませんでした（{sid}）: {exc}") from exc
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"作品名が空欄です: {sid}")
            item = {"id": sid, "name": name.strip()}
            if volume is not None:
                item["owned_volume"] = volume
            prepared.append(item)
            report.append(f"登録: {item['name']} (ID {sid}, 所持巻 {volume if volume is not None else '未設定'})")
        elif action == "owned":
            item = by_id[sid]
            old = item.get("owned_volume")
            item["owned_volume"] = volume
            report.append(f"所持巻変更: {item['name']} (ID {sid}, {old if old is not None else '未設定'} → {volume})")
        elif action == "remove":
            removed_ids.add(sid)
            report.append(f"登録解除: {by_id[sid]['name']} (ID {sid})")

    if removed_ids:
        prepared = [item for item in prepared if str(item["id"]) not in removed_ids]
    updated_data = data
    if data is not None and removed_ids:
        updated_data = dict(data)
        updated_data["books"] = [
            book for book in data["books"]
            if str(book.get("id")) not in removed_ids
        ]
    return prepared, updated_data, report


def main() -> None:
    if os.environ.get("MANGA_MANAGEMENT_TITLE", "").strip() != "manga-batch: apply":
        raise ValueError("一括更新のIssueタイトルが不正です")
    operations = parse_operations(os.environ.get("MANGA_MANAGEMENT_BODY", ""))
    series_path = ROOT / "series.json"
    data_path = ROOT / "data.json"
    series = json.loads(series_path.read_text(encoding="utf-8"))
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else None
    prepared, updated_data, report = prepare_changes(series, data, operations)

    # Actions commits series.json and data.json together after this script succeeds.
    if prepared != series:
        save_json(series_path, prepared)
    if data is not None and updated_data != data:
        save_json(data_path, updated_data)
    print(f"混合一括更新: {len(operations)}件を検証・処理しました")
    for line in report:
        print("- " + line)


if __name__ == "__main__":
    main()
