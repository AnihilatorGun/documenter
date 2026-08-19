import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _emails(raw: str) -> list[str]:
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


@dataclass
class Settings:
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET", ""))
    owner_email: str = field(default_factory=lambda: os.getenv("OWNER_EMAIL", "").lower())
    allowed_emails: list[str] = field(default_factory=lambda: _emails(os.getenv("ALLOWED_EMAILS", "")))
    session_secret: str = field(default_factory=lambda: os.getenv("SESSION_SECRET", "dev-secret"))
    storage: str = field(default_factory=lambda: os.getenv("STORAGE", "local"))
    drive_folder_name: str = field(default_factory=lambda: os.getenv("DRIVE_FOLDER_NAME", "Documenter"))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/documenter.db"))
    local_files_dir: str = field(default_factory=lambda: os.getenv("LOCAL_FILES_DIR", "data/files"))
    base_url: str = field(default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000"))

    def may_log_in(self, email: str) -> bool:
        email = email.lower()
        return email == self.owner_email or email in self.allowed_emails

    @property
    def redirect_uri(self) -> str:
        return f"{self.base_url}/auth/callback"


settings = Settings()
