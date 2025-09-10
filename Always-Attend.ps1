# Always Attend - PowerShell Launcher
# Right-click -> "Run with PowerShell" to run the attendance automation tool

# Set execution policy for current session if needed
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# Change to script directory
Set-Location -Path $PSScriptRoot

# Colors
$Colors = @{
    Blue = 'Cyan'
    Green = 'Green'  
    Yellow = 'Yellow'
    Red = 'Red'
    White = 'White'
}

function Write-ColorText {
    param([string]$Text, [string]$Color = 'White')
    Write-Host $Text -ForegroundColor $Colors[$Color]
}

function Write-Header {
    param([string]$Title)
    Write-Host ""
    Write-ColorText "==========================================" "Blue"
    Write-ColorText "        $Title" "Blue"
    Write-ColorText "==========================================" "Blue"
    Write-Host ""
}

Write-Header "Always Attend - PowerShell Launcher"

# Check Git installation (optional for updates)
try {
    git --version 2>&1 | Out-Null
} catch {
    Write-ColorText "⚠️  Git not found. Updates will be skipped." "Yellow"
}

# Helpers: latest week detection and week prompt
function Get-LatestWeek {
    $latest = $null
    if (Test-Path 'data') {
        try {
            Get-ChildItem -Path 'data' -Recurse -Filter '*.json' -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                $name = $_.BaseName
                if ($name -match '^[0-9]+$') {
                    $n = [int]$name
                    if (-not $latest -or $n -gt $latest) { $latest = $n }
                }
            }
        } catch {}
    }
    return $latest
}

function Prompt-Week {
    # Default non-interactive unless WEEK_PROMPT=1
    if (-not [string]::IsNullOrEmpty($env:WEEK_NUMBER)) { return }
    $latest = Get-LatestWeek
    if ($env:WEEK_PROMPT -eq '1') {
        Write-Host ""
        Write-ColorText "📅 Week Selection" "Blue"
        if ($latest) {
            $inputWeek = Read-Host "Use week $latest? Press Enter to accept, or type another week number"
            if ([string]::IsNullOrWhiteSpace($inputWeek)) {
                $env:WEEK_NUMBER = "$latest"
            } else {
                $env:WEEK_NUMBER = $inputWeek
            }
        } else {
            $inputWeek = Read-Host "Enter current week number (e.g., 1,2,3...)"
            if (-not [string]::IsNullOrWhiteSpace($inputWeek)) {
                $env:WEEK_NUMBER = $inputWeek
            }
        }
    } else {
        if ($latest) { $env:WEEK_NUMBER = "$latest" }
    }
}

# Check if Python is available
$pythonCmd = $null
try {
    python --version 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $pythonCmd = "python"
    }
} catch {}

if (-not $pythonCmd) {
    try {
        py --version 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $pythonCmd = "py"
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-ColorText "❌ Error: Python is not installed or not in PATH" "Red"
    Write-ColorText "Please install Python 3.11+ from https://python.org" "Yellow"
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-ColorText "⚠️  Virtual environment not found. Setting up..." "Yellow"
    Write-Host ""
    
    # Create virtual environment
    Write-ColorText "Creating virtual environment..." "Blue"
    & $pythonCmd -m venv .venv
    
    if ($LASTEXITCODE -ne 0) {
        Write-ColorText "❌ Failed to create virtual environment" "Red"
        Read-Host "Press Enter to exit"
        exit 1
    }
    
    Write-ColorText "✅ Virtual environment created" "Green"
}

# Activate virtual environment
Write-ColorText "Activating virtual environment..." "Blue"
& ".venv\Scripts\Activate.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-ColorText "❌ Failed to activate virtual environment" "Red"
    Write-ColorText "Trying alternative activation method..." "Yellow"
    
    # Try cmd activation
    cmd /c ".venv\Scripts\activate.bat && python --version"
    
    if ($LASTEXITCODE -ne 0) {
        Write-ColorText "❌ Failed to activate virtual environment" "Red"
        Write-ColorText "Please run PowerShell as Administrator and execute:" "Yellow"
        Write-ColorText "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned" "Yellow"
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Check if requirements are installed
if (-not (Test-Path ".venv\requirements_installed.flag")) {
    Write-ColorText "Installing requirements..." "Blue"
    
    # Upgrade pip first
    python -m pip install --upgrade pip
    
    # Install requirements
    python -m pip install -r requirements.txt
    
    if ($LASTEXITCODE -eq 0) {
        # Create flag file
        New-Item -Path ".venv\requirements_installed.flag" -ItemType File -Force | Out-Null
        Write-ColorText "✅ Requirements installed successfully" "Green"
    } else {
        Write-ColorText "❌ Failed to install requirements" "Red"
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-ColorText "⚠️  Configuration file (.env) not found" "Yellow"
    Write-ColorText "Copying example configuration..." "Blue"
    
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-ColorText "✅ Created .env from example" "Green"
        Write-ColorText "📝 Please edit .env file to configure your credentials" "Yellow"
        Write-ColorText "   You can edit it with: notepad .env" "Yellow"
        Write-Host ""
        Read-Host "Press Enter to continue"
    } else {
        Write-ColorText "❌ .env.example not found" "Red"
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Main menu loop
while ($true) {
    Write-Header "Main Menu"
    
    Write-ColorText "1) Run attendance submission" "Green"
    Write-ColorText "2) Run with browser visible (debug mode)" "Green"  
    Write-ColorText "3) Dry run (preview codes only)" "Green"
    Write-ColorText "4) Login only (refresh session)" "Green"
    Write-ColorText "5) View statistics" "Green"
    Write-ColorText "6) Open configuration file" "Green"
    Write-ColorText "7) Update from git" "Green"
    Write-ColorText "8) Exit" "Green"
    Write-Host ""
    
    $choice = Read-Host "Choose an option (1-8)"
    Write-Host ""
    
    switch ($choice) {
        "1" {
            Write-ColorText "🚀 Running attendance submission..." "Blue"
            Prompt-Week
            python main.py
        }
        "2" {
            Write-ColorText "🚀 Running with browser visible..." "Blue"
            Prompt-Week
            python main.py --headed
        }
        "3" {
            Write-ColorText "👀 Running dry run (preview only)..." "Blue"
            Prompt-Week
            python main.py --dry-run
        }
        "4" {
            Write-ColorText "🔐 Refreshing login session..." "Blue"
            python main.py --login-only --headed
        }
        "5" {
            Write-ColorText "📊 Viewing statistics..." "Blue"
            python main.py --stats
        }
        "6" {
            Write-ColorText "📝 Opening configuration file..." "Blue"
            if (Get-Command code -ErrorAction SilentlyContinue) {
                code .env
            } else {
                notepad .env
            }
        }
        "7" {
            Write-ColorText "⬇️  Updating from git..." "Blue"
            git pull
            Write-ColorText "✅ Update complete" "Green"
        }
        "8" {
            Write-ColorText "👋 Goodbye!" "Green"
            exit 0
        }
        default {
            Write-ColorText "❌ Invalid option. Please choose 1-8." "Red"
        }
    }
    
    Write-Host ""
    Read-Host "Press Enter to continue"
}
