from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = ["openid", "email", "profile", "https://www.googleapis.com/auth/drive.file"]


@dataclass
class GoogleUser:
    email: str
    name: str
    refresh_token: str | None
    # Google lets the user untick individual permissions, so what was asked for
    # and what was granted are not the same thing.
    granted_scopes: list[str] = field(default_factory=list)


def build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        # prompt=consent forces Google to reissue a refresh_token even for a user
        # who already granted access before; without it a repeat login omits it.
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    client: httpx.Client | None = None,
) -> GoogleUser:
    http = client or httpx.Client()
    try:
        token_response = http.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()

        userinfo_response = http.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

        return GoogleUser(
            email=userinfo["email"],
            name=userinfo.get("name", ""),
            refresh_token=token_data.get("refresh_token"),
            granted_scopes=token_data.get("scope", "").split(),
        )
    finally:
        if client is None:
            http.close()


def fetch_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    client: httpx.Client | None = None,
) -> str:
    http = client or httpx.Client()
    try:
        response = http.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]
    finally:
        if client is None:
            http.close()
