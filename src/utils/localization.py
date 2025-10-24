#!/usr/bin/env python3
"""
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
src/utils/localization.py
Localization utilities powering multilingual support.

Provides multi-language support for user interface strings
"""

import json
import os
import locale
from typing import Dict, Optional

class LocalizationManager:
    """Manages localization and provides translated strings"""
    
    def __init__(self, i18n_file: str = "i18n.json"):
        """
        Initialize localization manager
        
        Args:
            i18n_file: Path to the i18n JSON file
        """
        self.i18n_file = i18n_file
        self.translations = {}
        self.current_language = "en"
        self.load_translations()
        self.detect_language()
    
    def load_translations(self) -> None:
        """Load translations from i18n file"""
        try:
            if os.path.exists(self.i18n_file):
                with open(self.i18n_file, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load translations: {e}")
            self.translations = {}
    
    def detect_language(self) -> None:
        """Auto-detect system language"""
        try:
            # Try environment variable first
            lang = os.getenv('LANG', '').lower()
            if not lang:
                # Try system locale
                system_locale = locale.getdefaultlocale()[0]
                if system_locale:
                    lang = system_locale.lower()
            
            # Map common locale codes to our language keys
            if 'zh_cn' in lang or 'zh-cn' in lang or lang.startswith('zh_cn'):
                self.current_language = "zh_CN"
            elif 'zh_tw' in lang or 'zh-tw' in lang or lang.startswith('zh_tw'):
                self.current_language = "zh_TW"
            elif 'zh' in lang:
                # Default Chinese to simplified
                self.current_language = "zh_CN"
            else:
                # Default to English
                self.current_language = "en"
                
        except Exception:
            # Fallback to English
            self.current_language = "en"
    
    def set_language(self, language: str) -> bool:
        """
        Set current language
        
        Args:
            language: Language code (en, zh_CN, zh_TW)
            
        Returns:
            True if language was set successfully
        """
        if language in self.translations:
            self.current_language = language
            return True
        return False
    
    def get_available_languages(self) -> Dict[str, str]:
        """Get available languages with their display names"""
        return {
            "en": "English",
            "zh_CN": "简体中文",
            "zh_TW": "繁體中文"
        }
    
    def t(self, key: str, fallback: Optional[str] = None) -> str:
        """
        Get translated string
        
        Args:
            key: Translation key
            fallback: Fallback string if translation not found
            
        Returns:
            Translated string or fallback
        """
        if self.current_language in self.translations:
            translation = self.translations[self.current_language].get(key)
            if translation:
                return translation
        
        # Try English as fallback
        if self.current_language != "en" and "en" in self.translations:
            translation = self.translations["en"].get(key)
            if translation:
                return translation
        
        # Return fallback or key itself
        return fallback or key
    
    def get_language_name(self, lang_code: str = None) -> str:
        """Get display name for language code"""
        if lang_code is None:
            lang_code = self.current_language
        return self.get_available_languages().get(lang_code, lang_code)

# Global instance for easy access
_localization_manager = None

def get_localization_manager() -> LocalizationManager:
    """Get the global localization manager instance"""
    global _localization_manager
    if _localization_manager is None:
        _localization_manager = LocalizationManager()
    return _localization_manager

def t(key: str, fallback: Optional[str] = None) -> str:
    """Shorthand function for getting translated strings"""
    return get_localization_manager().t(key, fallback)

def set_language(language: str) -> bool:
    """Set the current language"""
    return get_localization_manager().set_language(language)

def get_current_language() -> str:
    """Get the current language code"""
    return get_localization_manager().current_language

def get_available_languages() -> Dict[str, str]:
    """Get available languages"""
    return get_localization_manager().get_available_languages()

def create_language_menu() -> str:
    """Create a language selection menu"""
    lm = get_localization_manager()
    available = lm.get_available_languages()
    current = lm.current_language
    
    menu_lines = []
    menu_lines.append("📌 " + t("choose_language", "Choose Language / 选择语言 / 選擇語言"))
    menu_lines.append("")
    
    for i, (code, name) in enumerate(available.items(), 1):
        marker = "➤" if code == current else " "
        menu_lines.append(f"{marker} {i}) {name}")
    
    menu_lines.append("")
    menu_lines.append(t("press_number", "Press number to select / 按数字选择 / 按數字選擇"))
    
    return "\n".join(menu_lines)

def get_localized_launcher_content(script_type: str = "bash") -> str:
    """
    Generate localized launcher script content
    
    Args:
        script_type: "bash" for macOS or "batch" for Windows
        
    Returns:
        Localized script content
    """
    lm = get_localization_manager()
    
    if script_type == "bash":
        return _generate_bash_launcher()
    elif script_type == "batch":
        return _generate_batch_launcher()
    else:
        raise ValueError("Script type must be 'bash' or 'batch'")

def _generate_bash_launcher() -> str:
    """Generate localized bash launcher for macOS"""
    return f'''#!/bin/bash
# Always Attend - {t("launcher_title")}

# Set locale for proper character display
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

cd "$(dirname "$0")"

echo
echo "=========================================="
echo "   {t("launcher_title")}"
echo "=========================================="
echo

# Function to display localized messages
show_message() {{
    echo "$1"
}}

# Check Python installation
show_message "{t("checking_python")}"
'''

def _generate_batch_launcher() -> str:
    """Generate localized batch launcher for Windows"""
    return f'''@echo off
REM {t("launcher_title")}

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ==========================================
echo    {t("launcher_title")}
echo ==========================================
echo.

REM Check Python installation
echo {t("checking_python")}
'''

if __name__ == "__main__":
    # Demo the localization system
    lm = LocalizationManager()
    
    print("🌍 Localization System Demo")
    print("=" * 40)
    
    # Show detected language
    print(f"Detected language: {lm.get_language_name()}")
    print()
    
    # Test translations in different languages
    for lang_code, lang_name in lm.get_available_languages().items():
        lm.set_language(lang_code)
        print(f"[{lang_name}]")
        print(f"  App Title: {t('app_title')}")
        print(f"  Checking Python: {t('checking_python')}")
        print(f"  Main Menu: {t('main_menu')}")
        print()
    
    # Show language menu
    print("Language Selection Menu:")
    print(create_language_menu())
