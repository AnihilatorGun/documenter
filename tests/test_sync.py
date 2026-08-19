import sqlite3

import pytest

from documenter import local_state, sync
from documenter.db import connect, init_db


@pytest.fixture(autouse=True)
def clean_local_state():
    # local_state.PATH lives next to the (shared, per-session) test DB_PATH, so tests
    # must not depend on leftover state written by a previous test.
    local_state.PATH.unlink(missing_ok=True)


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


class FakeDrive:
    """In-memory stand-in for DriveStorage: one named file, versions bump on write."""

    def __init__(self):
        self.files = {}
        self._next_id = 1
        self._failures = {}

    def fail(self, method, error=None):
        self._failures[method] = error or RuntimeError(f"{method} unavailable")

    def _check(self, method):
        if method in self._failures:
            raise self._failures[method]

    def find_by_name(self, filename):
        self._check("find_by_name")
        for key, file in self.files.items():
            if file["name"] == filename:
                return key
        return None

    def version(self, key):
        self._check("version")
        return self.files[key]["version"]

    def upload(self, filename, mime_type, data):
        self._check("upload")
        key = f"file-{self._next_id}"
        self._next_id += 1
        self.files[key] = {"name": filename, "mime_type": mime_type, "data": data, "version": "1"}
        return key

    def replace(self, key, mime_type, data):
        self._check("replace")
        file = self.files[key]
        file["mime_type"] = mime_type
        file["data"] = data
        file["version"] = str(int(file["version"]) + 1)

    def download(self, key):
        self._check("download")
        return self.files[key]["data"]


def add_row(conn, name):
    conn.execute("INSERT INTO persons (name) VALUES (?)", (name,))
    conn.commit()


def person_names(db_path):
    fetched = sqlite3.connect(db_path)
    try:
        return [row[0] for row in fetched.execute("SELECT name FROM persons")]
    finally:
        fetched.close()


def test_pull_downloads_existing_index_and_records_state(tmp_path):
    drive = FakeDrive()
    seed = connect(str(tmp_path / "seed.db"))
    init_db(seed)
    add_row(seed, "Alice")
    key = drive.upload(sync.INDEX_FILENAME, sync.INDEX_MIME, sync._snapshot(seed))

    db_path = tmp_path / "local.db"
    message = sync.pull(drive, str(db_path))

    assert message == ""
    assert person_names(db_path) == ["Alice"]
    state = local_state.load()
    assert state["sync_ready"] is True
    assert state["index_key"] == key
    assert state["index_version"] == drive.version(key)


def test_pull_without_existing_index_marks_ready_with_no_key(tmp_path):
    drive = FakeDrive()

    message = sync.pull(drive, str(tmp_path / "local.db"))

    assert message == ""
    state = local_state.load()
    assert state["sync_ready"] is True
    assert state["index_key"] is None
    assert not (tmp_path / "local.db").exists()


def test_pull_failure_disables_sync_and_returns_message(tmp_path):
    drive = FakeDrive()
    drive.fail("find_by_name")

    message = sync.pull(drive, str(tmp_path / "local.db"))

    assert message != ""
    assert local_state.load()["sync_ready"] is False


def test_pull_failure_while_downloading_also_disables_sync(tmp_path):
    drive = FakeDrive()
    drive.upload(sync.INDEX_FILENAME, sync.INDEX_MIME, b"remote index")
    drive.fail("download")

    message = sync.pull(drive, str(tmp_path / "local.db"))

    assert message != ""
    assert local_state.load()["sync_ready"] is False


def test_push_refuses_after_a_failed_pull(tmp_path, conn):
    drive = FakeDrive()
    drive.fail("find_by_name")
    sync.pull(drive, str(tmp_path / "local.db"))

    message = sync.push(conn, drive)

    assert message != ""
    assert drive.files == {}


def test_push_without_sync_ready_does_not_upload(conn):
    drive = FakeDrive()

    message = sync.push(conn, drive)

    assert message != ""
    assert drive.files == {}


def test_push_creates_file_when_no_index_key_yet(conn):
    local_state.update(sync_ready=True, index_key=None, index_version=None)
    drive = FakeDrive()

    message = sync.push(conn, drive)

    assert message == ""
    state = local_state.load()
    assert state["index_key"] in drive.files
    assert state["index_version"] == drive.version(state["index_key"])


def test_push_replaces_file_when_remote_version_matches(conn):
    drive = FakeDrive()
    key = drive.upload(sync.INDEX_FILENAME, sync.INDEX_MIME, b"stale")
    local_state.update(sync_ready=True, index_key=key, index_version=drive.version(key))

    add_row(conn, "Bob")
    message = sync.push(conn, drive)

    assert message == ""
    assert drive.files[key]["data"] != b"stale"
    assert local_state.load()["index_version"] == drive.version(key)


def test_push_warns_but_still_overwrites_when_remote_version_changed(conn):
    drive = FakeDrive()
    key = drive.upload(sync.INDEX_FILENAME, sync.INDEX_MIME, b"stale")
    local_state.update(sync_ready=True, index_key=key, index_version=drive.version(key))
    # simulate another device editing the file after our copy of the version was recorded
    drive.replace(key, sync.INDEX_MIME, b"edited elsewhere")

    add_row(conn, "Carol")
    message = sync.push(conn, drive)

    assert message != ""
    assert drive.files[key]["data"] != b"edited elsewhere"
    assert local_state.load()["index_version"] == drive.version(key)


def test_push_failure_returns_message_and_does_not_raise(conn):
    local_state.update(sync_ready=True, index_key=None, index_version=None)
    drive = FakeDrive()
    drive.fail("upload")

    message = sync.push(conn, drive)

    assert message != ""


def test_push_uploads_a_valid_sqlite_snapshot(conn, tmp_path):
    local_state.update(sync_ready=True, index_key=None, index_version=None)
    drive = FakeDrive()
    add_row(conn, "Dana")

    sync.push(conn, drive)

    key = local_state.load()["index_key"]
    snapshot_path = tmp_path / "snapshot.db"
    snapshot_path.write_bytes(drive.files[key]["data"])
    assert person_names(str(snapshot_path)) == ["Dana"]


def test_enable_after_login_is_noop_when_already_ready():
    local_state.update(sync_ready=True, index_key="existing", index_version="7")
    drive = FakeDrive()

    message = sync.enable_after_login(drive)

    assert message == ""
    assert local_state.load()["index_key"] == "existing"


def test_enable_after_login_enables_sync_when_drive_has_no_index():
    drive = FakeDrive()

    message = sync.enable_after_login(drive)

    assert message == ""
    assert local_state.load()["sync_ready"] is True


def test_enable_after_login_does_not_enable_when_drive_already_has_index():
    drive = FakeDrive()
    drive.upload(sync.INDEX_FILENAME, sync.INDEX_MIME, b"data")

    message = sync.enable_after_login(drive)

    assert message != ""
    assert local_state.load().get("sync_ready") is not True


def names_in(conn):
    return [row[0] for row in conn.execute("SELECT name FROM persons")]


def test_refresh_does_nothing_when_drive_version_is_unchanged(tmp_path, conn):
    drive = FakeDrive()
    add_row(conn, "Alice")
    sync.pull(drive, str(tmp_path / "local.db"))
    sync.push(conn, drive)
    drive.fail("download")

    assert sync.refresh(conn, drive) == ""
    assert names_in(conn) == ["Alice"]


def test_refresh_brings_in_edits_made_elsewhere(tmp_path, conn):
    drive = FakeDrive()
    add_row(conn, "Alice")
    sync.pull(drive, str(tmp_path / "local.db"))
    sync.push(conn, drive)

    elsewhere = connect(str(tmp_path / "other.db"))
    init_db(elsewhere)
    add_row(elsewhere, "Bob")
    drive.replace(local_state.load()["index_key"], sync.INDEX_MIME, sync._snapshot(elsewhere))

    assert sync.refresh(conn, drive) == ""
    assert names_in(conn) == ["Bob"]
    assert local_state.load()["index_version"] == drive.version(local_state.load()["index_key"])


def test_refresh_reports_drive_failure_without_raising(tmp_path, conn):
    drive = FakeDrive()
    sync.pull(drive, str(tmp_path / "local.db"))
    sync.push(conn, drive)
    drive.fail("version")

    assert sync.refresh(conn, drive) != ""


def test_refresh_is_a_no_op_before_the_first_push(tmp_path, conn):
    drive = FakeDrive()
    sync.pull(drive, str(tmp_path / "local.db"))
    drive.fail("version")

    assert sync.refresh(conn, drive) == ""
