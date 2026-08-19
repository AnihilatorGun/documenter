import sqlite3
from datetime import date, datetime, timedelta

from documenter.models import Document, DocumentFilter, DocumentInput, Person, StoredFile, Tag


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
    placeholders = ",".join("?" * len(docs))
    ids = list(by_id)

    for row in conn.execute(
        f"SELECT dp.document_id AS document_id, p.id AS id, p.name AS name "
        f"FROM document_persons dp JOIN persons p ON p.id = dp.person_id "
        f"WHERE dp.document_id IN ({placeholders}) ORDER BY p.name",
        ids,
    ):
        by_id[row["document_id"]].persons.append(Person(row["id"], row["name"]))

    for row in conn.execute(
        f"SELECT dt.document_id AS document_id, t.id AS id, t.name AS name "
        f"FROM document_tags dt JOIN tags t ON t.id = dt.tag_id "
        f"WHERE dt.document_id IN ({placeholders}) ORDER BY t.name",
        ids,
    ):
        by_id[row["document_id"]].tags.append(Tag(row["id"], row["name"]))

    for row in conn.execute(
        f"SELECT document_id, language FROM document_languages "
        f"WHERE document_id IN ({placeholders}) ORDER BY language",
        ids,
    ):
        by_id[row["document_id"]].languages.append(row["language"])

    for row in conn.execute(
        f"SELECT * FROM files WHERE document_id IN ({placeholders}) ORDER BY id",
        ids,
    ):
        by_id[row["document_id"]].files.append(_row_to_file(row))


def _set_links(conn: sqlite3.Connection, document_id: int, data: DocumentInput) -> None:
    conn.executemany(
        "INSERT INTO document_persons (document_id, person_id) VALUES (?, ?)",
        [(document_id, pid) for pid in data.person_ids],
    )
    conn.executemany(
        "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
        [(document_id, tid) for tid in data.tag_ids],
    )
    conn.executemany(
        "INSERT INTO document_languages (document_id, language) VALUES (?, ?)",
        [(document_id, lang) for lang in data.languages],
    )


def _clear_links(conn: sqlite3.Connection, document_id: int) -> None:
    conn.execute("DELETE FROM document_persons WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM document_tags WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM document_languages WHERE document_id = ?", (document_id,))


def list_persons(conn: sqlite3.Connection) -> list[Person]:
    rows = conn.execute("SELECT id, name FROM persons ORDER BY name").fetchall()
    return [Person(row["id"], row["name"]) for row in rows]


def create_person(conn: sqlite3.Connection, name: str) -> Person:
    row = conn.execute("SELECT id, name FROM persons WHERE name = ?", (name,)).fetchone()
    if row:
        return Person(row["id"], row["name"])
    cur = conn.execute("INSERT INTO persons (name) VALUES (?)", (name,))
    conn.commit()
    return Person(cur.lastrowid, name)


def list_tags(conn: sqlite3.Connection) -> list[Tag]:
    rows = conn.execute("SELECT id, name FROM tags ORDER BY name").fetchall()
    return [Tag(row["id"], row["name"]) for row in rows]


def create_tag(conn: sqlite3.Connection, name: str) -> Tag:
    row = conn.execute("SELECT id, name FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return Tag(row["id"], row["name"])
    cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    conn.commit()
    return Tag(cur.lastrowid, name)


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

    if filt.person_ids:
        placeholders = ",".join("?" * len(filt.person_ids))
        clauses.append(f"id IN (SELECT document_id FROM document_persons WHERE person_id IN ({placeholders}))")
        params.extend(filt.person_ids)

    if filt.tag_ids:
        placeholders = ",".join("?" * len(filt.tag_ids))
        clauses.append(f"id IN (SELECT document_id FROM document_tags WHERE tag_id IN ({placeholders}))")
        params.extend(filt.tag_ids)

    if filt.languages:
        placeholders = ",".join("?" * len(filt.languages))
        clauses.append(f"id IN (SELECT document_id FROM document_languages WHERE language IN ({placeholders}))")
        params.extend(filt.languages)

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
