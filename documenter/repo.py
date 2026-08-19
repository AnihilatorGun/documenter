import sqlite3
from datetime import date, datetime, timedelta

from documenter.models import CATALOGS, Document, DocumentFilter, DocumentInput, Entry, StoredFile

# table, link table, link column for each catalog; the only place raw SQL identifiers come from user-known names
_CATALOG_TABLES = {
    "persons": ("persons", "document_persons", "person_id"),
    "tags": ("tags", "document_tags", "tag_id"),
    "languages": ("languages", "document_languages", "language_id"),
}


def _catalog_tables(catalog: str) -> tuple[str, str, str]:
    try:
        return _CATALOG_TABLES[catalog]
    except KeyError:
        raise ValueError(f"unknown catalog: {catalog}") from None


def _ids_attr(catalog: str) -> str:
    return catalog[:-1] + "_ids"  # persons -> person_ids, tags -> tag_ids, languages -> language_ids


def _to_date_str(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        title=row["title"],
        doc_number=row["doc_number"],
        issuer=row["issuer"],
        doc_date=_parse_date(row["doc_date"]),
        expires_at=_parse_date(row["expires_at"]),
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
        created_by=row["created_by"],
    )


def _row_to_file(row: sqlite3.Row) -> StoredFile:
    return StoredFile(
        id=row["id"],
        document_id=row["document_id"],
        filename=row["filename"],
        mime_type=row["mime_type"],
        size=row["size"],
        storage_key=row["storage_key"],
        uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
    )


def _attach_relations(conn: sqlite3.Connection, docs: list[Document]) -> None:
    if not docs:
        return
    by_id = {d.id: d for d in docs}
    ids = list(by_id)
    placeholders = ",".join("?" * len(ids))

    # catalog name doubles as the Document attribute name (persons/tags/languages)
    for catalog in CATALOGS:
        table, link, col = _catalog_tables(catalog)
        for row in conn.execute(
            f"SELECT l.document_id AS document_id, e.id AS id, e.name AS name "
            f"FROM {link} l JOIN {table} e ON e.id = l.{col} "
            f"WHERE l.document_id IN ({placeholders}) ORDER BY e.name",
            ids,
        ):
            getattr(by_id[row["document_id"]], catalog).append(Entry(row["id"], row["name"]))

    for row in conn.execute(
        f"SELECT * FROM files WHERE document_id IN ({placeholders}) ORDER BY id", ids
    ):
        by_id[row["document_id"]].files.append(_row_to_file(row))


def _set_links(conn: sqlite3.Connection, document_id: int, data: DocumentInput) -> None:
    for catalog in CATALOGS:
        _, link, col = _catalog_tables(catalog)
        entry_ids = getattr(data, _ids_attr(catalog))
        conn.executemany(
            f"INSERT INTO {link} (document_id, {col}) VALUES (?, ?)",
            [(document_id, entry_id) for entry_id in entry_ids],
        )


def _clear_links(conn: sqlite3.Connection, document_id: int) -> None:
    for catalog in CATALOGS:
        _, link, _ = _catalog_tables(catalog)
        conn.execute(f"DELETE FROM {link} WHERE document_id = ?", (document_id,))


def list_entries(conn: sqlite3.Connection, catalog: str) -> list[Entry]:
    table, link, col = _catalog_tables(catalog)
    rows = conn.execute(
        f"SELECT e.id AS id, e.name AS name, COUNT(l.document_id) AS documents "
        f"FROM {table} e LEFT JOIN {link} l ON l.{col} = e.id "
        f"GROUP BY e.id ORDER BY e.name"
    ).fetchall()
    return [Entry(row["id"], row["name"], row["documents"]) for row in rows]


def create_entry(conn: sqlite3.Connection, catalog: str, name: str) -> Entry:
    table, link, col = _catalog_tables(catalog)
    row = conn.execute(f"SELECT id, name FROM {table} WHERE name = ?", (name,)).fetchone()
    if row is None:
        cur = conn.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
        conn.commit()
        return Entry(cur.lastrowid, name, 0)
    documents = conn.execute(f"SELECT COUNT(*) FROM {link} WHERE {col} = ?", (row["id"],)).fetchone()[0]
    return Entry(row["id"], row["name"], documents)


def delete_entry(conn: sqlite3.Connection, catalog: str, entry_id: int) -> bool:
    table, link, col = _catalog_tables(catalog)
    in_use = conn.execute(f"SELECT 1 FROM {link} WHERE {col} = ? LIMIT 1", (entry_id,)).fetchone()
    if in_use is not None:
        return False
    cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
    conn.commit()
    return cur.rowcount > 0


def create_document(conn: sqlite3.Connection, data: DocumentInput, created_by: str) -> int:
    cur = conn.execute(
        "INSERT INTO documents (title, doc_number, issuer, doc_date, expires_at, notes, created_at, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data.title,
            data.doc_number,
            data.issuer,
            _to_date_str(data.doc_date),
            _to_date_str(data.expires_at),
            data.notes,
            _now_str(),
            created_by,
        ),
    )
    document_id = cur.lastrowid
    _set_links(conn, document_id, data)
    conn.commit()
    return document_id


def update_document(conn: sqlite3.Connection, document_id: int, data: DocumentInput) -> None:
    conn.execute(
        "UPDATE documents SET title = ?, doc_number = ?, issuer = ?, doc_date = ?, "
        "expires_at = ?, notes = ? WHERE id = ?",
        (
            data.title,
            data.doc_number,
            data.issuer,
            _to_date_str(data.doc_date),
            _to_date_str(data.expires_at),
            data.notes,
            document_id,
        ),
    )
    _clear_links(conn, document_id)
    _set_links(conn, document_id, data)
    conn.commit()


def get_document(conn: sqlite3.Connection, document_id: int) -> Document | None:
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        return None
    doc = _row_to_document(row)
    _attach_relations(conn, [doc])
    return doc


def delete_document(conn: sqlite3.Connection, document_id: int) -> list[str]:
    rows = conn.execute("SELECT storage_key FROM files WHERE document_id = ?", (document_id,)).fetchall()
    keys = [row["storage_key"] for row in rows]
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))  # cascades to links and files
    conn.commit()
    return keys


def search_documents(conn: sqlite3.Connection, filt: DocumentFilter, today: date) -> list[Document]:
    clauses = []
    params: list = []

    for catalog in CATALOGS:
        entry_ids = getattr(filt, _ids_attr(catalog))
        if entry_ids:
            _, link, col = _catalog_tables(catalog)
            placeholders = ",".join("?" * len(entry_ids))
            clauses.append(f"id IN (SELECT document_id FROM {link} WHERE {col} IN ({placeholders}))")
            params.extend(entry_ids)

    if filt.query:
        pattern = f"%{filt.query.lower()}%"
        clauses.append(
            "(lower(title) LIKE ? OR lower(notes) LIKE ? OR lower(doc_number) LIKE ? OR lower(issuer) LIKE ?)"
        )
        params.extend([pattern] * 4)

    if filt.expiring_within_days is not None:
        deadline = (today + timedelta(days=filt.expiring_within_days)).isoformat()
        clauses.append("expires_at IS NOT NULL AND expires_at <= ?")
        params.append(deadline)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order_by = "expires_at ASC" if filt.expiring_within_days is not None else "created_at DESC"
    rows = conn.execute(f"SELECT * FROM documents {where} ORDER BY {order_by}", params).fetchall()

    docs = [_row_to_document(row) for row in rows]
    _attach_relations(conn, docs)
    return docs


def add_file(
    conn: sqlite3.Connection, document_id: int, filename: str, mime_type: str, size: int, storage_key: str
) -> StoredFile:
    uploaded_at = _now_str()
    cur = conn.execute(
        "INSERT INTO files (document_id, filename, mime_type, size, storage_key, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (document_id, filename, mime_type, size, storage_key, uploaded_at),
    )
    conn.commit()
    return StoredFile(
        id=cur.lastrowid,
        document_id=document_id,
        filename=filename,
        mime_type=mime_type,
        size=size,
        storage_key=storage_key,
        uploaded_at=datetime.fromisoformat(uploaded_at),
    )


def get_file(conn: sqlite3.Connection, file_id: int) -> StoredFile | None:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return _row_to_file(row) if row else None


def delete_file(conn: sqlite3.Connection, file_id: int) -> str | None:
    row = conn.execute("SELECT storage_key FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()
    return row["storage_key"]
