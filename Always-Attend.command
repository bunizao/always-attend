#!/bin/bash

# Always Attend - macOS Launcher with Enhanced First-Time Setup
# Double-click to run the attendance automation tool

# Change to the script directory
cd "$(dirname "$0")"

# Set locale for proper character display
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Load localization
LANG_FILE="i18n.json"
CURRENT_LANG=""

# Function to detect system language
detect_language() {
    local lang="${LANG:-en}"
    case "$lang" in
        zh_CN*|zh-CN*) CURRENT_LANG="zh_CN" ;;
        zh_TW*|zh-TW*) CURRENT_LANG="zh_TW" ;;
        zh*) CURRENT_LANG="zh_CN" ;;
        *) CURRENT_LANG="en" ;;
    esac
}

# Function to get translated text
t() {
    local key="$1"
    local fallback="$2"
    
    if [ ! -f "$LANG_FILE" ]; then
        echo "${fallback:-$key}"
        return
    fi
    
    # Try to extract translation using basic text processing
    local translation
    translation=$(python3 -c "
import json, sys
try:
    with open('$LANG_FILE', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(data.get('$CURRENT_LANG', {}).get('$key', data.get('en', {}).get('$key', '$key')))
except:
    print('$key')
" 2>/dev/null)
    
    if [ -n "$translation" ] && [ "$translation" != "$key" ]; then
        echo "$translation"
    else
        echo "${fallback:-$key}"
    fi
}

# Function to display ASCII art banner
show_banner() {
    echo -e "${CYAN}"
    cat << 'EOF'
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝
                                                     
 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
EOF
    echo -e "${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}        Attendance Automation Tool - Now in Public Beta        ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo
}

# Function to show privacy policy and get consent
show_privacy_policy() {
    echo -e "${YELLOW}📋 $(t "privacy_policy" "Privacy Policy and Terms of Use")${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
    echo
    echo -e "${GREEN}$(t "disclaimer_title" "Disclaimer and Legal Notice:")${NC}"
    echo
    echo "• This project is for educational and personal use only."
    echo "• Use it responsibly and follow your institution's policies."
    echo "• This project is not affiliated with any university or service provider."
    echo "• You are solely responsible for any use of this tool and consequences."
    echo "• The authors provide no guarantee that it will work for your setup."
    echo
    echo -e "${GREEN}$(t "data_processing" "Data Processing and Privacy:")${NC}"
    echo
    echo "• Your credentials are stored locally in encrypted format"
    echo "• No email data is processed by this tool"
    echo "• Only attendance code images are processed by AI - no personal data"
    echo "• All sensitive data remains secure and stored locally"
    echo "• No data is shared with third parties"
    echo
    echo -e "${RED}⚠️  $(t "compliance_warning" "IMPORTANT: Ensure compliance with your institution's policies")${NC}"
    echo
    echo -e "${CYAN}Press Enter to accept and continue, or Ctrl+C to exit...${NC}"
    read
}

# Function for first-time setup
first_time_setup() {
    echo -e "${BLUE}🚀 $(t "first_time_setup" "First-Time Setup Wizard")${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo
    
    # University configuration
    echo -e "${GREEN}1. $(t "university_config" "University Configuration")${NC}"
    echo
    echo "Which university are you attending?"
    echo "1) Monash University Malaysia"
    echo "2) Other university"
    echo
    read -p "$(t "choose_university" "Please choose (1-2):")" univ_choice
    
    if [ "$univ_choice" = "1" ]; then
        clear
        show_banner
        echo -e "${GREEN}✅ $(t "monash_configured" "Monash University Malaysia configured")${NC}"
        echo "PORTAL_URL=https://attendance.monash.edu.my" >> .env
    else
        clear
        show_banner
        echo
        read -p "$(t "enter_portal_url" "Please enter your attendance portal URL:")" portal_url
        echo "PORTAL_URL=$portal_url" >> .env
        echo -e "${GREEN}✅ $(t "portal_configured" "Portal URL configured")${NC}"
    fi
    echo
    
    # Email configuration
    echo -e "${GREEN}2. $(t "email_config" "Email Configuration")${NC}"
    echo
    read -p "$(t "enter_email" "Enter your university email address:")" email
    echo "USERNAME=$email" >> .env
    echo
    
    read -s -p "$(t "enter_password" "Enter your password:")" password
    echo
    echo "PASSWORD=$password" >> .env
    echo
    
    # Week number
    echo -e "${GREEN}3. $(t "week_config" "Week Configuration")${NC}"
    echo
    read -p "$(t "enter_week" "Enter current week number (e.g., 1, 2, 3...):")" week_num
    echo "WEEK_NUMBER=$week_num" >> .env
    echo
    
    # Step removed: Gmail/OCR features are not included
    echo -e "${GREEN}4. $(t "browser_config" "Browser Configuration")${NC}"
    echo "Using your system Chrome/Edge by default."
    echo "You can change BROWSER/BROWSER_CHANNEL later in .env if needed."
    echo >> .env
    
    # Create first-time flag
    touch .first_time_setup_complete
    echo -e "${GREEN}🎉 $(t "setup_complete" "First-time setup complete!")${NC}"
    echo
}

# Initialize language
detect_language

# Show banner
show_banner

# Check or install Git (optional for updates)
if ! command -v git >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Git not found. Attempting installation...${NC}"
    if command -v brew >/dev/null 2>&1; then
        echo -e "${BLUE}Installing Git via Homebrew...${NC}"
        brew install git || echo -e "${YELLOW}⚠️  Homebrew install failed.${NC}"
    else
        # Try Xcode Command Line Tools which include git
        if ! xcode-select -p >/dev/null 2>&1; then
            echo -e "${BLUE}Installing Xcode Command Line Tools (provides git)...${NC}"
            xcode-select --install >/dev/null 2>&1 || true
            echo -e "${YELLOW}Please complete the installer window, then press Enter to continue...${NC}"
            read
        else
            echo -e "${YELLOW}Opening Git for macOS download page...${NC}"
            open "https://git-scm.com/download/mac" >/dev/null 2>&1 || true
            echo -e "${YELLOW}Install Git, then press Enter to continue...${NC}"
            read
        fi
    fi
    if command -v git >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Git installed${NC}"
    else
        echo -e "${YELLOW}⚠️  Git still not available. Updates will be skipped.${NC}"
    fi
fi

# Helper: detect latest week number from data/<COURSE>/<WEEK>.json
detect_latest_week() {
    local latest=""
    if [ -d "data" ]; then
        # Find all *.json under data/*/, take numeric basename, compute max
        while IFS= read -r -d '' f; do
            base="${f##*/}"
            base="${base%.json}"
            if [[ "$base" =~ ^[0-9]+$ ]]; then
                if [ -z "$latest" ] || [ "$base" -gt "$latest" ]; then
                    latest="$base"
                fi
            fi
        done < <(find data -type f -name '*.json' -print0 2>/dev/null)
    fi
    echo "$latest"
}

# Add preparing stage
echo -e "${BLUE}$(t "preparing" "Preparing Always Attend...")${NC}"
echo -e "${YELLOW}$(t "initializing" "Initializing system components...")${NC}"
sleep 1
echo -e "${GREEN}$(t "loading_config" "Loading configuration...")${NC}"
sleep 1
echo

# Check if this is first time
if [ ! -f ".first_time_setup_complete" ]; then
    show_privacy_policy
fi

# Check if Python is available
echo -e "${BLUE}$(t "checking_python" "Checking Python installation...")${NC}"
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}❌ $(t "python_not_found" "Error: Python not found")${NC}"
    echo -e "${YELLOW}$(t "python_required" "Python is required to run this program")${NC}"
    echo
    echo -e "${BLUE}$(t "solution" "Solution:")${NC}"
    echo "$(t "install_python" "1. Visit https://python.org to download Python 3.8 or higher")"
    echo "$(t "add_to_path" "2. Make sure to check 'Add Python to PATH' during installation")"
    echo "$(t "restart_terminal" "3. Restart terminal and try again")"
    echo
    echo "$(t "press_continue" "Press any key to continue...")"
    read -n 1
    exit 1
fi

# Set Python command and check version
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

# Check Python version
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${RED}❌ $(t "python_version_low" "Python version too low"): $PYTHON_VERSION${NC}"
    echo -e "${YELLOW}$(t "python_version_required" "Python 3.8 or higher is required")${NC}"
    echo
    echo "$(t "press_continue" "Press any key to continue...")"
    read -n 1
    exit 1
fi

echo -e "${GREEN}✅ $(t "python_version_passed" "Python version check passed"): $PYTHON_VERSION${NC}"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  $(t "venv_not_found" "Virtual environment not found. Setting up...")${NC}"
    echo
    
    # Create virtual environment
    echo -e "${BLUE}$(t "creating_venv" "Creating virtual environment...")${NC}"
    $PYTHON_CMD -m venv .venv
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ $(t "venv_create_failed" "Virtual environment creation failed")${NC}"
        echo
        echo "$(t "press_continue" "Press any key to continue...")"
        read -n 1
        exit 1
    fi
    
    echo -e "${GREEN}✅ $(t "venv_created" "Virtual environment created successfully")${NC}"
fi

# Activate virtual environment
echo -e "${BLUE}$(t "activating_venv" "Activating virtual environment...")${NC}"
source .venv/bin/activate

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ $(t "venv_activate_failed" "Virtual environment activation failed")${NC}"
    echo
    echo "$(t "press_continue" "Press any key to continue...")"
    read -n 1
    exit 1
fi

# Check if requirements are installed
if [ ! -f ".venv/requirements_installed.flag" ]; then
    echo -e "${BLUE}$(t "installing_deps" "Installing dependencies...")${NC}"
    echo -e "${YELLOW}$(t "wait_patiently" "This may take a few minutes, please wait patiently")${NC}"
    
    # Check if requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        echo -e "${RED}❌ $(t "requirements_not_found" "requirements.txt file not found")${NC}"
        echo "$(t "press_continue" "Press any key to continue...")"
        read -n 1
        exit 1
    fi
    
    # Install requirements
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    
    if [ $? -eq 0 ]; then
        touch .venv/requirements_installed.flag
        echo -e "${GREEN}✅ $(t "deps_installed" "Dependencies installed successfully")${NC}"
    else
        echo -e "${RED}❌ $(t "deps_install_failed" "Dependencies installation failed")${NC}"
        echo
        echo "$(t "press_continue" "Press any key to continue...")"
        read -n 1
        exit 1
    fi
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  $(t "config_not_found" "Configuration file (.env) not found")${NC}"
    echo -e "${BLUE}$(t "creating_config" "Creating configuration file...")${NC}"
    
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ $(t "config_created" "Created .env configuration file from example")${NC}"
        echo
    else
        echo -e "${RED}❌ $(t "example_not_found" ".env.example file not found")${NC}"
        echo "$(t "press_continue" "Press any key to continue...")"
        read -n 1
        exit 1
    fi
fi

# Run first-time setup if needed
if [ ! -f ".first_time_setup_complete" ]; then
    first_time_setup
fi

# Main execution - simplified approach
echo
echo -e "${BLUE}🚀 $(t "starting_program" "Starting Always Attend...")${NC}"
echo -e "${YELLOW}$(t "auto_mode" "The program will automatically determine what actions are needed")${NC}"
echo

# Week selection: default is non-interactive
DETECTED_WEEK="$(detect_latest_week)"
if [ -z "$WEEK_NUMBER" ]; then
  if [ "${WEEK_PROMPT:-0}" = "1" ]; then
    echo -e "${BLUE}📅 Week Selection${NC}"
    if [ -n "$DETECTED_WEEK" ]; then
      read -p "Use week ${DETECTED_WEEK}? Press Enter to accept, or type another week number: " input_week
      if [ -n "$input_week" ]; then
        export WEEK_NUMBER="$input_week"
      else
        export WEEK_NUMBER="$DETECTED_WEEK"
      fi
    else
      read -p "Enter current week number (e.g., 1,2,3...): " input_week
      if [ -n "$input_week" ]; then export WEEK_NUMBER="$input_week"; fi
    fi
  else
    # No prompt: silently use detected week if available
    if [ -n "$DETECTED_WEEK" ]; then export WEEK_NUMBER="$DETECTED_WEEK"; fi
  fi
fi

# Run the main program
python main.py

echo
echo -e "${GREEN}👋 $(t "goodbye" "Thank you for using Always Attend!")${NC}"
echo "$(t "support_url" "For issues, visit: https://github.com/bunizao/always-attend/issues")"
