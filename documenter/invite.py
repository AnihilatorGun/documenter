import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from documenter import local_state
from documenter.config import settings

PROJECT_ROOT = Path(__file__).parent.parent


class InviteError(Exception):
    pass


def create() -> tuple[str, str]:
    token = local_state.load().get("drive_refresh_token")
    if not token or not settings.google_client_id:
        raise InviteError(
            "Нет доступа к Google Drive на этом компьютере: сначала войдите в приложение и подключите Drive."
        )

    payload = {
        "google_client_id": settings.google_client_id,
        "google_client_secret": settings.google_client_secret,
        "owner_email": settings.owner_email,
        "allowed_emails": ",".join(settings.allowed_emails),
        "drive_folder_name": settings.drive_folder_name,
        "drive_refresh_token": token,
    }

    key = Fernet.generate_key()
    blob = Fernet(key).encrypt(json.dumps(payload).encode())
    return blob.decode(), key.decode()


def apply(blob: str, key: str, root: Path = PROJECT_ROOT) -> None:
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GOOGLE_CLIENT_ID=") and line.split("=", 1)[1].strip():
                raise InviteError("Приложение уже настроено: файл .env уже содержит GOOGLE_CLIENT_ID.")

    try:
        payload = json.loads(Fernet(key.encode()).decrypt(blob.encode()))
    except (InvalidToken, ValueError):
        raise InviteError("Не удалось разобрать приглашение: неверный ключ или повреждённая строка приглашения.")

    env_path.write_text(
        "GOOGLE_CLIENT_ID={google_client_id}\n"
        "GOOGLE_CLIENT_SECRET={google_client_secret}\n"
        "\n"
        "OWNER_EMAIL={owner_email}\n"
        "\n"
        "ALLOWED_EMAILS={allowed_emails}\n"
        "\n"
        "SESSION_SECRET={session_secret}\n"
        "\n"
        "STORAGE=drive\n"
        "DRIVE_FOLDER_NAME={drive_folder_name}\n"
        "\n"
        "DB_PATH=data/documenter.db\n"
        "LOCAL_FILES_DIR=data/files\n"
        "BASE_URL=http://localhost:8000\n".format(
            session_secret=secrets.token_urlsafe(32),
            **payload,
        )
    )

    local_state.update(drive_refresh_token=payload["drive_refresh_token"])
