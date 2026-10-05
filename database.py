"""Small SQLite store; every operation opens and closes its own connection."""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from models import Profile, TroubleshootingStep

DB_PATH = Path(os.getenv("CALL_MAC_DB", str(Path(__file__).parent / "data" / "call_mac.db")))


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def initialize():
    with connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, operating_system TEXT NOT NULL,
            computer TEXT NOT NULL, phone TEXT NOT NULL, technical_level TEXT NOT NULL,
            preferences TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL REFERENCES profiles(id),
            problem TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id),
            step TEXT NOT NULL, result TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS solutions (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL REFERENCES profiles(id),
            session_id INTEGER UNIQUE REFERENCES sessions(id), problem TEXT NOT NULL,
            solution TEXT NOT NULL, history TEXT NOT NULL DEFAULT '[]',
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(attempts)")}
        for name, definition in [("observation", "TEXT NOT NULL DEFAULT ''"),
                                 ("action_id", "INTEGER"), ("is_explanation", "INTEGER NOT NULL DEFAULT 0")]:
            if name not in columns:
                conn.execute(f"ALTER TABLE attempts ADD COLUMN {name} {definition}")
        conn.execute("UPDATE attempts SET action_id=id WHERE action_id IS NULL")


def load_profile(profile_id=1):
    with connection() as conn:
        return Profile(**dict(conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()))


def list_profiles():
    with connection() as conn:
        return [Profile(**dict(row)) for row in conn.execute("SELECT * FROM profiles ORDER BY id")]


def save_profile(profile):
    with connection() as conn:
        values = (profile.name, profile.operating_system, profile.computer, profile.phone,
                  profile.technical_level, profile.preferences)
        if profile.id == 0:
            return conn.execute("INSERT INTO profiles (name, operating_system, computer, phone, technical_level, preferences) VALUES (?, ?, ?, ?, ?, ?)", values).lastrowid
        conn.execute("INSERT INTO profiles (id, name, operating_system, computer, phone, technical_level, preferences) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, operating_system=excluded.operating_system, computer=excluded.computer, phone=excluded.phone, technical_level=excluded.technical_level, preferences=excluded.preferences", (profile.id, *values))
        return profile.id


def start_session(problem, profile_id=1):
    problem = problem.strip()
    if not problem:
        raise ValueError("Please describe what's going wrong first.")
    with connection() as conn:
        conn.execute("UPDATE sessions SET status='paused' WHERE profile_id=? AND status='active'", (profile_id,))
        return conn.execute("INSERT INTO sessions (profile_id, problem) VALUES (?, ?)",
                            (profile_id, problem)).lastrowid


def active_session(profile_id=1):
    with connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE status='active' AND profile_id=? ORDER BY id DESC LIMIT 1", (profile_id,)).fetchone()
        return dict(row) if row else None


def pause_active(profile_id=1):
    with connection() as conn:
        conn.execute("UPDATE sessions SET status='paused' WHERE profile_id=? AND status='active'", (profile_id,))


def attempts(session_id):
    with connection() as conn:
        rows = conn.execute("SELECT * FROM attempts WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        return [{**dict(row), "step": json.loads(row["step"])} for row in rows]


def add_step(session_id, step, explanation_of=None):
    with connection() as conn:
        cursor = conn.execute("INSERT INTO attempts (session_id, step, action_id, is_explanation) VALUES (?, ?, ?, ?)",
                     (session_id, step.model_dump_json(), explanation_of, int(explanation_of is not None)))
        if explanation_of is None:
            conn.execute("UPDATE attempts SET action_id=id WHERE id=?", (cursor.lastrowid,))


def record_result(attempt_id, result, observation=""):
    if result not in {"failed", "unclear", "reply"}:
        raise ValueError("Unknown feedback.")
    with connection() as conn:
        conn.execute("UPDATE attempts SET result=?, observation=? WHERE id=?", (result, observation.strip()[:2000], attempt_id))


def resolve(session_id, observation=""):
    with connection() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        rows = conn.execute("SELECT * FROM attempts WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        if not session or not rows or rows[-1]["result"] != "pending":
            raise ValueError("Get a troubleshooting step before marking it fixed.")
        history = [{"step": json.loads(row["step"]), "result": row["result"], "observation": row["observation"], "action_id": row["action_id"], "is_explanation": bool(row["is_explanation"])} for row in rows]
        history[-1]["result"] = "fixed"
        history[-1]["observation"] = observation.strip()[:2000]
        original = next((row for row in rows if row["id"] == rows[-1]["action_id"]), rows[-1])
        if history[-1]["step"].get("next_move") == "resolved":
            candidate = next((row for row in reversed(rows[:-1])
                              if json.loads(row["step"]).get("kind") == "action"), None)
            if candidate is not None:
                original = next((row for row in rows if row["id"] == candidate["action_id"]), candidate)
            else:
                original = None
        solution = json.loads(original["step"])["step"] if original else "The user confirmed the issue was resolved."
        observations = [item["observation"] for item in history if item["observation"]]
        if observations:
            solution += "\n\nWhat the user observed: " + " | ".join(observations)
        conn.execute("UPDATE attempts SET result='fixed', observation=? WHERE id=?", (history[-1]["observation"], rows[-1]["id"]))
        conn.execute("INSERT INTO solutions (profile_id, session_id, problem, solution, history) VALUES (?, ?, ?, ?, ?)",
                     (session["profile_id"], session_id, session["problem"],
                      solution, json.dumps(history)))
        conn.execute("UPDATE sessions SET status='resolved' WHERE id=?", (session_id,))


def keywords(text):
    stop = {"the", "and", "that", "this", "with", "when", "what", "even", "though", "does", "says", "have", "been", "from", "into", "computer", "problem"}
    return {word.rstrip("s") for word in re.findall(r"[a-z0-9]+", text.casefold())
            if len(word) > 2 and word not in stop}


def memories(profile_id=1, limit=5, problem=None):
    with connection() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT problem, solution, is_demo, created_at FROM solutions WHERE profile_id=? ORDER BY id DESC",
            (profile_id,))]
    if problem is None:
        return rows[:limit]
    query = keywords(problem)
    ranked = [(len(query & keywords(row["problem"] + " " + row["solution"])), index, row)
              for index, row in enumerate(rows)]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [row for score, _, row in ranked if score > 0][:limit]


def seed_demo(profile_id=1):
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM solutions WHERE is_demo=1 AND profile_id=?", (profile_id,)).fetchone():
            conn.execute("INSERT INTO solutions (profile_id, problem, solution, is_demo) VALUES (?, ?, ?, 1)",
                         (profile_id, "Printer showed as offline even though it was powered on.",
                          "Restarting the Windows Print Spooler restored the printer connection."))
