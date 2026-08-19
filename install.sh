#!/usr/bin/env bash
set -euo pipefail

# Папка, где лежит этот скрипт, — она же корень проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Устанавливаем Documenter..."

if ! command -v uv >/dev/null 2>&1; then
    echo "Менеджер пакетов uv не найден, устанавливаем..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Сразу после установки uv может быть недоступен в PATH этой сессии терминала
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "Не удалось найти uv после установки." >&2
    echo "Откройте новое окно терминала и запустите install.sh ещё раз." >&2
    exit 1
fi

echo "Устанавливаем Python и зависимости проекта (это может занять минуту)..."
uv sync

chmod +x "$SCRIPT_DIR/Documenter.command"

echo ""
echo "Готово! Установка завершена."
echo "Чтобы запустить приложение, дважды кликните файл Documenter.command в этой папке."
