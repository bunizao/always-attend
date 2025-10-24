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
src/config/config_wizard.py
Interactive configuration wizard for Always Attend.
"""

import os
import sys
import shutil
import getpass
from typing import Dict, Optional

from utils.logger import logger


class ConfigWizard:
    """Interactive configuration wizard for first-time setup"""
    
    def __init__(self, env_file: str = ".env"):
        self.env_file = env_file
        self.config = {}
        
    def run(self) -> bool:
        """Run the configuration wizard"""
        print("\n" + "="*60)
        print("🎯 Welcome to Always Attend Configuration Wizard")
        print("="*60)
        
        # Ensure .env file exists by copying from .env.example
        self._ensure_env_file()
        
        # Language selection first
        print("\n" + "🌍 Language Selection".center(60, "-"))
        self._configure_language()
        
        # Check existing configuration
        existing_config = self._load_existing_config()
        
        # Basic credentials
        print("\n" + "🔐 Authentication Setup".center(60, "-"))
        self._configure_credentials()
        
        # Gmail/OCR/GitHub features removed
        
        # Browser configuration
        print("\n" + "🌐 Browser Settings".center(60, "-"))
        self._configure_browser()
            
        # Save configuration
        if self.config:
            self._save_config()
            print(f"\n✅ Configuration saved to {self.env_file}")
            
        print("\n" + "🎉 Setup Complete!".center(60, "="))
        print("\nYou can now run the attendance automation:")
        print("  python main.py")
        print("\nOr test with dry run:")
        print("  python main.py --dry-run")
        
        return True
        
    def _ensure_env_file(self) -> None:
        """Ensure .env file exists by copying from .env.example if needed"""
        env_example_path = ".env.example"
        
        if not os.path.exists(self.env_file):
            if os.path.exists(env_example_path):
                try:
                    shutil.copy2(env_example_path, self.env_file)
                    logger.info(f"Created {self.env_file} from {env_example_path}")
                    print(f"✅ Created {self.env_file} from template")
                except Exception as e:
                    logger.error(f"Failed to copy {env_example_path} to {self.env_file}: {e}")
                    # Create a minimal .env file as fallback
                    with open(self.env_file, 'w', encoding='utf-8') as f:
                        f.write("# Always Attend Configuration\n")
                        f.write("# Created by configuration wizard\n\n")
                    print(f"⚠️ Created minimal {self.env_file} file")
            else:
                logger.warning(f"{env_example_path} not found, creating minimal {self.env_file}")
                # Create a minimal .env file
                with open(self.env_file, 'w', encoding='utf-8') as f:
                    f.write("# Always Attend Configuration\n")
                    f.write("# Created by configuration wizard\n\n")
                print(f"⚠️ Created minimal {self.env_file} file")
        else:
            logger.debug(f"{self.env_file} already exists")
        
    def _load_existing_config(self) -> Dict[str, str]:
        """Load existing configuration from .env file"""
        config = {}
        if os.path.exists(self.env_file):
            try:
                with open(self.env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            # Remove quotes if present
                            value = value.strip().strip('"\'')
                            if value:
                                config[key.strip()] = value
            except Exception as e:
                logger.warning(f"Error reading existing config: {e}")
        return config
        
    # Gmail/OCR removed
        
    def _configure_language(self) -> None:
        """Configure language preference"""
        from utils.localization import get_available_languages, create_language_menu, set_language
        
        print("\n🌍 Choose your preferred language:")
        print(create_language_menu())
        
        try:
            available_langs = list(get_available_languages().keys())
            choice = input("\nEnter your choice (1-3): ").strip()
            
            if choice in ['1', '2', '3']:
                lang_index = int(choice) - 1
                if 0 <= lang_index < len(available_langs):
                    selected_lang = available_langs[lang_index]
                    set_language(selected_lang)
                    self.config['LANGUAGE_PREFERENCE'] = selected_lang
                    print(f"✅ Language set to: {get_available_languages()[selected_lang]}")
            else:
                print("📝 Using default language (English)")
                self.config['LANGUAGE_PREFERENCE'] = 'en'
                
        except (ValueError, EOFError, KeyboardInterrupt):
            print("📝 Using default language (English)")
            self.config['LANGUAGE_PREFERENCE'] = 'en'
    
    def _configure_credentials(self) -> None:
        """Configure basic authentication"""
        print("\n🔐 Enter your university credentials:")
        print("This will be used to log into the attendance portal.")
        
        # Username/Email
        username = input("\nUsername/Email: ").strip()
        if username:
            self.config['USERNAME'] = username
            # Automatically set SCHOOL_EMAIL if it looks like an email
            if '@' in username:
                self.config['SCHOOL_EMAIL'] = username
        
        # Password (hidden input)
        password = getpass.getpass("Password: ")
        if password:
            self.config['PASSWORD'] = password
            
        # Portal URL (default to Monash)
        print("\nPortal URL:")
        print("1) Monash University Malaysia (https://attendance.monash.edu.my)")
        print("2) Other university")
        
        portal_choice = input("\nChoose (1-2): ").strip()
        if portal_choice == '1':
            self.config['PORTAL_URL'] = 'https://attendance.monash.edu.my'
            print("✅ Using Monash University Malaysia portal")
        else:
            portal_url = input("Enter your portal URL: ").strip()
            if portal_url:
                self.config['PORTAL_URL'] = portal_url
                
    def _configure_browser(self) -> None:
        """Configure browser settings"""
        print("\n🌐 Browser Configuration:")
        print("For better compatibility, we recommend using your system browser.")
        
        print("\n1) Use system Chrome (Recommended)")
        print("2) Use system Edge")  
        print("3) Use Playwright's Chrome")
        print("4) Use Firefox")
        
        browser_choice = input("\nChoose (1-4): ").strip()
        
        if browser_choice == '1':
            self.config['BROWSER'] = 'chromium'
            self.config['BROWSER_CHANNEL'] = 'chrome'
            print("✅ Using system Chrome browser")
        elif browser_choice == '2':
            self.config['BROWSER'] = 'chromium'
            self.config['BROWSER_CHANNEL'] = 'msedge'
            print("✅ Using system Edge browser")
        elif browser_choice == '3':
            self.config['BROWSER'] = 'chromium'
            self.config['BROWSER_CHANNEL'] = ''
            print("✅ Using Playwright's Chrome (requires: playwright install)")
        elif browser_choice == '4':
            self.config['BROWSER'] = 'firefox'
            self.config['BROWSER_CHANNEL'] = ''
            print("✅ Using Firefox browser")
        else:
            # Default to system Chrome
            self.config['BROWSER'] = 'chromium'
            self.config['BROWSER_CHANNEL'] = 'chrome'
            print("✅ Using system Chrome browser (default)")
        
    def _configure_ocr(self) -> bool:
        """Legacy OCR config removed; no-op."""
        return False
                
    # Gemini/OpenAI setup removed
            
    def _configure_github_fallback(self) -> None:
        """Legacy GitHub fallback removed; no-op."""
        return None
            
    # Gmail/OCR removed
            
    def _save_config(self) -> None:
        """Save configuration to .env file"""
        try:
            # Read existing content
            existing_lines = []
            if os.path.exists(self.env_file):
                with open(self.env_file, 'r') as f:
                    existing_lines = f.readlines()
                    
            # Update or add new configuration
            updated_lines = []
            keys_added = set()
            
            for line in existing_lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=', 1)[0].strip()
                    if key in self.config:
                        # Update existing key (ensure proper newline)
                        updated_lines.append(f'{key}="{self.config[key]}"\n')
                        keys_added.add(key)
                    else:
                        # Keep existing line
                        updated_lines.append(line)
                else:
                    # Keep comments and empty lines
                    updated_lines.append(line)
                    
            # Add new keys
            if keys_added != set(self.config.keys()):
                for key, value in self.config.items():
                    if key not in keys_added:
                        updated_lines.append(f'{key}="{value}"\n')
                        
            # Write back to file
            with open(self.env_file, 'w') as f:
                f.writelines(updated_lines)
                
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            print(f"❌ Error saving configuration: {e}")
            
    @staticmethod
    def should_run_wizard() -> bool:
        """Check if the wizard should run (first time setup)"""
        # If launchers have already completed first-time setup, skip
        if os.path.exists(".first_time_setup_complete"):
            return False
        # Check if .env exists and has some configuration
        if os.path.exists(".env"):
            try:
                with open(".env", 'r') as f:
                    content = f.read()
                    # If .env has more than just basic configuration, assume setup is done
                    config_lines = [line for line in content.split('\\n') 
                                  if line.strip() and not line.strip().startswith('#') and '=' in line]
                    if len(config_lines) > 3:  # More than bare-minimum config
                        return False
            except Exception:
                pass
                
        return True
        
    @staticmethod
    def prompt_user_for_wizard() -> bool:
        """Prompt user to run the configuration wizard"""
        print("\n🎯 First-time Configuration Setup")
        print("=" * 40)
        print("This wizard will help you set portal URL, credentials, and browser settings.")
        
        try:
            run_wizard = input("Run configuration wizard? (Y/n): ").strip().lower()
            return run_wizard != 'n'
        except EOFError:
            # Non-interactive environment, skip wizard
            return False


def main():
    """Run the configuration wizard standalone"""
    wizard = ConfigWizard()
    wizard.run()


if __name__ == "__main__":
    main()
