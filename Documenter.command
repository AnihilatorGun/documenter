#!/usr/bin/env bash
set -euo pipefail

# Переходим в папку, где лежит сам ярлык — иначе двойной клик из Finder
# стартует сервер из домашней папки, и uv не найдёт проект
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PATH="$HOME/.local/bin:$PATH"

# Открываем браузер отдельно, с задержкой — чтобы сервер успел подняться
( sleep 2 && open "http://localhost:8000" ) &

echo "Запускаем Documenter..."
echo "Приложение работает. Чтобы остановить — закройте это окно или нажмите Ctrl+C."
echo ""

uv run uvicorn documenter.app:app --port 8000
