# Always Attend - PowerShell launcher
# Delegates all interactive experience to the Python portal.

Set-Location -Path $PSScriptRoot

$pythonCandidates = @("python3", "python")
$pythonCmd = $null

foreach ($candidate in $pythonCandidates) {
    try {
        $null = Get-Command $candidate -ErrorAction Stop
        $pythonCmd = $candidate
        break
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "Python 3.8+ is required. Install it from https://python.org/downloads/." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "🚀 Launching Always Attend portal..." -ForegroundColor Cyan
& $pythonCmd "main.py" $args
