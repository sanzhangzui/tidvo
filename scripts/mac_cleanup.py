#!/usr/bin/env python3
"""Compatibility entry point for pre-Tidvo checkouts; no state migration."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("tidvo.py")), run_name="__main__")
