@echo off
REM Always Attend - Windows Launcher with Enhanced First-Time Setup
REM Double-click to run the attendance automation tool

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Set locale for proper character display
chcp 65001 >nul 2>&1

REM Function to display ASCII art banner
:show_banner
echo.
echo  █████╗ ██╗    ██╗ █████╗ ██╗   ██╗███████╗      
echo ██╔══██╗██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝      
echo ███████║██║ █╗ ██║███████║ ╚████╔╝ ███████╗█████╗
echo ██╔══██║██║███╗██║██╔══██║  ╚██╔╝  ╚════██║╚════╝
echo ██║  ██║╚███╔███╔╝██║  ██║   ██║   ███████║      
echo ╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝      
echo.
echo                                                   
echo  █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
echo ██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
echo ███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
echo ██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
echo ██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
echo ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
echo.
echo ═══════════════════════════════════════════════════════════════
echo         Attendance Automation Tool - Now in Public Beta        
echo ═══════════════════════════════════════════════════════════════
echo.
goto :eof

REM Function to show privacy policy and get consent
:show_privacy_policy
echo 📋 Privacy Policy and Terms of Use
echo ══════════════════════════════════════════════════════════
echo.
echo Disclaimer and Legal Notice:
echo.
echo • This project is for educational and personal use only.
echo • Use it responsibly and follow your institution's policies.
echo • This project is not affiliated with any university or service provider.
echo • You are solely responsible for any use of this tool and consequences.
echo • The authors provide no guarantee that it will work for your setup.
echo.
echo Data Processing and Privacy:
echo.
echo • Your credentials are stored locally in encrypted format
echo • No email data is processed by this tool
echo • All sensitive data remains secure and stored locally
echo • No data is shared with third parties
echo.
echo ⚠️  IMPORTANT: Ensure compliance with your institution's policies
echo.
echo Press Enter to accept and continue, or Ctrl+C to exit...
pause >nul
goto :eof

REM Function for first-time setup
:first_time_setup
echo 🚀 First-Time Setup Wizard
echo ═══════════════════════════════════════════════
echo.

REM Email configuration
echo 1. Email Configuration
echo.
set /p email=Enter your university email address: 
echo USERNAME=!email! >> .env
echo.

echo Enter your password (will be hidden): 
powershell -Command "$pword = read-host 'Password' -AsSecureString ; $BSTR=[System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($pword); $UnsecurePassword=[System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR); echo \"PASSWORD=$UnsecurePassword\" | Out-File -Append .env -Encoding ascii"
echo.

set /p portal_url=Enter your attendance portal URL (e.g., https://attendance.monash.edu.my): 
echo PORTAL_URL=!portal_url! >> .env
echo.

REM Week number
echo 2. Week Configuration
echo.
set /p week_num=Enter current week number (e.g., 1, 2, 3...): 
echo WEEK_NUMBER=!week_num! >> .env
echo.

REM Browser Configuration
echo 3. Browser Configuration
echo.
echo ⭐ Recommended: Use system browser for better compatibility
echo 1) Use system Chrome (Recommended)
echo 2) Use system Edge  
echo 3) Use Playwright's Chrome (requires: playwright install)
echo 4) Use Firefox
echo.
set /p browser_choice=Please choose (1-4): 

if "%browser_choice%"=="1" (
    echo BROWSER=chromium >> .env
    echo BROWSER_CHANNEL=chrome >> .env
    echo ✅ Using system Chrome browser
) else if "%browser_choice%"=="2" (
    echo BROWSER=chromium >> .env
    echo BROWSER_CHANNEL=msedge >> .env
    echo ✅ Using system Edge browser
) else if "%browser_choice%"=="3" (
    echo BROWSER=chromium >> .env
    echo BROWSER_CHANNEL= >> .env
    echo ⚠️  Playwright's Chrome requires: playwright install
) else if "%browser_choice%"=="4" (
    echo BROWSER=firefox >> .env
    echo BROWSER_CHANNEL= >> .env
    echo ✅ Using Firefox browser
) else (
    echo BROWSER=chromium >> .env
    echo BROWSER_CHANNEL=chrome >> .env
    echo ✅ Using system Chrome browser (default)
)
echo.

REM Step removed: Gmail/OCR not included
echo 4. Browser Configuration (continued)
echo Using your system Chrome/Edge by default. You can edit BROWSER/BROWSER_CHANNEL in .env later.
echo.

REM Create first-time flag
echo. > .first_time_setup_complete
echo 🎉 First-time setup complete!
echo.
goto :eof

REM Main script starts here
call :show_banner

REM Add preparing stage
echo Preparing Always Attend...
echo Initializing system components...
timeout /t 1 /nobreak >nul
echo Loading configuration...
timeout /t 1 /nobreak >nul
echo.

REM Check or install Git (optional for updates)
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  Git not found. Attempting installation...
    where winget >nul 2>&1
    if %errorlevel%==0 (
        echo Installing Git via winget...
        winget install -e --id Git.Git -h --accept-package-agreements --accept-source-agreements
    ) else (
        where choco >nul 2>&1
        if %errorlevel%==0 (
            echo Installing Git via Chocolatey...
            choco install git -y
        ) else (
            echo Downloading Git installer...
            powershell -NoProfile -ExecutionPolicy Bypass -Command "try{Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/latest/download/Git-64-bit.exe' -OutFile \"$env:TEMP\\git-installer.exe\" -UseBasicParsing}catch{}"
            if exist "%TEMP%\git-installer.exe" (
                echo Running Git installer silently...
                "%TEMP%\git-installer.exe" /VERYSILENT /NORESTART /NOCANCEL
            )
        )
    )
    git --version >nul 2>&1
    if %errorlevel%==0 (
        echo ✅ Git installed
    ) else (
        echo ⚠️  Git still not available. Updates will be skipped.
    )
)

REM Check if this is first time
if not exist ".first_time_setup_complete" (
    call :show_privacy_policy
)

REM Check if Python is available
echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo ❌ Error: Python not found
        echo Python is required to run this program
        echo.
        echo Solution:
        echo 1. Visit https://python.org to download Python 3.8 or higher
        echo 2. Make sure to check 'Add Python to PATH' during installation
        echo 3. Restart terminal and try again
        echo.
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
) else (
    set PYTHON_CMD=python
)

REM Check Python version
for /f "tokens=2" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set PYTHON_VERSION=%%i

REM Extract major and minor version numbers
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

if %PYTHON_MAJOR% LSS 3 (
    echo.
    echo ❌ Python version too low: %PYTHON_VERSION%
    echo Python 3.8 or higher is required
    echo.
    pause
    exit /b 1
)

if %PYTHON_MAJOR% EQU 3 if %PYTHON_MINOR% LSS 8 (
    echo.
    echo ❌ Python version too low: %PYTHON_VERSION%
    echo Python 3.8 or higher is required
    echo.
    pause
    exit /b 1
)

echo ✅ Python version check passed: %PYTHON_VERSION%

REM Check if virtual environment exists
if not exist ".venv\" (
    echo ⚠️  Virtual environment not found. Setting up...
    echo.
    
    REM Create virtual environment
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    
    if %errorlevel% neq 0 (
        echo ❌ Virtual environment creation failed
        echo.
        pause
        exit /b 1
    )
    
    echo ✅ Virtual environment created successfully
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

if %errorlevel% neq 0 (
    echo ❌ Virtual environment activation failed
    echo.
    pause
    exit /b 1
)

REM Check if requirements are installed
if not exist ".venv\requirements_installed.flag" (
    echo Installing dependencies...
    echo This may take a few minutes, please wait patiently
    echo.
    
    REM Check if requirements.txt exists
    if not exist "requirements.txt" (
        echo ❌ requirements.txt file not found
        pause
        exit /b 1
    )
    
    REM Install requirements
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    
    if %errorlevel% equ 0 (
        echo. > .venv\requirements_installed.flag
        echo ✅ Dependencies installed successfully
    ) else (
        echo ❌ Dependencies installation failed
        echo.
        pause
        exit /b 1
    )
)

REM Check if .env file exists
if not exist ".env" (
    echo ⚠️  Configuration file (.env) not found
    echo Creating configuration file...
    
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo ✅ Created .env configuration file from example
        echo.
    ) else (
        echo ❌ .env.example file not found
        pause
        exit /b 1
    )
)

REM Run first-time setup if needed
if not exist ".first_time_setup_complete" (
    call :first_time_setup
)

REM Ensure language preference is set to avoid repeated prompts
REM If LANGUAGE_PREFERENCE not in .env, detect from system UI culture and save
for /f "delims=" %%A in ('findstr /B /C:"LANGUAGE_PREFERENCE=" .env ^| find /c /v ""') do set "_has_lang=%%A"
if not defined _has_lang (
    for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "[System.Globalization.CultureInfo]::CurrentUICulture.Name"`) do set "UILANG=%%L"
    set "LANGUAGE_PREFERENCE=en"
    echo.%UILANG% | findstr /I "^zh" >nul && set "LANGUAGE_PREFERENCE=zh_CN"
    >> .env echo LANGUAGE_PREFERENCE="%LANGUAGE_PREFERENCE%"
)
REM Also set in current process env
if not defined LANGUAGE_PREFERENCE (
    if not "%LANGUAGE_PREFERENCE%"=="" (
        set "LANGUAGE_PREFERENCE=%LANGUAGE_PREFERENCE%"
    ) else (
        set "LANGUAGE_PREFERENCE=en"
    )
)

REM Main execution - simplified approach
echo.
echo 🚀 Starting Always Attend...
echo The program will automatically determine what actions are needed
echo.

REM ---- Week selection: detect latest and prompt user ----
set "LATEST_WEEK="
if exist "data" (
  for /r "data" %%F in (*.json) do (
    set "_name=%%~nF"
    call :_check_week !_name!
  )
)

REM Week selection: default non-interactive. Set WEEK_PROMPT=1 to prompt.
if not defined WEEK_NUMBER (
  if /I "%WEEK_PROMPT%"=="1" (
    echo 📅 Week Selection
    if defined LATEST_WEEK (
      set /p INPUT_WEEK=Use week %LATEST_WEEK%? Press Enter to accept, or type another week number: 
      if defined INPUT_WEEK (
        set "WEEK_NUMBER=%INPUT_WEEK%"
      ) else (
        set "WEEK_NUMBER=%LATEST_WEEK%"
      )
    ) else (
      set /p INPUT_WEEK=Enter current week number (e.g., 1,2,3...): 
      if defined INPUT_WEEK set "WEEK_NUMBER=%INPUT_WEEK%"
    )
  ) else (
    if defined LATEST_WEEK set "WEEK_NUMBER=%LATEST_WEEK%"
  )
)

REM Run the main program
python main.py

echo.
echo 👋 Thank you for using Always Attend!
echo For issues, visit: https://github.com/bunizao/always-attend/issues

REM Keep window open when double-clicked (default). Pass "--nopause" to skip.
if /I "%~1"=="--nopause" goto :eof
echo.
pause
goto :eof

REM Helper: check if argument is numeric and keep max as LATEST_WEEK
:_check_week
set "_wk=%~1"
echo.%_wk%| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 goto :eof
if not defined LATEST_WEEK (
  set "LATEST_WEEK=%_wk%"
) else (
  set /a _a=%_wk% 1>nul 2>nul
  set /a _b=%LATEST_WEEK% 1>nul 2>nul
  if %_a% GTR %_b% set "LATEST_WEEK=%_wk%"
)
goto :eof
