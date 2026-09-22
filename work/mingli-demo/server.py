from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
SYSTEM_SCRIPTS = ROOT.parent / "mingli-system" / "scripts"
sys.path.insert(0, str(SYSTEM_SCRIPTS))
sys.path.insert(0, str(ROOT))

from report_engine import (  # noqa: E402
    MODEL_VERSION,
    WISDOM_MODEL_VERSION,
    dumps,
    generate_report,
    lunar_year_options,
    normalize_input,
    resolve_birthplace,
)
from narrative_diversity import body_text  # noqa: E402


DEFAULT_DB = ROOT / "data" / "demo_records.db"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_records (
          record_id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          gender TEXT NOT NULL,
          birth_date_text TEXT NOT NULL,
          birthplace TEXT,
          quality_level TEXT NOT NULL,
          max_report_level TEXT NOT NULL,
          input_json TEXT NOT NULL,
          chart_json TEXT NOT NULL,
          quality_json TEXT NOT NULL,
          rectification_json TEXT NOT NULL,
          report_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(report_records)")}
    for column, definition in (
        ("input_fingerprint", "TEXT"),
        ("model_version", "TEXT NOT NULL DEFAULT 'legacy'"),
    ):
        if column not in columns:
            conn.execute(f"ALTER TABLE report_records ADD COLUMN {column} {definition}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_fingerprint_version "
        "ON report_records(input_fingerprint, model_version)"
    )
    conn.commit()
    return conn


def report_fingerprint(input_data: dict[str, object]) -> str:
    canonical = {
        "name": input_data.get("name"),
        "gender": input_data.get("gender"),
        "calendarType": input_data.get("calendarType"),
        "year": input_data.get("year"),
        "month": input_data.get("month"),
        "day": input_data.get("day"),
        "isLeapMonth": input_data.get("isLeapMonth"),
        "solarDate": input_data.get("solarDate"),
        "timeText": input_data.get("timeText"),
        "timePrecision": input_data.get("timePrecision"),
        "birthplace": input_data.get("resolvedPlace") or input_data.get("birthplace"),
        "longitude": input_data.get("longitude"),
        "latitude": input_data.get("latitude"),
        "timezone": input_data.get("timezone"),
        "calendarVerified": input_data.get("calendarVerified"),
        "timeStandardVerified": input_data.get("timeStandardVerified"),
        "events": input_data.get("events") or [],
    }
    stable = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _record_from_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "recordId": row["record_id"], "createdAt": row["created_at"],
        "inputFingerprint": row["input_fingerprint"], "modelVersion": row["model_version"],
        **{key: json.loads(row[f"{key}_json"]) for key in ("input", "chart", "quality", "rectification", "report")},
    }


def save_report(db_path: Path, generated: dict[str, object], *,
                connection: sqlite3.Connection | None = None) -> dict[str, object]:
    input_data = generated["input"]
    quality = generated["quality"]
    fingerprint = report_fingerprint(input_data)
    model_version = str(generated.get("report", {}).get("modelVersion") or MODEL_VERSION)
    conn = connection or connect(db_path)
    owns_connection = connection is None
    try:
        if owns_connection:
            conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM report_records WHERE input_fingerprint = ? AND model_version = ? "
            "ORDER BY created_at DESC LIMIT 1", (fingerprint, model_version),
        ).fetchone()
        if existing:
            return {**_record_from_row(existing), "reused": True}
        record_id = uuid.uuid4().hex
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        birth_date_text = f"{input_data['calendarType']} {input_data['year']}-{input_data['month']}-{input_data['day']}"
        conn.execute(
            """INSERT INTO report_records (
                record_id, name, gender, birth_date_text, birthplace,
                quality_level, max_report_level, input_json, chart_json,
                quality_json, rectification_json, report_json, created_at, updated_at,
                input_fingerprint, model_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, input_data["name"], input_data["gender"], birth_date_text, input_data["birthplace"],
             quality["level"], quality["maxReportLevel"], dumps(input_data), dumps(generated["chart"]),
             dumps(quality), dumps(generated["rectification"]), dumps(generated["report"]), now, now,
             fingerprint, model_version),
        )
        if owns_connection:
            conn.commit()
        return {"recordId": record_id, "createdAt": now, "inputFingerprint": fingerprint,
                "modelVersion": model_version, "reused": False, **generated}
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


def narrative_fingerprint(input_data: dict[str, object]) -> str:
    return report_fingerprint({**input_data, "name": None})


def generate_and_save_report(db_path: Path, payload: dict[str, object], *, use_wisdom: bool = False) -> dict[str, object]:
    if not use_wisdom:
        return save_report(db_path, generate_report(payload))
    data = normalize_input(payload)
    fingerprint = report_fingerprint(data)
    identity = narrative_fingerprint(data)
    conn = connect(db_path)
    try:
        # Audit and save atomically; existing history cannot change the canonical draft.
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM report_records WHERE input_fingerprint = ? AND model_version = ? "
            "ORDER BY created_at DESC LIMIT 1", (fingerprint, WISDOM_MODEL_VERSION),
        ).fetchone()
        if existing:
            return {**_record_from_row(existing), "reused": True}
        references = []
        for row in conn.execute("SELECT input_json, report_json, model_version FROM report_records ORDER BY created_at, record_id"):
            prior_input, prior = json.loads(row["input_json"]), json.loads(row["report_json"])
            if narrative_fingerprint(prior_input) == identity:
                continue
            text = body_text(prior["sections"])
            references.append(text.replace(str(prior_input["name"]), "[姓名]"))
        generated = generate_report(payload, use_wisdom=True, narrative_references=references)
        saved = save_report(db_path, generated, connection=conn)
        conn.commit()
        return saved
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_reports(db_path: Path, query: str = "") -> list[dict[str, object]]:
    conn = connect(db_path)
    try:
        sql = """
            SELECT record_id, name, gender, birth_date_text, birthplace,
                   quality_level, max_report_level, created_at,
                   input_fingerprint, model_version
            FROM report_records
        """
        params: tuple[object, ...] = ()
        if query:
            sql += " WHERE name LIKE ? OR birthplace LIKE ?"
            pattern = f"%{query}%"
            params = (pattern, pattern)
        sql += " ORDER BY created_at DESC LIMIT 200"
        return [
            {
                "recordId": row["record_id"],
                "name": row["name"],
                "gender": row["gender"],
                "birthDateText": row["birth_date_text"],
                "birthplace": row["birthplace"],
                "qualityLevel": row["quality_level"],
                "maxReportLevel": row["max_report_level"],
                "createdAt": row["created_at"],
                "inputFingerprint": row["input_fingerprint"],
                "modelVersion": row["model_version"],
            }
            for row in conn.execute(sql, params)
        ]
    finally:
        conn.close()


def get_report(db_path: Path, record_id: str) -> dict[str, object] | None:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM report_records WHERE record_id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        return {
            "recordId": row["record_id"],
            "createdAt": row["created_at"],
            "inputFingerprint": row["input_fingerprint"],
            "modelVersion": row["model_version"],
            "input": json.loads(row["input_json"]),
            "chart": json.loads(row["chart_json"]),
            "quality": json.loads(row["quality_json"]),
            "rectification": json.loads(row["rectification_json"]),
            "report": json.loads(row["report_json"]),
        }
    finally:
        conn.close()


def delete_report(db_path: Path, record_id: str) -> bool:
    conn = connect(db_path)
    try:
        cursor = conn.execute("DELETE FROM report_records WHERE record_id = ?", (record_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


class DemoHandler(SimpleHTTPRequestHandler):
    db_path = DEFAULT_DB
    use_wisdom = True

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        if not urlparse(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json({"ok": True})
            return
        if parsed.path == "/api/calendar/lunar":
            try:
                year = int(parse_qs(parsed.query).get("year", [""])[0])
                self.send_json(lunar_year_options(year))
            except (TypeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/places":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            match = resolve_birthplace(query)
            self.send_json({"match": match})
            return
        if parsed.path == "/api/reports":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            self.send_json({"records": list_reports(self.db_path, query)})
            return
        if parsed.path.startswith("/api/reports/"):
            record = get_report(self.db_path, parsed.path.rsplit("/", 1)[-1])
            if record is None:
                self.send_json({"error": "记录不存在"}, HTTPStatus.NOT_FOUND)
            else:
                self.send_json(record)
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/reports":
            self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self.send_json(generate_and_save_report(self.db_path, payload, use_wisdom=self.use_wisdom), HTTPStatus.CREATED)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"error": f"报告生成失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/reports/"):
            self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return
        deleted = delete_report(self.db_path, parsed.path.rsplit("/", 1)[-1])
        self.send_json({"deleted": deleted}, HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Mingli report demo server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--wisdom-candidate", action="store_true", help="Accepted for compatibility; the wisdom report is now the default")
    parser.add_argument("--legacy-report", action="store_true", help="Use the legacy mingli-report-v3 generator")
    args = parser.parse_args()
    DemoHandler.db_path = args.db
    DemoHandler.use_wisdom = not args.legacy_report
    connect(args.db).close()
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"Mingli demo: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
