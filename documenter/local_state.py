import json
from pathlib import Path

from documenter.config import settings

# Everything the machine needs BEFORE the database is available, so it cannot live inside it:
# the Drive credential is what lets us download the database in the first place.
PATH = Path(settings.db_path).with_name("local_state.json")


def load() -> dict:
    return json.loads(PATH.read_text()) if PATH.exists() else {}


def update(**values) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(load() | values, indent=2))
