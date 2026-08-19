@echo off
chcp 65001 >nul
setlocal

rem Переходим в папку, где лежит сам ярлык — иначе двойной клик
rem стартует сервер из другой папки, и uv не найдёт проект
cd /d "%~dp0"

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

rem Открываем браузер в отдельном окне, с задержкой — чтобы сервер успел подняться
start /min "" cmd /c "timeout /t 2 >nul && start http://localhost:8000"

echo Запускаем Documenter...
echo Приложение работает. Чтобы остановить — закройте это окно или нажмите Ctrl+C.
echo.

uv run uvicorn documenter.app:app --port 8000
