#!/usr/bin/env bash
set -euo pipefail

# Папка, где лежит этот скрипт, — она же корень проекта.
# Двойной клик из Finder стартует скрипт из домашней папки, поэтому переходим сюда явно.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Устанавливаем Documenter..."

if ! command -v uv >/dev/null 2>&1; then
    echo "Нужная программа (uv) не найдена, устанавливаем её..."
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo "" >&2
        echo "Не получилось установить нужную программу." >&2
        echo "Проверьте подключение к интернету и попробуйте снова." >&2
        read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно..." || true
        exit 1
    fi
fi

# Сразу после установки программа может быть недоступна в этом окне терминала
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "" >&2
    echo "Не удалось найти нужную программу после установки." >&2
    echo "Закройте это окно и дважды кликните Install.command ещё раз." >&2
    read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно..." || true
    exit 1
fi

echo "Устанавливаем всё необходимое для работы Documenter (это может занять минуту)..."
if ! uv sync; then
    echo "" >&2
    echo "Установка не завершилась. Прочитайте сообщение выше." >&2
    read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно..." || true
    exit 1
fi

chmod +x "$SCRIPT_DIR/Documenter.command"
chmod +x "$SCRIPT_DIR/Install.command"

# Файлы, скачанные из интернета (например, распакованные из ZIP-архива с GitHub),
# macOS помечает «карантином» и не даёт запустить их двойным кликом, показывая
# ошибку «неизвестный разработчик». Снимаем эту метку с Documenter.command,
# чтобы следующий двойной клик сработал сразу, без ошибок.
xattr -d com.apple.quarantine "$SCRIPT_DIR/Documenter.command" 2>/dev/null || true

echo ""
echo "Готово! Установка завершена."
echo "Чтобы запустить приложение, дважды кликните файл Documenter.command в этой папке."
read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно..." || true
echo ""
