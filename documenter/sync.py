import sqlite3
import sys
import tempfile
from pathlib import Path

from documenter import local_state

INDEX_FILENAME = "documenter-index.db"
INDEX_MIME = "application/x-sqlite3"


def _snapshot(conn: sqlite3.Connection) -> bytes:
    # Reading the .db file directly can capture half of a transaction.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshot.db"
        destination = sqlite3.connect(path)
        with destination:
            conn.backup(destination)
        destination.close()
        return path.read_bytes()


def pull(storage, db_path: str) -> str:
    """Fetch the index from Drive before the app opens it. Returns a message for the user, or ''."""
    try:
        key = storage.find_by_name(INDEX_FILENAME)
        if key is None:
            local_state.update(sync_ready=True, index_key=None, index_version=None)
            return ""
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(db_path).write_bytes(storage.download(key))
        local_state.update(sync_ready=True, index_key=key, index_version=storage.version(key))
        return ""
    except Exception as error:
        # Pushing over an index we failed to read would erase someone else's work.
        local_state.update(sync_ready=False)
        print(f"sync.pull: {error}", file=sys.stderr)
        return "Не удалось связаться с Google Диском. Работаем с локальной копией, изменения не уедут."


def push(conn: sqlite3.Connection, storage) -> str:
    state = local_state.load()
    if not state.get("sync_ready"):
        return "Изменения сохранены только на этом компьютере: связи с Google Drive нет."

    key = state.get("index_key")
    warning = ""
    try:
        if key is None:
            key = storage.upload(INDEX_FILENAME, INDEX_MIME, _snapshot(conn))
        else:
            if storage.version(key) != state.get("index_version"):
                warning = (
                    "База в Drive менялась на другом устройстве. Ваши изменения записаны поверх, "
                    "прежнюю версию можно достать из истории версий файла в Drive."
                )
            storage.replace(key, INDEX_MIME, _snapshot(conn))
        local_state.update(index_key=key, index_version=storage.version(key))
        return warning
    except Exception as error:
        print(f"sync.push: {error}", file=sys.stderr)
        return "Не удалось сохранить изменения в Google Диске. Пока они только на этом компьютере."


def enable_after_login(storage) -> str:
    """The first login brings the credential that the startup pull did not have yet."""
    if local_state.load().get("sync_ready"):
        return ""
    try:
        key = storage.find_by_name(INDEX_FILENAME)
    except Exception as error:
        print(f"sync.enable_after_login: {error}", file=sys.stderr)
        return "Google Диск недоступен. Изменения останутся на этом компьютере."
    if key is not None:
        return "В Drive уже есть база документов. Перезапустите приложение, чтобы загрузить её."
    local_state.update(sync_ready=True, index_key=None, index_version=None)
    return ""


def refresh(conn: sqlite3.Connection, storage) -> str:
    """Pick up edits made from another computer."""
    state = local_state.load()
    key = state.get("index_key")
    if not state.get("sync_ready") or key is None:
        return ""
    try:
        remote_version = storage.version(key)
        if remote_version == state.get("index_version"):
            return ""
        data = storage.download(key)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incoming.db"
            path.write_bytes(data)
            incoming = sqlite3.connect(path)
            # Copying into the live connection keeps already-open cursors valid.
            incoming.backup(conn)
            incoming.close()
        local_state.update(index_version=remote_version)
        return ""
    except Exception as error:
        print(f"sync.refresh: {error}", file=sys.stderr)
        return "Не удалось проверить изменения в Google Диске."
