import sqlite3
from pathlib import Path

from documenter.models import DEFAULT_LANGUAGES, DEFAULT_TAGS

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


EARLIER_LANGUAGE_CODES = {"ru": "русский", "pl": "польский", "en": "английский"}


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    _move_languages_into_a_catalog(conn)
    _seed(conn, "tags", DEFAULT_TAGS)
    _seed(conn, "languages", DEFAULT_LANGUAGES)
    conn.commit()


def _seed(conn: sqlite3.Connection, table: str, names: list[str]) -> None:
    if conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0:
        conn.executemany(f"INSERT INTO {table} (name) VALUES (?)", [(name,) for name in names])


def _move_languages_into_a_catalog(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(document_languages)")}
    if "language" not in columns:
        return
    links = conn.execute("SELECT document_id, language FROM document_languages").fetchall()
    conn.execute("DROP TABLE document_languages")
    conn.executescript(SCHEMA_PATH.read_text())
    for link in links:
        name = EARLIER_LANGUAGE_CODES.get(link["language"], link["language"])
        conn.execute("INSERT OR IGNORE INTO languages (name) VALUES (?)", (name,))
        conn.execute(
            "INSERT OR IGNORE INTO document_languages (document_id, language_id) "
            "SELECT ?, id FROM languages WHERE name = ?",
            (link["document_id"], name),
        )


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
