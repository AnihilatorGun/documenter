import json
from pathlib import Path

from documenter.config import settings

# The Drive credential must be readable before the index exists, so it cannot live inside it.
PATH = Path(settings.db_path).with_name("local_state.json")


def load() -> dict:
    return json.loads(PATH.read_text()) if PATH.exists() else {}


def update(**values) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(load() | values, indent=2))
