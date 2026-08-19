$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Программа для запуска не найдена."
    Write-Host "Сначала дважды кликните файл Install.bat в этой папке."
    Read-Host "Нажмите Enter, чтобы закрыть окно"
    exit 1
}

Write-Host "Запускаем Documenter..."
uv run python -m documenter.run
