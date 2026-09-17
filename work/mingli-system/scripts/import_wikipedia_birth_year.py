from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from typing import Any

from import_wikidata_entities import run as import_wikidata_entities


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mingli_validation.db"
DEFAULT_TMP_QIDS = ROOT / "data" / "cache" / "wikipedia_birth_year_qids.txt"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def api_get(params: dict[str, str], retries: int = 6, pause: float = 0.5) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{WIKIPEDIA_API}?{query}",
        headers={"User-Agent": "MingliValidationWikipediaBirthYear/0.1 (local research; contact: local)"},
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if pause:
                    time.sleep(pause)
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < retries:
                retry_after = exc.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else min(90, 10 * attempt)
                time.sleep(wait)
                continue
            if attempt < retries:
                time.sleep(attempt * 3)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(3 * attempt)
    raise RuntimeError("Wikipedia API request failed") from last_error


def category_members(year: int, limit: int) -> list[dict[str, Any]]:
    title = f"Category:{year} births"
    members: list[dict[str, Any]] = []
    cmcontinue: str | None = None
    while len(members) < limit:
        batch_limit = min(50, limit - len(members))
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": title,
            "cmnamespace": "0",
            "cmlimit": str(batch_limit),
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = api_get(params)
        members.extend(data.get("query", {}).get("categorymembers", []))
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return members[:limit]


def wikidata_qids_for_pages(page_ids: list[int]) -> list[str]:
    qids: list[str] = []
    for offset in range(0, len(page_ids), 50):
        chunk = page_ids[offset:offset + 50]
        data = api_get(
            {
                "action": "query",
                "pageids": "|".join(str(page_id) for page_id in chunk),
                "prop": "pageprops",
                "format": "json",
            }
        )
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                qids.append(qid)
    return sorted(set(qids))


def write_qids(qids: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(qids) + "\n", encoding="utf-8")


def run(db_path: Path, year: int, limit: int, qids_path: Path) -> dict[str, Any]:
    members = category_members(year, limit)
    page_ids = [int(item["pageid"]) for item in members if "pageid" in item]
    qids = wikidata_qids_for_pages(page_ids)
    write_qids(qids, qids_path)
    import_result = import_wikidata_entities(db_path, qids_path)
    return {
        "year": year,
        "requested_limit": limit,
        "category_members": len(members),
        "page_ids": len(page_ids),
        "unique_qids": len(qids),
        "qids_file": str(qids_path),
        "import_result": import_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import public people from an English Wikipedia birth-year category.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--qids", type=Path, default=DEFAULT_TMP_QIDS)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.year, args.limit, args.qids), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
