# start.ps1 — PowerShell launcher for Windows
param()

$ErrorActionPreference = "Continue"
$env:SEC_EDGAR_USER_AGENT = "StockPortfolioAgent/1.0 (research@example.com)"
$env:PYTHONPATH = Split-Path -Parent $PSScriptRoot

Write-Host "Starting MCP servers..." -ForegroundColor Cyan
$secJob = Start-Job -ScriptBlock { param($a) $env:SEC_EDGAR_USER_AGENT = $a; uvx sec-edgar-mcp } -ArgumentList $env:SEC_EDGAR_USER_AGENT
$ediJob = Start-Job -ScriptBlock { uvx edinet-mcp }

Start-Sleep -Seconds 3

Write-Host "Starting backend..." -ForegroundColor Cyan
$backJob = Start-Job -ScriptBlock {
    param($root, $ua)
    $env:PYTHONPATH = $root
    $env:SEC_EDGAR_USER_AGENT = $ua
    Set-Location $root
    & "venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
} -ArgumentList $PSScriptRoot, $env:SEC_EDGAR_USER_AGENT

Write-Host "Starting frontend..." -ForegroundColor Cyan
$frontJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location "$root\frontend"
    npm run dev
} -ArgumentList $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  System starting:" -ForegroundColor Green
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow

try {
    while ($true) {
        Start-Sleep -Seconds 1
        # Check if any job failed
        $secJob | Receive-Job -ErrorAction SilentlyContinue | Out-Null
        $ediJob | Receive-Job -ErrorAction SilentlyContinue | Out-Null
        $backJob | Receive-Job -ErrorAction SilentlyContinue | Out-Null
        $frontJob | Receive-Job -ErrorAction SilentlyContinue | Out-Null
    }
} finally {
    Write-Host "Shutting down..." -ForegroundColor Yellow
    $secJob, $ediJob, $backJob, $frontJob | Stop-Job -PassThru | Remove-Job
}