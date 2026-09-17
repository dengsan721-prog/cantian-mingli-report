from __future__ import annotations

import argparse
import json
from pathlib import Path

from calculate_chart_snapshots import run as calculate_snapshots
from build_precision_foundation import run as build_precision_foundation
from db_stats import collect as collect_stats
from evaluate_quality_rules import run as evaluate_rules
from import_wikidata_entities import run as import_wikidata_entities
from init_database import DEFAULT_DB, create_database
from validate_database import validate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QIDS = ROOT / "pipeline" / "wikidata_seed_qids.txt"


def rebuild(db_path: Path, qids_path: Path, skip_wikidata: bool) -> dict[str, object]:
    init_counts = create_database(db_path, reset=True)
    import_result = None
    if not skip_wikidata:
        import_result = import_wikidata_entities(db_path, qids_path)
    chart_result = calculate_snapshots(db_path)
    precision_result = build_precision_foundation(db_path)
    eval_result = evaluate_rules(db_path)
    validation = validate(db_path)
    stats = collect_stats(db_path)
    return {
        "database": str(db_path),
        "init_counts": init_counts,
        "wikidata_import": import_result,
        "chart_snapshots": chart_result,
        "precision_foundation": precision_result,
        "rule_evaluation": eval_result,
        "validation": validation,
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the Mingli validation database end to end.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--qids", type=Path, default=DEFAULT_QIDS)
    parser.add_argument("--skip-wikidata", action="store_true")
    args = parser.parse_args()
    result = rebuild(args.db, args.qids, args.skip_wikidata)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["validation"]["ok"] else 1)  # type: ignore[index]


if __name__ == "__main__":
    main()
