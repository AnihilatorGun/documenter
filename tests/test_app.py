import base64
import json

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from documenter.app import app
from documenter.config import settings


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def logged_in(client):
    payload = base64.b64encode(json.dumps({"email": settings.owner_email, "name": "Owner"}).encode())
    client.cookies.set("session", TimestampSigner(settings.session_secret).sign(payload).decode())
    return client


def test_anonymous_is_sent_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_renders(client):
    assert client.get("/login").status_code == 200


def test_document_lifecycle(logged_in):
    assert logged_in.get("/").status_code == 200
    assert logged_in.get("/documents/new").status_code == 200

    response = logged_in.post(
        "/documents",
        data={
            "title": "Карта побыту",
            "new_person": "Никита",
            "new_tag": "легализация",
            "lang": ["pl", "ru"],
            "doc_number": "ABC123",
            "expires_at": "2030-01-01",
            "notes": "лежит в синей папке",
        },
        files={"files": ("scan.pdf", b"%PDF-fake", "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    document_url = response.headers["location"]

    page = logged_in.get(document_url)
    assert page.status_code == 200
    assert "Карта побыту" in page.text
    assert "Никита" in page.text

    assert logged_in.get(f"{document_url}/edit").status_code == 200
    assert logged_in.get("/?q=синей").text.count("Карта побыту") == 1
    assert "Карта побыту" not in logged_in.get("/?q=такого+нет").text

    download = logged_in.get("/files/1")
    assert download.content == b"%PDF-fake"

    assert logged_in.post("/files/1/delete", follow_redirects=False).status_code == 303
    assert logged_in.post(f"{document_url}/delete", follow_redirects=False).status_code == 303
    assert logged_in.get(document_url, follow_redirects=False).status_code == 303


def test_local_door_works_while_google_is_not_configured(client):
    response = client.get("/auth/local", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert client.get("/").status_code == 200


def test_setup_page_is_reachable_without_logging_in(client):
    assert client.get("/setup").status_code == 200


def setup_token(client):
    page = client.get("/setup").text
    return page.split('name="token" value="')[1].split('"')[0]


def test_setup_rejects_nonsense_with_a_message(client):
    response = client.post(
        "/setup",
        data={"blob": "не приглашение", "key": "не ключ", "token": setup_token(client)},
    )
    assert response.status_code == 200
    assert 'class="error"' in response.text


def test_setup_refuses_a_form_that_did_not_come_from_its_own_page(client):
    response = client.post("/setup", data={"blob": "что угодно", "key": "что угодно"})
    assert "Страница устарела" in response.text


def test_invite_page_needs_a_login(client):
    response = client.get("/invite", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_owner_sees_the_invite_page(logged_in):
    assert logged_in.get("/invite").status_code == 200


def test_invite_creation_explains_itself_when_drive_is_not_connected(logged_in):
    response = logged_in.post("/invite")
    assert response.status_code == 200
    assert "error" in response.text
