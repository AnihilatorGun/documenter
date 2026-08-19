from datetime import date, timedelta

import pytest

from documenter import repo
from documenter.db import connect, init_db
from documenter.models import CATALOGS, DocumentFilter, DocumentInput


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def make_document(conn, **overrides):
    kwargs = dict(title="Passport", doc_number="123", issuer="MVD", notes="hello")
    kwargs.update(overrides)
    data = DocumentInput(**kwargs)
    return repo.create_document(conn, data, created_by="alice@example.com")


def make_entry(conn, catalog, name):
    return repo.create_entry(conn, catalog, name).id


@pytest.mark.parametrize("catalog", CATALOGS)
def test_create_entry_idempotent(conn, catalog):
    e1 = repo.create_entry(conn, catalog, "Alice")
    e2 = repo.create_entry(conn, catalog, "Alice")
    assert e1.id == e2.id
    assert [e.name for e in repo.list_entries(conn, catalog)].count("Alice") == 1


@pytest.mark.parametrize("catalog", CATALOGS)
def test_list_entries_sorted_alphabetically(conn, catalog):
    repo.create_entry(conn, catalog, "Zeta")
    repo.create_entry(conn, catalog, "Alpha")
    names = [e.name for e in repo.list_entries(conn, catalog) if e.name in ("Zeta", "Alpha")]
    assert names == ["Alpha", "Zeta"]


def test_list_tags_includes_defaults(conn):
    names = {t.name for t in repo.list_entries(conn, "tags")}
    assert "виза" in names


def test_list_languages_includes_defaults(conn):
    names = {t.name for t in repo.list_entries(conn, "languages")}
    assert "русский" in names


def test_unknown_catalog_raises(conn):
    with pytest.raises(ValueError):
        repo.list_entries(conn, "bogus")
    with pytest.raises(ValueError):
        repo.create_entry(conn, "bogus", "x")
    with pytest.raises(ValueError):
        repo.delete_entry(conn, "bogus", 1)


@pytest.mark.parametrize("catalog", CATALOGS)
def test_list_entries_counts_documents(conn, catalog):
    used = repo.create_entry(conn, catalog, "used")
    unused = repo.create_entry(conn, catalog, "unused")
    ids_attr = catalog[:-1] + "_ids"
    make_document(conn, **{ids_attr: [used.id]})
    make_document(conn, **{ids_attr: [used.id]})

    entries = {e.name: e for e in repo.list_entries(conn, catalog)}
    assert entries["used"].documents == 2
    assert entries["unused"].documents == 0


@pytest.mark.parametrize("catalog", CATALOGS)
def test_create_entry_existing_reports_document_count(conn, catalog):
    entry = repo.create_entry(conn, catalog, "used")
    ids_attr = catalog[:-1] + "_ids"
    make_document(conn, **{ids_attr: [entry.id]})

    again = repo.create_entry(conn, catalog, "used")
    assert again.documents == 1


@pytest.mark.parametrize("catalog", CATALOGS)
def test_delete_entry_unused_succeeds(conn, catalog):
    entry = repo.create_entry(conn, catalog, "throwaway")
    assert repo.delete_entry(conn, catalog, entry.id) is True
    assert entry.name not in [e.name for e in repo.list_entries(conn, catalog)]


@pytest.mark.parametrize("catalog", CATALOGS)
def test_delete_entry_used_fails_and_keeps_data(conn, catalog):
    entry = repo.create_entry(conn, catalog, "in-use")
    ids_attr = catalog[:-1] + "_ids"
    doc_id = make_document(conn, **{ids_attr: [entry.id]})

    assert repo.delete_entry(conn, catalog, entry.id) is False

    assert entry.name in [e.name for e in repo.list_entries(conn, catalog)]
    doc = repo.get_document(conn, doc_id)
    assert entry.name in [e.name for e in getattr(doc, catalog)]


def test_create_and_get_document_with_relations(conn):
    alice = repo.create_entry(conn, "persons", "Alice")
    bob = repo.create_entry(conn, "persons", "Bob")
    tag = repo.create_entry(conn, "tags", "виза")
    ru = repo.create_entry(conn, "languages", "русский")
    en = repo.create_entry(conn, "languages", "английский")

    data = DocumentInput(
        title="Passport",
        person_ids=[alice.id, bob.id],
        tag_ids=[tag.id],
        language_ids=[ru.id, en.id],
        doc_number="AB-1",
        issuer="MVD",
        doc_date=date(2020, 1, 1),
        expires_at=date(2030, 1, 1),
        notes="some notes",
    )
    doc_id = repo.create_document(conn, data, created_by="alice@example.com")

    doc = repo.get_document(conn, doc_id)
    assert doc is not None
    assert doc.title == "Passport"
    assert doc.doc_number == "AB-1"
    assert doc.issuer == "MVD"
    assert doc.doc_date == date(2020, 1, 1)
    assert doc.expires_at == date(2030, 1, 1)
    assert doc.notes == "some notes"
    assert doc.created_by == "alice@example.com"
    assert {p.name for p in doc.persons} == {"Alice", "Bob"}
    assert [t.name for t in doc.tags] == ["виза"]
    assert [lang.name for lang in doc.languages] == ["английский", "русский"]
    assert doc.files == []


def test_get_document_missing_returns_none(conn):
    assert repo.get_document(conn, 999) is None


def test_create_document_with_no_dates(conn):
    data = DocumentInput(title="Note")
    doc_id = repo.create_document(conn, data, created_by="alice@example.com")
    doc = repo.get_document(conn, doc_id)
    assert doc.doc_date is None
    assert doc.expires_at is None


def test_update_document_replaces_links(conn):
    alice = repo.create_entry(conn, "persons", "Alice")
    bob = repo.create_entry(conn, "persons", "Bob")
    tag1 = repo.create_entry(conn, "tags", "виза")
    tag2 = repo.create_entry(conn, "tags", "медицина")
    ru = repo.create_entry(conn, "languages", "русский")
    en = repo.create_entry(conn, "languages", "английский")

    doc_id = make_document(
        conn, person_ids=[alice.id], tag_ids=[tag1.id], language_ids=[ru.id], title="Old title"
    )

    updated = DocumentInput(
        title="New title",
        person_ids=[bob.id],
        tag_ids=[tag2.id],
        language_ids=[en.id],
        doc_number="new-number",
    )
    repo.update_document(conn, doc_id, updated)

    doc = repo.get_document(conn, doc_id)
    assert doc.title == "New title"
    assert doc.doc_number == "new-number"
    assert [p.name for p in doc.persons] == ["Bob"]
    assert [t.name for t in doc.tags] == ["медицина"]
    assert [lang.name for lang in doc.languages] == ["английский"]


def test_delete_document_returns_storage_keys_and_cascades(conn):
    doc_id = make_document(conn)
    repo.add_file(conn, doc_id, "a.pdf", "application/pdf", 10, "key-a")
    repo.add_file(conn, doc_id, "b.pdf", "application/pdf", 20, "key-b")

    keys = repo.delete_document(conn, doc_id)
    assert sorted(keys) == ["key-a", "key-b"]
    assert repo.get_document(conn, doc_id) is None

    row = conn.execute("SELECT COUNT(*) AS n FROM files WHERE document_id = ?", (doc_id,)).fetchone()
    assert row["n"] == 0


def test_delete_document_no_files_returns_empty_list(conn):
    doc_id = make_document(conn)
    assert repo.delete_document(conn, doc_id) == []


def test_add_get_delete_file(conn):
    doc_id = make_document(conn)
    f = repo.add_file(conn, doc_id, "scan.pdf", "application/pdf", 42, "storage-1")
    assert f.filename == "scan.pdf"
    assert f.document_id == doc_id

    fetched = repo.get_file(conn, f.id)
    assert fetched == f

    key = repo.delete_file(conn, f.id)
    assert key == "storage-1"
    assert repo.get_file(conn, f.id) is None


def test_delete_file_missing_returns_none(conn):
    assert repo.delete_file(conn, 999) is None


def test_get_document_files_sorted_by_id(conn):
    doc_id = make_document(conn)
    f2 = repo.add_file(conn, doc_id, "b.pdf", "application/pdf", 1, "k2")
    f1 = repo.add_file(conn, doc_id, "a.pdf", "application/pdf", 1, "k1")

    doc = repo.get_document(conn, doc_id)
    assert [f.id for f in doc.files] == sorted([f1.id, f2.id])


def test_search_filter_by_person_is_or_within_group(conn):
    alice = repo.create_entry(conn, "persons", "Alice")
    bob = repo.create_entry(conn, "persons", "Bob")
    carol = repo.create_entry(conn, "persons", "Carol")

    doc_alice = make_document(conn, person_ids=[alice.id], title="doc-alice")
    doc_bob = make_document(conn, person_ids=[bob.id], title="doc-bob")
    doc_carol = make_document(conn, person_ids=[carol.id], title="doc-carol")

    results = repo.search_documents(conn, DocumentFilter(person_ids=[alice.id, bob.id]), date.today())
    ids = {d.id for d in results}
    assert ids == {doc_alice, doc_bob}
    assert doc_carol not in ids


def test_search_filter_by_tag(conn):
    tag1 = repo.create_entry(conn, "tags", "виза")
    tag2 = repo.create_entry(conn, "tags", "медицина")
    doc1 = make_document(conn, tag_ids=[tag1.id], title="doc1")
    doc2 = make_document(conn, tag_ids=[tag2.id], title="doc2")

    results = repo.search_documents(conn, DocumentFilter(tag_ids=[tag1.id]), date.today())
    assert [d.id for d in results] == [doc1]
    assert doc2 not in [d.id for d in results]


def test_search_filter_by_language(conn):
    ru = repo.create_entry(conn, "languages", "русский")
    en = repo.create_entry(conn, "languages", "английский")
    doc_ru = make_document(conn, language_ids=[ru.id], title="ru-doc")
    doc_en = make_document(conn, language_ids=[en.id], title="en-doc")

    results = repo.search_documents(conn, DocumentFilter(language_ids=[en.id]), date.today())
    assert [d.id for d in results] == [doc_en]
    assert doc_ru not in [d.id for d in results]


def test_search_filter_by_query_substring_case_insensitive(conn):
    doc1 = make_document(conn, title="Foreign Passport", notes="", doc_number="", issuer="")
    doc2 = make_document(conn, title="Something else", notes="passport copy", doc_number="", issuer="")
    doc3 = make_document(conn, title="Unrelated", notes="", doc_number="", issuer="")

    results = repo.search_documents(conn, DocumentFilter(query="PASSPORT"), date.today())
    ids = {d.id for d in results}
    assert ids == {doc1, doc2}
    assert doc3 not in ids


def test_search_empty_query_does_not_filter(conn):
    doc_id = make_document(conn)
    results = repo.search_documents(conn, DocumentFilter(query=""), date.today())
    assert doc_id in [d.id for d in results]


def test_search_filter_combination_is_and_between_groups(conn):
    alice = repo.create_entry(conn, "persons", "Alice")
    bob = repo.create_entry(conn, "persons", "Bob")
    tag = repo.create_entry(conn, "tags", "виза")

    doc_match = make_document(conn, person_ids=[alice.id], tag_ids=[tag.id], title="match")
    doc_wrong_person = make_document(conn, person_ids=[bob.id], tag_ids=[tag.id], title="wrong-person")
    doc_no_tag = make_document(conn, person_ids=[alice.id], title="no-tag")

    results = repo.search_documents(
        conn, DocumentFilter(person_ids=[alice.id], tag_ids=[tag.id]), date.today()
    )
    assert [d.id for d in results] == [doc_match]
    ids = {d.id for d in results}
    assert doc_wrong_person not in ids
    assert doc_no_tag not in ids


def test_search_expiring_within_days_includes_overdue(conn):
    today = date(2026, 8, 19)
    doc_overdue = make_document(conn, title="overdue", expires_at=today - timedelta(days=5))
    doc_soon = make_document(conn, title="soon", expires_at=today + timedelta(days=3))
    doc_far = make_document(conn, title="far", expires_at=today + timedelta(days=100))
    doc_none = make_document(conn, title="none", expires_at=None)

    results = repo.search_documents(conn, DocumentFilter(expiring_within_days=10), today)
    ids = {d.id for d in results}
    assert ids == {doc_overdue, doc_soon}
    assert doc_far not in ids
    assert doc_none not in ids


def test_search_expiring_within_days_sorted_ascending(conn):
    today = date(2026, 8, 19)
    doc_later = make_document(conn, title="later", expires_at=today + timedelta(days=9))
    doc_sooner = make_document(conn, title="sooner", expires_at=today + timedelta(days=1))

    results = repo.search_documents(conn, DocumentFilter(expiring_within_days=30), today)
    assert [d.id for d in results] == [doc_sooner, doc_later]


def test_search_default_sort_is_created_at_desc(conn):
    doc1 = make_document(conn, title="first")
    doc2 = make_document(conn, title="second")
    # force distinct timestamps: two creations can land in the same second otherwise
    conn.execute("UPDATE documents SET created_at = '2020-01-01 00:00:00' WHERE id = ?", (doc1,))
    conn.execute("UPDATE documents SET created_at = '2020-01-02 00:00:00' WHERE id = ?", (doc2,))
    conn.commit()

    results = repo.search_documents(conn, DocumentFilter(), date.today())
    assert [d.id for d in results] == [doc2, doc1]


def test_search_no_filters_returns_all_with_relations(conn):
    person = repo.create_entry(conn, "persons", "Alice")
    doc_id = make_document(conn, person_ids=[person.id])
    results = repo.search_documents(conn, DocumentFilter(), date.today())
    assert len(results) == 1
    assert results[0].id == doc_id
    assert [p.name for p in results[0].persons] == ["Alice"]
