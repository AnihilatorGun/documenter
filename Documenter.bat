@echo off
chcp 65001 >nul
setlocal

rem Переходим в папку, где лежит сам ярлык — иначе двойной клик
rem стартует сервер из другой папки, и uv не найдёт проект
cd /d "%~dp0"

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where /q uv
if errorlevel 1 (
    echo Программа для запуска не найдена.
    echo Сначала дважды кликните файл Install.bat в этой папке.
    pause
    exit /b 1
)

echo Запускаем Documenter...
echo.

uv run python -m documenter.run
