# Entwicklungsstart unter Windows: Umgebung einrichten und Anzeige oeffnen.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".\.venv")) {
    Write-Host "Erstelle virtuelle Umgebung..." -ForegroundColor Cyan
    py -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
}

if (-not (Test-Path ".\config.yaml")) {
    Copy-Item config.example.yaml config.yaml
    Write-Host "config.yaml aus Vorlage erstellt." -ForegroundColor Yellow
}

$port = 8080
if ((Get-Content config.yaml) -match '^\s*port:\s*(\d+)') {
    $port = [int]$Matches[1]
}

Start-Process "http://127.0.0.1:$port/"
.\.venv\Scripts\python.exe -m app.server --config config.yaml
