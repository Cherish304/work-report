#!/usr/bin/env python3
"""Install portable report skills without downloading code or altering schedules."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "runtime"))
from work_report import DEFAULTS, ReportError, atomic_write, private_dir

SKILLS = ("daily-report", "weekly-report", "work-report-schedules")


def install(target, replace=False, dry_run=False, auto_submit=False):
    target = target.expanduser().resolve()
    if target == Path(target.anchor) or target == Path.home().resolve():
        raise ReportError("Choose a dedicated Codex data directory, not a drive root or home")
    skill_root = target / "skills"
    for name in SKILLS:
        destination = skill_root / name
        if destination.is_symlink():
            raise ReportError("Refusing symlink skill destination")
        if destination.exists() and not replace:
            raise ReportError("Existing skill detected; --replace is required and keeps a recoverable backup")
    if dry_run:
        return {"ok": True, "dry_run": True, "skills": list(SKILLS), "replace": replace,
                "creates_schedules": False, "sends_reports": False}
    private_dir(skill_root)
    stage = Path(tempfile.mkdtemp(prefix=".work-report-install-", dir=skill_root))
    backup = target / "work-report" / "backups" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + stage.name.rsplit("-", 1)[-1])
    moved, installed = [], []
    try:
        for name in SKILLS:
            staged_skill = stage / name
            shutil.copytree(REPO / "skills" / name, staged_skill,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if name != "work-report-schedules":
                shutil.copyfile(REPO / "runtime" / "work_report.py", staged_skill / "scripts" / "work_report.py")
                (staged_skill / "references").mkdir()
                shutil.copyfile(REPO / "runtime" / "workflow.md", staged_skill / "references" / "workflow.md")
                entry = staged_skill / "SKILL.md"
                entry.write_text(entry.read_text(encoding="utf-8").replace(
                    "../../runtime/workflow.md", "references/workflow.md"), encoding="utf-8")
        for name in SKILLS:
            destination = skill_root / name
            if destination.exists():
                private_dir(backup)
                destination.rename(backup / name)
                moved.append(name)
            (stage / name).rename(destination)
            installed.append(name)
        config_file = target / "work-report" / "config.json"
        if not config_file.exists():
            atomic_write(config_file, dict(DEFAULTS, auto_submit=auto_submit))
    except Exception:
        # Only remove directories created by this transaction; restore each original.
        for name in reversed(installed):
            shutil.rmtree(skill_root / name)
        for name in reversed(moved):
            (backup / name).rename(skill_root / name)
        raise
    finally:
        shutil.rmtree(stage)
    return {"ok": True, "skills": list(SKILLS), "backup_created": bool(moved),
            "creates_schedules": False, "sends_reports": False, "credentials_modified": False}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path,
                        default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auto-submit", action="store_true")
    args = parser.parse_args()
    try:
        result = install(args.codex_home, args.replace, args.dry_run, args.auto_submit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ReportError, OSError) as exc:
        message = str(exc) if isinstance(exc, ReportError) else "Installation failed; originals restored where applicable"
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
