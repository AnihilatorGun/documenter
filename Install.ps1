$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

Write-Host "Устанавливаем Documenter..."

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Нужная программа (uv) не найдена, устанавливаем её..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}

# Сразу после установки uv ещё не виден этому окну
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "Не удалось найти нужную программу после установки."
    Write-Host "Закройте это окно и запустите Install.bat ещё раз."
    exit 1
}

Write-Host "Устанавливаем всё необходимое для работы (это может занять минуту)..."
uv sync
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Установка не завершилась. Прочитайте сообщение выше."
    exit 1
}

Write-Host ""
Write-Host "Готово! Установка завершена."
Write-Host "Чтобы запустить приложение, дважды кликните файл Documenter.bat в этой папке."
