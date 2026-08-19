@echo off
chcp 65001 >nul
setlocal

rem Папка, где лежит этот скрипт, — она же корень проекта
cd /d "%~dp0"

echo Устанавливаем Documenter...

where /q uv
if errorlevel 1 (
    echo Нужная программа (uv) не найдена, устанавливаем её...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo.
        echo Не получилось установить нужную программу.
        echo Проверьте подключение к интернету и попробуйте снова.
        pause
        exit /b 1
    )
)

rem Сразу после установки программа может быть недоступна в этом окне
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where /q uv
if errorlevel 1 (
    echo.
    echo Не удалось найти нужную программу после установки.
    echo Закройте это окно и запустите Install.bat ещё раз.
    pause
    exit /b 1
)

echo Устанавливаем всё необходимое для работы Documenter (это может занять минуту)...
uv sync
if errorlevel 1 (
    echo.
    echo Установка не завершилась. Прочитайте сообщение выше.
    pause
    exit /b 1
)

echo.
echo Готово! Установка завершена.
echo Чтобы запустить приложение, дважды кликните файл Documenter.bat в этой папке.
pause
