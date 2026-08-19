from dataclasses import dataclass, field
from datetime import date, datetime

LANGUAGES = {"ru": "русский", "pl": "польский", "en": "английский"}

DEFAULT_TAGS = ["виза", "медицина", "ИП", "учёба", "налоги", "легализация"]


@dataclass
class Person:
    id: int
    name: str


@dataclass
class Tag:
    id: int
    name: str


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
    persons: list[Person] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    files: list[StoredFile] = field(default_factory=list)

    def days_until_expiry(self, today: date) -> int | None:
        return None if self.expires_at is None else (self.expires_at - today).days


@dataclass
class DocumentInput:
    """What a create/update form submits. Ids refer to existing persons and tags."""

    title: str
    person_ids: list[int] = field(default_factory=list)
    tag_ids: list[int] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    doc_number: str = ""
    issuer: str = ""
    doc_date: date | None = None
    expires_at: date | None = None
    notes: str = ""


@dataclass
class DocumentFilter:
    person_ids: list[int] = field(default_factory=list)
    tag_ids: list[int] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    query: str = ""
    expiring_within_days: int | None = None
