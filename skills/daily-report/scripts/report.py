#!/usr/bin/env python3
"""Thin entrypoint; the installer places the shared runtime alongside this file."""
import sys
from pathlib import Path

if not (Path(__file__).parent / "work_report.py").exists():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runtime"))
from work_report import main

if __name__ == "__main__":
    main(default_kind="daily")
