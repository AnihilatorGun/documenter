from dataclasses import dataclass, field
from datetime import date, datetime

# The three lists a document is filed under. They behave identically, so they share
# one table shape and one set of queries.
CATALOGS = ("persons", "tags", "languages")

DEFAULT_TAGS = ["виза", "медицина", "ИП", "учёба", "налоги", "легализация"]
DEFAULT_LANGUAGES = ["русский", "польский", "английский"]


@dataclass
class Entry:
    id: int
    name: str
    documents: int = 0


@dataclass
class StoredFile:
    id: int
    document_id: int
    filename: str
    mime_type: str
    size: int
    storage_key: str
    uploaded_at: datetime


@dataclass
class Document:
    id: int
    title: str
    doc_number: str
    issuer: str
    doc_date: date | None
    expires_at: date | None
    notes: str
    created_at: datetime
    created_by: str
    persons: list[Entry] = field(default_factory=list)
    tags: list[Entry] = field(default_factory=list)
    languages: list[Entry] = field(default_factory=list)
    files: list[StoredFile] = field(default_factory=list)

    def days_until_expiry(self, today: date) -> int | None:
        return None if self.expires_at is None else (self.expires_at - today).days


@dataclass
class DocumentInput:
    """What a create/update form submits. Ids refer to existing persons and tags."""

    title: str
    person_ids: list[int] = field(default_factory=list)
    tag_ids: list[int] = field(default_factory=list)
    language_ids: list[int] = field(default_factory=list)
    doc_number: str = ""
    issuer: str = ""
    doc_date: date | None = None
    expires_at: date | None = None
    notes: str = ""


@dataclass
class DocumentFilter:
    person_ids: list[int] = field(default_factory=list)
    tag_ids: list[int] = field(default_factory=list)
    language_ids: list[int] = field(default_factory=list)
    query: str = ""
    expiring_within_days: int | None = None
