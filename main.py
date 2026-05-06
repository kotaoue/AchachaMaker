#!/usr/bin/env python3
"""Top-level entry point. Run with: python main.py"""

import sys
import os

# Ensure project root is on sys.path when run directly
sys.path.insert(0, os.path.dirname(__file__))

from src.main import main

if __name__ == "__main__":
    main()
