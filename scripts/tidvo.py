#!/usr/bin/env python3
"""Tidvo entry point. Python 3.11+; macOS beta, Windows planned."""
import sys

if sys.version_info < (3, 11):
    print('Python 3.11+ is required. Install it explicitly; this skill does not change your runtime.', file=sys.stderr)
    raise SystemExit(2)

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from macdev.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
