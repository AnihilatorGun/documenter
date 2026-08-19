import socket
import threading
import time
import webbrowser

import uvicorn

from documenter.config import settings

# Google returns the user only to an address registered in its console, so the port
# cannot be arbitrary: these four are the ones registered there.
PORTS = (8000, 8001, 8002, 8003)


def _taken(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _first_free_port() -> int:
    for port in PORTS:
        if not _taken(port):
            return port
    raise SystemExit(
        f"Порты {', '.join(str(p) for p in PORTS)} заняты другими программами.\n"
        "Закройте лишнее и запустите Documenter снова."
    )


def _open_browser_once_listening(url: str, port: int) -> None:
    for _ in range(100):
        if _taken(port):
            webbrowser.open(url)
            return
        time.sleep(0.1)


def main() -> None:
    port = _first_free_port()
    settings.base_url = f"http://localhost:{port}"
    threading.Thread(
        target=_open_browser_once_listening, args=(settings.base_url, port), daemon=True
    ).start()
    print(f"Documenter работает: {settings.base_url}", flush=True)
    print("Чтобы остановить — закройте это окно или нажмите Ctrl+C.", flush=True)
    uvicorn.run("documenter.app:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
