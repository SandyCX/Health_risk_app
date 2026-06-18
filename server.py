from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import datetime as dt
import json
import mimetypes
import random
import re
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "health_logs.db"


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def classify_risk(sleep_hours, steps, mood_score):
    """Decision tree: sleep -> steps -> mood."""
    if sleep_hours < 6:
        if steps < 4000:
            if mood_score <= 4:
                return "高"
            return "中"
        if mood_score <= 3:
            return "高"
        return "中"

    if sleep_hours < 7:
        if steps < 5000:
            if mood_score <= 4:
                return "中"
            return "中"
        if mood_score <= 3:
            return "中"
        return "低"

    if steps < 4000:
        if mood_score <= 4:
            return "中"
        return "中"
    if mood_score <= 3:
        return "中"
    return "低"


def normalize_log(row):
    return {
        "id": row["id"],
        "log_date": row["log_date"],
        "sleep_hours": row["sleep_hours"],
        "steps": row["steps"],
        "mood_score": row["mood_score"],
        "risk_level": row["risk_level"],
    }


def validate_log(payload, partial=False):
    fields = ["log_date", "sleep_hours", "steps", "mood_score"]
    if not partial:
        missing = [field for field in fields if field not in payload]
        if missing:
            raise ValueError(f"缺少欄位: {', '.join(missing)}")

    cleaned = {}
    if "log_date" in payload:
        try:
            dt.date.fromisoformat(str(payload["log_date"]))
        except ValueError as exc:
            raise ValueError("log_date 必須是 YYYY-MM-DD") from exc
        cleaned["log_date"] = str(payload["log_date"])

    if "sleep_hours" in payload:
        sleep = float(payload["sleep_hours"])
        if sleep < 0 or sleep > 24:
            raise ValueError("sleep_hours 必須介於 0 到 24")
        cleaned["sleep_hours"] = round(sleep, 1)

    if "steps" in payload:
        steps = int(payload["steps"])
        if steps < 0:
            raise ValueError("steps 不可為負數")
        cleaned["steps"] = steps

    if "mood_score" in payload:
        mood = int(payload["mood_score"])
        if mood < 1 or mood > 10:
            raise ValueError("mood_score 必須介於 1 到 10")
        cleaned["mood_score"] = mood

    return cleaned


def seed_rows():
    rng = random.Random(20260618)
    today = dt.date.today()
    rows = []

    groups = [
        (25, (4.0, 5.5), (1000, 3500), (1, 4)),
        (40, (5.7, 7.2), (3200, 6500), (4, 7)),
        (25, (7.0, 9.0), (6000, 10000), (6, 9)),
    ]
    day_offset = 89
    for count, sleep_range, steps_range, mood_range in groups:
        for _ in range(count):
            log_date = today - dt.timedelta(days=day_offset)
            sleep = round(rng.uniform(*sleep_range), 1)
            steps = rng.randint(*steps_range)
            mood = rng.randint(*mood_range)
            risk = classify_risk(sleep, steps, mood)
            rows.append((log_date.isoformat(), sleep, steps, mood, risk))
            day_offset -= 1

    return rows


def init_db():
    with connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS health_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date DATE NOT NULL,
                sleep_hours REAL NOT NULL,
                steps INTEGER NOT NULL,
                mood_score INTEGER NOT NULL,
                risk_level TEXT
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM health_logs").fetchone()[0]
        if count == 0:
            conn.executemany(
                """
                INSERT INTO health_logs
                    (log_date, sleep_hours, steps, mood_score, risk_level)
                VALUES (?, ?, ?, ?, ?)
                """,
                seed_rows(),
            )


def json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw)


def api_path(path):
    if path.startswith("/api/"):
        return path[4:]
    return path


class AppHandler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = api_path(parsed.path)

        if path == "/health-logs":
            with connect_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM health_logs ORDER BY log_date DESC, id DESC"
                ).fetchall()
            self.send_json([normalize_log(row) for row in rows])
            return

        if path == "/health-logs/risk":
            with connect_db() as conn:
                latest = conn.execute(
                    "SELECT * FROM health_logs ORDER BY log_date DESC, id DESC LIMIT 1"
                ).fetchone()
                counts = conn.execute(
                    "SELECT risk_level, COUNT(*) AS total FROM health_logs GROUP BY risk_level"
                ).fetchall()
            if latest is None:
                self.send_json({"risk_level": None, "latest": None, "summary": []})
                return
            risk = classify_risk(
                latest["sleep_hours"], latest["steps"], latest["mood_score"]
            )
            self.send_json(
                {
                    "risk_level": risk,
                    "latest": normalize_log(latest),
                    "summary": [dict(row) for row in counts],
                    "tree": [
                        "先判斷睡眠時數",
                        "再依睡眠結果判斷步數",
                        "最後用心情分數處理中間情況",
                    ],
                }
            )
            return

        self.serve_static(path)

    def do_POST(self):
        if api_path(urlparse(self.path).path) != "/health-logs":
            self.send_error_json("找不到 API", 404)
            return
        try:
            payload = validate_log(json_body(self))
            risk = classify_risk(
                payload["sleep_hours"], payload["steps"], payload["mood_score"]
            )
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error_json(str(exc))
            return

        with connect_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO health_logs
                    (log_date, sleep_hours, steps, mood_score, risk_level)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload["log_date"],
                    payload["sleep_hours"],
                    payload["steps"],
                    payload["mood_score"],
                    risk,
                ),
            )
            row = conn.execute(
                "SELECT * FROM health_logs WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        self.send_json(normalize_log(row), 201)

    def do_PUT(self):
        match = re.fullmatch(r"/health-logs/(\d+)", api_path(urlparse(self.path).path))
        if not match:
            self.send_error_json("找不到 API", 404)
            return
        log_id = int(match.group(1))
        try:
            updates = validate_log(json_body(self), partial=True)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error_json(str(exc))
            return
        if not updates:
            self.send_error_json("沒有可更新欄位")
            return

        with connect_db() as conn:
            current = conn.execute(
                "SELECT * FROM health_logs WHERE id = ?", (log_id,)
            ).fetchone()
            if current is None:
                self.send_error_json("找不到紀錄", 404)
                return
            merged = normalize_log(current)
            merged.update(updates)
            merged["risk_level"] = classify_risk(
                merged["sleep_hours"], merged["steps"], merged["mood_score"]
            )
            conn.execute(
                """
                UPDATE health_logs
                SET log_date = ?, sleep_hours = ?, steps = ?, mood_score = ?, risk_level = ?
                WHERE id = ?
                """,
                (
                    merged["log_date"],
                    merged["sleep_hours"],
                    merged["steps"],
                    merged["mood_score"],
                    merged["risk_level"],
                    log_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM health_logs WHERE id = ?", (log_id,)
            ).fetchone()
        self.send_json(normalize_log(row))

    def do_DELETE(self):
        match = re.fullmatch(r"/health-logs/(\d+)", api_path(urlparse(self.path).path))
        if not match:
            self.send_error_json("找不到 API", 404)
            return
        log_id = int(match.group(1))
        with connect_db() as conn:
            cursor = conn.execute("DELETE FROM health_logs WHERE id = ?", (log_id,))
        if cursor.rowcount == 0:
            self.send_error_json("找不到紀錄", 404)
            return
        self.send_json({"deleted": True, "id": log_id})

    def serve_static(self, path):
        if path == "/":
            target = STATIC_DIR / "index.html"
        else:
            target = (STATIC_DIR / path.lstrip("/")).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                self.send_error_json("非法路徑", 403)
                return
        if not target.exists() or target.is_dir():
            self.send_error_json("找不到頁面", 404)
            return
        content = target.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(target.name)[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), AppHandler)
    print("Health risk app running at http://127.0.0.1:8000")
    server.serve_forever()
