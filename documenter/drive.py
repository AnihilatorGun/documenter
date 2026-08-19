import json
from typing import Callable

import httpx

API_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class DriveStorage:
    def __init__(
        self,
        get_access_token: Callable[[], str],
        folder_name: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._get_access_token = get_access_token
        self._folder_name = folder_name
        self._client = client or httpx.Client()
        self._folder_id: str | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def _folder(self) -> str:
        if self._folder_id is not None:
            return self._folder_id

        # With drive.file this query only ever sees folders the app created itself.
        query = (
            f"name='{self._folder_name}' and mimeType='{FOLDER_MIME_TYPE}' and trashed=false"
        )
        response = self._client.get(
            API_URL,
            headers=self._headers(),
            params={"q": query, "fields": "files(id)"},
        )
        response.raise_for_status()
        files = response.json()["files"]
        if files:
            self._folder_id = files[0]["id"]
            return self._folder_id

        response = self._client.post(
            API_URL,
            headers=self._headers(),
            json={"name": self._folder_name, "mimeType": FOLDER_MIME_TYPE},
        )
        response.raise_for_status()
        self._folder_id = response.json()["id"]
        return self._folder_id

    def upload(self, filename: str, mime_type: str, data: bytes) -> str:
        metadata = json.dumps({"name": filename, "parents": [self._folder()]})
        boundary = "documenter-boundary"
        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--".encode()

        headers = self._headers()
        headers["Content-Type"] = f"multipart/related; boundary={boundary}"
        response = self._client.post(
            UPLOAD_URL,
            headers=headers,
            params={"uploadType": "multipart"},
            content=body,
        )
        response.raise_for_status()
        return response.json()["id"]

    def find_by_name(self, filename: str) -> str | None:
        response = self._client.get(
            API_URL,
            headers=self._headers(),
            params={
                "q": f"name='{filename}' and '{self._folder()}' in parents and trashed=false",
                "fields": "files(id)",
            },
        )
        response.raise_for_status()
        files = response.json()["files"]
        return files[0]["id"] if files else None

    def version(self, key: str) -> str:
        response = self._client.get(
            f"{API_URL}/{key}", headers=self._headers(), params={"fields": "version"}
        )
        response.raise_for_status()
        return response.json()["version"]

    def replace(self, key: str, mime_type: str, data: bytes) -> None:
        # PATCH keeps the same file id, so Drive stores the old content as a revision.
        headers = self._headers()
        headers["Content-Type"] = mime_type
        response = self._client.patch(
            f"{UPLOAD_URL}/{key}",
            headers=headers,
            params={"uploadType": "media"},
            content=data,
        )
        response.raise_for_status()

    def download(self, key: str) -> bytes:
        response = self._client.get(
            f"{API_URL}/{key}",
            headers=self._headers(),
            params={"alt": "media"},
        )
        response.raise_for_status()
        return response.content

    def delete(self, key: str) -> None:
        response = self._client.delete(f"{API_URL}/{key}", headers=self._headers())
        response.raise_for_status()

    def external_link(self, key: str) -> str | None:
        return f"https://drive.google.com/file/d/{key}/view"
