$ErrorActionPreference = "Stop"

# Папка, где лежит этот скрипт, — она же корень проекта
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "Устанавливаем Documenter..."

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Менеджер пакетов uv не найден, устанавливаем..."
    irm https://astral.sh/uv/install.ps1 | iex
}

# Сразу после установки uv может быть недоступен в PATH этой сессии PowerShell
$uvBin = Join-Path $env:USERPROFILE ".local\bin"
$env:PATH = "$uvBin;$env:PATH"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Не удалось найти uv после установки." -ForegroundColor Red
    Write-Host "Откройте новое окно PowerShell и запустите install.ps1 ещё раз." -ForegroundColor Red
    exit 1
}

Write-Host "Устанавливаем Python и зависимости проекта (это может занять минуту)..."
uv sync

Write-Host ""
Write-Host "Готово! Установка завершена."
Write-Host "Чтобы запустить приложение, дважды кликните файл Documenter.bat в этой папке."
