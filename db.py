"""The small SQLite database — built on startup from content.py (ITEM-005/006)."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from config import *
from content import *

# --- Database ----------------------------------------------------------------

def init_db(database_path: str = DATABASE_PATH) -> None:
    """Create the database file and its base table if they aren't there yet.

    Safe to call every start-up: it only creates what's missing, so a restart
    never loses or duplicates anything. Later items add the real game tables and
    fill them from the fire-safety reference and the story.
    """
    # Make sure the folder exists (it always will for the default, but a custom
    # DATABASE_PATH might point somewhere new).
    parent = os.path.dirname(os.path.abspath(database_path))
    os.makedirs(parent, exist_ok=True)

    with closing(sqlite3.connect(database_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # Record the schema version so a future rebuild step can notice a change.
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    # Build (or rebuild) the fire content from the source of truth (ITEM-006).
    build_content(database_path)


def read_meta(key: str, database_path: str = DATABASE_PATH) -> str | None:
    """Read one value from the meta table. Returns None if the database or the
    table isn't there yet, so a page render can never crash just because the
    database hasn't been built — it degrades gracefully instead."""
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None
    except sqlite3.OperationalError:
        # e.g. the table doesn't exist yet — treat as "not set" rather than error.
        return None


# --- The fire content in the database (ITEM-006) ------------------------------

def build_content(database_path: str = DATABASE_PATH) -> None:
    """Create the fire-content tables and fill them from the source of truth above.
    Rebuilds them whenever CONTENT_VERSION changes, so editing the facts and bumping
    the version updates what the game uses on the next start. Safe to call every
    start-up."""
    parent = os.path.dirname(os.path.abspath(database_path))
    os.makedirs(parent, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fire_classes (
                id TEXT PRIMARY KEY, name_de TEXT, name_en TEXT,
                examples_de TEXT, icon TEXT, note_de TEXT, sort INTEGER
            );
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY, name_de TEXT, name_en TEXT,
                colour_de TEXT, sort INTEGER
            );
            CREATE TABLE IF NOT EXISTS matrix (
                class_id TEXT, tool_id TEXT, outcome TEXT, reason_de TEXT,
                PRIMARY KEY (class_id, tool_id)
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            """
        )
        stored = conn.execute(
            "SELECT value FROM meta WHERE key = 'content_version'"
        ).fetchone()
        if stored and stored[0] == str(CONTENT_VERSION):
            return  # already current; nothing to rebuild

        # Rebuild from scratch so a change to the facts is reflected exactly.
        conn.execute("DELETE FROM fire_classes")
        conn.execute("DELETE FROM tools")
        conn.execute("DELETE FROM matrix")
        for i, c in enumerate(FIRE_CLASSES):
            conn.execute(
                "INSERT INTO fire_classes (id,name_de,name_en,examples_de,icon,note_de,sort) "
                "VALUES (?,?,?,?,?,?,?)",
                (c["id"], c["name_de"], c["name_en"], c["examples_de"], c["icon"], c["note_de"], i),
            )
        for i, t in enumerate(TOOLS):
            conn.execute(
                "INSERT INTO tools (id,name_de,name_en,colour_de,sort) VALUES (?,?,?,?,?)",
                (t["id"], t["name_de"], t["name_en"], t["colour_de"], i),
            )
        for class_id, row in MATRIX.items():
            for tool_id, outcome in row.items():
                conn.execute(
                    "INSERT INTO matrix (class_id,tool_id,outcome,reason_de) VALUES (?,?,?,?)",
                    (class_id, tool_id, outcome, DANGER_REASONS.get((class_id, tool_id))),
                )
        conn.execute(
            "INSERT INTO meta (key,value) VALUES ('content_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(CONTENT_VERSION),),
        )
        conn.commit()


def load_matrix(database_path: str = DATABASE_PATH) -> dict:
    """Return the stored matrix as {(class_id, tool_id): outcome}."""
    with closing(sqlite3.connect(database_path)) as conn:
        rows = conn.execute("SELECT class_id, tool_id, outcome FROM matrix").fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def content_counts(database_path: str = DATABASE_PATH) -> tuple[int, int]:
    """(number of fire classes, number of tools) currently stored, or (0, 0) if the
    content isn't built yet — never raises, so the page can't crash."""
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            nc = conn.execute("SELECT COUNT(*) FROM fire_classes").fetchone()[0]
            nt = conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]
            return nc, nt
    except sqlite3.OperationalError:
        return 0, 0

