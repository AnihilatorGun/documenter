import pytest
from cryptography.fernet import Fernet

from documenter import invite, local_state
from documenter.config import settings


@pytest.fixture(autouse=True)
def clean_local_state():
    local_state.PATH.unlink(missing_ok=True)


def _set_owner_settings(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "owner_email", "owner@example.com")
    monkeypatch.setattr(settings, "allowed_emails", ["wife@example.com", "mom@example.com"])
    monkeypatch.setattr(settings, "drive_folder_name", "Documenter")


def test_create_then_apply_round_trip(tmp_path, monkeypatch):
    _set_owner_settings(monkeypatch)
    local_state.update(drive_refresh_token="refresh-token-123")

    blob, key = invite.create()
    assert isinstance(blob, str)
    assert isinstance(key, str)

    local_state.PATH.unlink()  # simulate the second computer, which has no state yet

    invite.apply(blob, key, root=tmp_path)

    env_text = (tmp_path / ".env").read_text()
    assert "GOOGLE_CLIENT_ID=client-id" in env_text
    assert "GOOGLE_CLIENT_SECRET=client-secret" in env_text
    assert "OWNER_EMAIL=owner@example.com" in env_text
    assert "ALLOWED_EMAILS=wife@example.com,mom@example.com" in env_text
    assert "DRIVE_FOLDER_NAME=Documenter" in env_text
    assert "STORAGE=drive" in env_text

    assert local_state.load()["drive_refresh_token"] == "refresh-token-123"


def test_apply_writes_fresh_session_secret(tmp_path, monkeypatch):
    _set_owner_settings(monkeypatch)
    local_state.update(drive_refresh_token="refresh-token-123")
    blob, key = invite.create()

    invite.apply(blob, key, root=tmp_path)
    env_text = (tmp_path / ".env").read_text()

    secret_line = next(line for line in env_text.splitlines() if line.startswith("SESSION_SECRET="))
    secret = secret_line.split("=", 1)[1]
    assert secret
    assert secret != "change-me"
    assert secret != "dev-secret"


def test_apply_rejects_wrong_key(tmp_path, monkeypatch):
    _set_owner_settings(monkeypatch)
    local_state.update(drive_refresh_token="refresh-token-123")
    blob, _key = invite.create()

    wrong_key = Fernet.generate_key().decode()
    with pytest.raises(invite.InviteError):
        invite.apply(blob, wrong_key, root=tmp_path)


def test_apply_rejects_corrupted_blob(tmp_path, monkeypatch):
    _set_owner_settings(monkeypatch)
    local_state.update(drive_refresh_token="refresh-token-123")
    _blob, key = invite.create()

    with pytest.raises(invite.InviteError):
        invite.apply("not-a-valid-fernet-token", key, root=tmp_path)


def test_create_fails_without_drive_token(monkeypatch):
    _set_owner_settings(monkeypatch)
    # no local_state.update: no drive_refresh_token saved

    with pytest.raises(invite.InviteError):
        invite.create()


def test_apply_refuses_when_env_already_configured(tmp_path, monkeypatch):
    _set_owner_settings(monkeypatch)
    local_state.update(drive_refresh_token="refresh-token-123")
    blob, key = invite.create()

    (tmp_path / ".env").write_text("GOOGLE_CLIENT_ID=already-configured\n")

    with pytest.raises(invite.InviteError):
        invite.apply(blob, key, root=tmp_path)
