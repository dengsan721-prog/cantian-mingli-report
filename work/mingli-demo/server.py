from __future__ import annotations

import argparse
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

from report_engine import dumps, generate_report  # noqa: E402


DEFAULT_DB = ROOT / "data" / "demo_records.db"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
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
    conn.commit()
    return conn


def save_report(db_path: Path, generated: dict[str, object]) -> dict[str, object]:
    record_id = uuid.uuid4().hex
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    input_data = generated["input"]
    quality = generated["quality"]
    assert isinstance(input_data, dict) and isinstance(quality, dict)
    birth_date_text = f"{input_data['calendarType']} {input_data['year']}-{input_data['month']}-{input_data['day']}"
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO report_records (
              record_id, name, gender, birth_date_text, birthplace,
              quality_level, max_report_level, input_json, chart_json,
              quality_json, rectification_json, report_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                input_data["name"],
                input_data["gender"],
                birth_date_text,
                input_data["birthplace"],
                quality["level"],
                quality["maxReportLevel"],
                dumps(input_data),
                dumps(generated["chart"]),
                dumps(quality),
                dumps(generated["rectification"]),
                dumps(generated["report"]),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"recordId": record_id, "createdAt": now, **generated}


def list_reports(db_path: Path, query: str = "") -> list[dict[str, object]]:
    conn = connect(db_path)
    try:
        sql = """
            SELECT record_id, name, gender, birth_date_text, birthplace,
                   quality_level, max_report_level, created_at
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
            self.send_json(save_report(self.db_path, generate_report(payload)), HTTPStatus.CREATED)
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
    args = parser.parse_args()
    DemoHandler.db_path = args.db
    connect(args.db).close()
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"Mingli demo: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
