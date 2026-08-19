import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from documenter.drive import DriveStorage
from documenter.google_oauth import (
    SCOPES,
    GoogleUser,
    build_auth_url,
    exchange_code,
    fetch_access_token,
)


def test_build_auth_url_contains_key_params():
    url = build_auth_url("client-id", "https://app.example/auth/callback", "state-123")
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"

    params = parse_qs(parsed.query)
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://app.example/auth/callback"]
    assert params["response_type"] == ["code"]
    assert params["scope"] == [" ".join(SCOPES)]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["include_granted_scopes"] == ["true"]
    assert params["state"] == ["state-123"]


def test_exchange_code_calls_both_endpoints_and_builds_user():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/token":
            body = parse_qs(request.content.decode())
            assert body["grant_type"] == ["authorization_code"]
            assert body["code"] == ["auth-code"]
            assert body["client_id"] == ["client-id"]
            assert body["client_secret"] == ["client-secret"]
            assert body["redirect_uri"] == ["https://app.example/auth/callback"]
            return httpx.Response(
                200,
                json={"access_token": "access-tok", "refresh_token": "refresh-tok"},
            )
        assert request.url.path == "/oauth2/v2/userinfo"
        assert request.headers["Authorization"] == "Bearer access-tok"
        return httpx.Response(200, json={"email": "a@b.com", "name": "A B"})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    user = exchange_code(
        "client-id",
        "client-secret",
        "https://app.example/auth/callback",
        "auth-code",
        client=client,
    )

    assert user == GoogleUser(email="a@b.com", name="A B", refresh_token="refresh-tok")
    assert len(calls) == 2


def test_exchange_code_without_refresh_token_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "access-tok"})
        return httpx.Response(200, json={"email": "a@b.com", "name": "A B"})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    user = exchange_code(
        "client-id", "client-secret", "https://app.example/auth/callback", "auth-code", client=client
    )

    assert user.refresh_token is None


def test_exchange_code_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.HTTPStatusError):
        exchange_code("client-id", "client-secret", "https://app.example/cb", "bad-code", client=client)


def test_fetch_access_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/token"
        body = parse_qs(request.content.decode())
        assert body["grant_type"] == ["refresh_token"]
        assert body["refresh_token"] == ["refresh-tok"]
        return httpx.Response(200, json={"access_token": "fresh-access-tok"})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    token = fetch_access_token("client-id", "client-secret", "refresh-tok", client=client)

    assert token == "fresh-access-tok"


class DriveFake:
    """Records requests and plays a Drive backend: no folder exists yet, one file."""

    def __init__(self):
        self.folder_created = False
        self.list_calls = 0
        self.create_calls = 0
        self.uploaded_files = {}
        self.deleted = []
        self.find_queries = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"

        if request.url.path == "/drive/v3/files" and request.method == "GET":
            query = request.url.params["q"]
            if "mimeType=" in query:
                self.list_calls += 1
                assert "name='Documenter'" in query
                assert "mimeType='application/vnd.google-apps.folder'" in query
                assert "trashed=false" in query
                if self.folder_created:
                    return httpx.Response(200, json={"files": [{"id": "folder-1"}]})
                return httpx.Response(200, json={"files": []})

            # find_by_name: query is against files, not folders
            self.find_queries.append(query)
            matches = [
                key for key, f in self.uploaded_files.items() if f"name='{f['name']}'" in query
            ]
            return httpx.Response(200, json={"files": [{"id": matches[0]}] if matches else []})

        if request.url.path == "/drive/v3/files" and request.method == "POST":
            self.create_calls += 1
            payload = json.loads(request.content)
            assert payload == {"name": "Documenter", "mimeType": "application/vnd.google-apps.folder"}
            self.folder_created = True
            return httpx.Response(200, json={"id": "folder-1"})

        if request.url.path == "/upload/drive/v3/files" and request.method == "POST":
            assert request.url.params["uploadType"] == "multipart"
            content_type = request.headers["Content-Type"]
            assert content_type.startswith("multipart/related; boundary=")
            boundary = content_type.split("boundary=")[1].encode()
            parts = request.content.split(b"--" + boundary)
            metadata_part = parts[1]
            metadata_json = metadata_part.split(b"\r\n\r\n", 1)[1].strip()
            metadata = json.loads(metadata_json)
            assert metadata["parents"] == ["folder-1"]
            file_id = f"file-{len(self.uploaded_files) + 1}"
            # the file part ends with "\r\n" right before the closing boundary marker
            file_data = parts[2].split(b"\r\n\r\n", 1)[1].removesuffix(b"\r\n")
            self.uploaded_files[file_id] = {"name": metadata["name"], "data": file_data, "version": "1"}
            return httpx.Response(200, json={"id": file_id})

        if request.url.path.startswith("/upload/drive/v3/files/") and request.method == "PATCH":
            assert request.url.params["uploadType"] == "media"
            file_id = request.url.path.rsplit("/", 1)[-1]
            self.uploaded_files[file_id]["mime_type"] = request.headers["Content-Type"]
            self.uploaded_files[file_id]["data"] = request.content
            return httpx.Response(200, json={"id": file_id})

        if request.url.path.startswith("/drive/v3/files/") and request.method == "GET":
            file_id = request.url.path.rsplit("/", 1)[-1]
            if request.url.params.get("fields") == "version":
                return httpx.Response(200, json={"version": self.uploaded_files[file_id]["version"]})
            assert request.url.params["alt"] == "media"
            return httpx.Response(200, content=self.uploaded_files[file_id]["data"])

        if request.url.path.startswith("/drive/v3/files/") and request.method == "DELETE":
            file_id = request.url.path.rsplit("/", 1)[-1]
            self.deleted.append(file_id)
            return httpx.Response(204)

        raise AssertionError(f"unexpected request: {request.method} {request.url}")


def make_storage(fake: DriveFake) -> DriveStorage:
    client = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return DriveStorage(lambda: "test-token", "Documenter", client=client)


def test_upload_creates_folder_then_reuses_cached_id():
    fake = DriveFake()
    storage = make_storage(fake)

    file_id_1 = storage.upload("a.txt", "text/plain", b"hello world")
    assert fake.list_calls == 1
    assert fake.create_calls == 1
    assert storage._folder_id == "folder-1"

    file_id_2 = storage.upload("b.txt", "text/plain", b"second file")
    # cached folder id means no further files.list/files.create calls
    assert fake.list_calls == 1
    assert fake.create_calls == 1

    assert fake.uploaded_files[file_id_1]["data"] == b"hello world"
    assert fake.uploaded_files[file_id_2]["data"] == b"second file"


def test_upload_reuses_existing_folder_without_creating():
    fake = DriveFake()
    fake.folder_created = True
    storage = make_storage(fake)

    storage.upload("a.txt", "text/plain", b"hello")

    assert fake.list_calls == 1
    assert fake.create_calls == 0


def test_download():
    fake = DriveFake()
    storage = make_storage(fake)
    file_id = storage.upload("a.txt", "text/plain", b"payload")

    assert storage.download(file_id) == b"payload"


def test_delete():
    fake = DriveFake()
    storage = make_storage(fake)
    file_id = storage.upload("a.txt", "text/plain", b"payload")

    storage.delete(file_id)

    assert fake.deleted == [file_id]


def test_external_link():
    fake = DriveFake()
    storage = make_storage(fake)

    assert storage.external_link("some-id") == "https://drive.google.com/file/d/some-id/view"


def test_find_by_name_returns_id_when_present():
    fake = DriveFake()
    storage = make_storage(fake)
    file_id = storage.upload("a.txt", "text/plain", b"hello")

    assert storage.find_by_name("a.txt") == file_id


def test_find_by_name_returns_none_when_no_match():
    fake = DriveFake()
    storage = make_storage(fake)
    storage.upload("a.txt", "text/plain", b"hello")

    assert storage.find_by_name("missing.txt") is None


def test_find_by_name_query_scopes_by_name_and_parent_folder():
    fake = DriveFake()
    fake.folder_created = True
    storage = make_storage(fake)

    storage.find_by_name("a.txt")

    assert len(fake.find_queries) == 1
    query = fake.find_queries[0]
    assert "name='a.txt'" in query
    assert "'folder-1' in parents" in query


def test_version_returns_version_field():
    fake = DriveFake()
    storage = make_storage(fake)
    file_id = storage.upload("a.txt", "text/plain", b"hello")
    fake.uploaded_files[file_id]["version"] = "42"

    assert storage.version(file_id) == "42"


def test_replace_patches_upload_endpoint_with_media_body_and_keeps_file_id():
    fake = DriveFake()
    storage = make_storage(fake)
    file_id = storage.upload("a.txt", "text/plain", b"old content")

    storage.replace(file_id, "text/plain", b"new content")

    assert fake.uploaded_files[file_id]["data"] == b"new content"
    assert set(fake.uploaded_files.keys()) == {file_id}
    assert storage.download(file_id) == b"new content"
