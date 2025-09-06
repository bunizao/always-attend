#!/usr/bin/env python3
"""
Always Attend - Main Entry Point
Redirects to the actual main module in src/core/
"""

import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the actual main module
if __name__ == "__main__":
    from core.main import main
    main()