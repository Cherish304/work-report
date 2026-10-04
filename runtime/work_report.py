#!/usr/bin/env python3
"""Portable deterministic helpers; report synthesis stays in the Codex skill."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULTS = {
    "timezone": "Asia/Shanghai", "auto_submit": False,
    "confirmation_minutes": 5, "dws_path": None,
    "daily_time": "18:30", "weekly_day": "MO", "weekly_time": "18:00",
    "weekly_mode": "previous_workweek",
    "daily_template_name": "日报", "weekly_template_name": "周报",
}
FIELDS = {
    "daily": ("今日完成工作", "未完成工作", "需协调工作"),
    "weekly": ("本周完成工作", "本周工作总结", "下周工作计划", "需协调与帮助"),
}
FALLBACKS = {
    "daily": ("暂无可核实的完成项", "暂无明确未完成事项", "暂无"),
    "weekly": ("暂无可核实的完成项", "暂无可核实的总结", "暂无明确计划，请在提交前补充", "暂无"),
}


class ReportError(Exception):
    pass


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()


def data_root():
    return codex_home() / "work-report"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def config():
    path = data_root() / "config.json"
    overrides = read_json(path) if path.exists() else {}
    if not isinstance(overrides, dict) or set(overrides) - set(DEFAULTS):
        raise ReportError("Invalid configuration keys")
    result = dict(DEFAULTS, **overrides)
    if type(result["auto_submit"]) is not bool:
        raise ReportError("auto_submit must be boolean")
    minutes = result["confirmation_minutes"]
    if type(minutes) is not int or minutes < 5 or minutes > 1440:
        raise ReportError("confirmation_minutes must be an integer from 5 to 1440")
    for key in ("daily_time", "weekly_time"):
        if not isinstance(result[key], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", result[key]):
            raise ReportError("Schedule time must be HH:MM")
    if result["weekly_day"] not in ("MO", "TU", "WE", "TH", "FR", "SA", "SU"):
        raise ReportError("Invalid weekly_day")
    if result["weekly_mode"] not in ("previous_workweek", "current_workweek"):
        raise ReportError("Invalid weekly_mode")
    for key in ("daily_template_name", "weekly_template_name", "timezone"):
        if not isinstance(result[key], str) or not result[key].strip():
            raise ReportError("Template names and timezone must be nonempty strings")
    if result["dws_path"] is not None and not isinstance(result["dws_path"], str):
        raise ReportError("dws_path must be a string or null")
    timezone(result)
    return result


def timezone(cfg):
    try:
        return ZoneInfo(cfg["timezone"])
    except ZoneInfoNotFoundError as exc:
        raise ReportError("Timezone data missing: install tzdata in this Python environment") from exc


def parse_time(value, tz):
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return (parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed).astimezone(tz)


def iso(value):
    return value.isoformat(timespec="seconds")


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ReportError("Refusing symlink data directory")
    if os.name != "nt":
        path.chmod(0o700)


def atomic_write(path, value):
    path = Path(path)
    private_dir(path.parent)
    if path.is_symlink():
        raise ReportError("Refusing symlink output")
    fd, name = tempfile.mkstemp(prefix=".work-report-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
        if os.name != "nt":
            os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def resolve_dws(cfg, system=None):
    system = system or platform.system()
    configured = cfg.get("dws_path")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and (system == "Windows" or os.access(path, os.X_OK)):
            return str(path.resolve())
        raise ReportError("Configured DWS executable is unavailable")
    names = ("dws.exe", "dws") if system == "Windows" else ("dws",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    candidate = Path.home() / ".local" / "bin" / ("dws.exe" if system == "Windows" else "dws")
    if candidate.is_file() and (system == "Windows" or os.access(candidate, os.X_OK)):
        return str(candidate)
    raise ReportError("DWS is unavailable; install the native binary or configure dws_path")


def run_dws(cfg, args, payload=None, timeout=60):
    # Bytes bypass PowerShell 5.1 defaults and JSON shell quoting on both platforms.
    env = dict(os.environ, NO_COLOR="1")
    result = subprocess.run(
        [resolve_dws(cfg), *args], input=payload, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, shell=False, env=env,
    )
    if result.returncode:
        # Do not log CLI stderr: authentication errors may contain sensitive context.
        raise ReportError(f"DWS failed with exit code {result.returncode}; check locally without exposing credentials")
    return result.stdout.decode("utf-8-sig")


def window(args, cfg):
    tz = timezone(cfg)
    now = parse_time(args.now, tz) if args.now else datetime.now(tz)
    if args.start or args.end:
        if not (args.start and args.end):
            raise ReportError("--start and --end must be provided together")
        start, end = parse_time(args.start, tz), parse_time(args.end, tz)
        mode = "explicit"
    elif args.kind == "daily":
        start = datetime.combine(now.date(), time.min, tzinfo=tz)
        end = now
        mode = "manual"
        if args.scheduled:
            end = datetime.combine(now.date(), time.fromisoformat(cfg["daily_time"]), tzinfo=tz)
            if now < end:
                raise ReportError("Scheduled daily cutoff is still in the future")
            mode = "scheduled_daily"
    elif args.scheduled and cfg["weekly_mode"] == "previous_workweek":
        days = (now.weekday() - 4) % 7
        # A Friday still in progress is not a fully completed workweek.
        friday = now.date() - timedelta(days=days or 7)
        start = datetime.combine(friday - timedelta(days=4), time.min, tzinfo=tz)
        end = datetime.combine(friday, time(23, 59, 59), tzinfo=tz)
        mode = "scheduled_previous_workweek"
    elif now.weekday() <= 4:
        start = datetime.combine(now.date() - timedelta(days=now.weekday()), time.min, tzinfo=tz)
        end, mode = now, "current_workweek"
    else:
        friday = now.date() - timedelta(days=now.weekday() - 4)
        start = datetime.combine(friday - timedelta(days=4), time.min, tzinfo=tz)
        end = datetime.combine(friday, time(23, 59, 59), tzinfo=tz)
        mode = "completed_workweek"
    if end < start:
        raise ReportError("end must not be earlier than start")
    run_key = start.date().isoformat()
    if args.kind == "weekly" or start.date() != end.date():
        run_key += "_" + end.date().isoformat()
    return {"kind": args.kind, "timezone": cfg["timezone"], "window_mode": mode,
            "start_iso": iso(start), "end_iso": iso(end), "run_key": run_key,
            "start_chat": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_chat": end.strftime("%Y-%m-%d %H:%M:%S"),
            "display_range": f"{start.month}.{start.day}～{end.month}.{end.day}"}


def collect(args, cfg):
    tz = timezone(cfg)
    start, end = parse_time(args.start, tz), parse_time(args.end, tz)
    if end < start:
        raise ReportError("end must not be earlier than start")
    root = Path(args.root).expanduser() if args.root else codex_home() / "memories" / "rollout_summaries"
    items, diagnostics, total = [], [], 0
    if not root.is_dir():
        return {"count": 0, "items": [], "diagnostics": ["rollout_summaries unavailable"]}
    for path in sorted(root.glob("*.md")):
        if path.is_symlink():
            continue
        try:
            if path.stat().st_size > 524288:
                diagnostics.append("Oversized summary skipped")
                continue
            raw = path.read_bytes()
            content = raw.decode("utf-8")
            # filename is a UTC timestamp in Codex rollout summary naming.
            # Explicit source_updated_at/updated_at is preferred; do not treat mtime as proof.
            stamp, origin = None, None
            for key in ("source_updated_at", "updated_at", "created_at"):
                match = re.search(rf"(?m)^{key}:\s*(\S+)", content[:16384])
                if match:
                    stamp, origin = parse_time(match.group(1), tz), "metadata:" + key
                    break
            if stamp is None:
                match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", path.name)
                if match:
                    stamp = parse_time(f"{match[1]}T{match[2]}:{match[3]}:{match[4]}+00:00", tz)
                    origin = "filename_utc"
            if stamp is None:
                diagnostics.append("Summary without reliable timestamp skipped")
                continue
            if not start <= stamp <= end:
                continue
            if total + len(raw) > 8388608:
                diagnostics.append("Summary byte budget reached; coverage incomplete")
                break
            total += len(raw)
            items.append({"file": path.name, "inferred_at": iso(stamp),
                          "timestamp_source": origin, "content": content})
        except (OSError, UnicodeError, ValueError):
            diagnostics.append("Unreadable or invalid summary skipped")
    items.sort(key=lambda item: (item["inferred_at"], item["file"]))
    return {"count": len(items), "items": items, "diagnostics": diagnostics}


def validate_payload(value, kind):
    if not isinstance(value, list) or len(value) != len(FIELDS[kind]):
        raise ReportError("Unexpected payload field count")
    for index, entry in enumerate(value):
        if (not isinstance(entry, dict) or entry.get("key") != FIELDS[kind][index]
                or entry.get("sort") != str(index) or entry.get("type") != "1"
                or entry.get("contentType") != "markdown"
                or not isinstance(entry.get("content"), str) or not entry["content"].strip()):
            raise ReportError("Invalid report payload field contract")
    return value


def build(args, cfg):
    if len(args.field_files) != len(FIELDS[args.kind]):
        raise ReportError("Supply one field file per template field in order")
    value = []
    for index, filename in enumerate(args.field_files):
        content = Path(filename).read_text(encoding="utf-8").strip() or FALLBACKS[args.kind][index]
        value.append({"key": FIELDS[args.kind][index], "sort": str(index),
                      "content": content, "contentType": "markdown", "type": "1"})
    validate_payload(value, args.kind)
    atomic_write(Path(args.output), value)
    return {"field_count": len(value), "contents_sha256": digest(Path(args.output))}


def safe_key(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:_\d{4}-\d{2}-\d{2})?", value):
        raise ReportError("run-key must be a date or date_date range")
    for part in value.split("_"):
        datetime.strptime(part, "%Y-%m-%d")
    return value


def paths(kind, key):
    key = safe_key(key)
    root = data_root() / kind / "runs"
    return root / (key + ".json"), root / key / "contents.json", root / (key + ".lock")


@contextmanager
def run_lock(kind, key):
    lock = paths(kind, key)[2]
    private_dir(lock.parent)
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ReportError("Report is locked; do not retry or steal the lock automatically") from exc
    try:
        yield
    finally:
        lock.rmdir()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_state(kind, key):
    state = read_json(paths(kind, key)[0])
    if state.get("kind") != kind or state.get("run_key") != key:
        raise ReportError("State identity mismatch")
    return state


def init_state(args, cfg):
    tz = timezone(cfg)
    now = parse_time(args.now, tz) if args.now else datetime.now(tz)
    start, end = parse_time(args.start, tz), parse_time(args.end, tz)
    if end < start:
        raise ReportError("Invalid report window")
    expected_key = start.date().isoformat()
    if args.kind == "weekly" or start.date() != end.date():
        expected_key += "_" + end.date().isoformat()
    if args.run_key != expected_key:
        raise ReportError("run-key does not match the report window")
    payload = validate_payload(read_json(args.contents_file), args.kind)
    state_path, contents_path, _ = paths(args.kind, args.run_key)
    with run_lock(args.kind, args.run_key):
        if state_path.exists():
            existing = load_state(args.kind, args.run_key)
            if existing["status"] != "awaiting_confirmation":
                raise ReportError("Terminal or uncertain state cannot be replaced")
            if not args.replace:
                raise ReportError("State exists; revised preview requires --replace")
        atomic_write(contents_path, payload)
        state = {"schema_version": 1, "kind": args.kind, "run_key": args.run_key,
                 "status": "awaiting_confirmation", "start_iso": iso(start), "end_iso": iso(end),
                 "template_id": args.template_id, "contents_sha256": digest(contents_path),
                 "previewed_at": iso(now), "updated_at": iso(now), "auto_submit": cfg["auto_submit"],
                 "submit_after": iso(now + timedelta(minutes=cfg["confirmation_minutes"])),
                 "report_id": None}
        atomic_write(state_path, state)
    return {"state": state}


def show_state(args, cfg):
    state = load_state(args.kind, args.run_key)
    contents = paths(args.kind, args.run_key)[1]
    return {"state": state, "contents_hash_matches": contents.is_file() and digest(contents) == state["contents_sha256"]}


def cancel(args, cfg):
    with run_lock(args.kind, args.run_key):
        state = load_state(args.kind, args.run_key)
        if state["status"] != "awaiting_confirmation":
            raise ReportError("Only a pending report can be canceled")
        state["status"] = "canceled"
        state["updated_at"] = iso(datetime.now(timezone(cfg)))
        atomic_write(paths(args.kind, args.run_key)[0], state)
    return {"state": state}


def find_report_id(value):
    if isinstance(value, dict):
        for key in ("reportId", "report_id"):
            if isinstance(value.get(key), (str, int)) and value[key]:
                return str(value[key])
        for child in value.values():
            found = find_report_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_report_id(child)
            if found:
                return found
    return None


def submit(args, cfg):
    # Task replies, live schema/identity and remote deduplication are semantic
    # preconditions checked by the skill, never inferred from a timer by Python.
    if not args.preflight_checked:
        raise ReportError("Skill must verify replies, live template, identity and remote duplicates first")
    with run_lock(args.kind, args.run_key):
        state_path, contents_path, _ = paths(args.kind, args.run_key)
        state = load_state(args.kind, args.run_key)
        if state["status"] != "awaiting_confirmation":
            raise ReportError("Report is not awaiting confirmation")
        raw = contents_path.read_bytes()
        validate_payload(json.loads(raw), args.kind)
        if hashlib.sha256(raw).hexdigest() != state["contents_sha256"]:
            raise ReportError("Payload changed since preview; regenerate preview")
        now = datetime.now(timezone(cfg))
        if args.mode == "timeout":
            if not (cfg["auto_submit"] and state["auto_submit"]):
                raise ReportError("Automatic submission was not enabled")
            if now < parse_time(state["submit_after"], timezone(cfg)):
                raise ReportError("Confirmation window has not elapsed")
        command = ["report", "entry", "submit", "--template-id", state["template_id"],
                   "--contents", "-", "--yes", "--format", "json"]
        if args.dry_run:
            return {"dry_run": True, "preview": run_dws(cfg, command + ["--dry-run"], raw)}
        state["status"], state["updated_at"] = "submitting", iso(now)
        atomic_write(state_path, state)
        try:
            result = json.loads(run_dws(cfg, command, raw))
            if result.get("success") is False or result.get("ok") is False:
                raise ReportError("DWS did not acknowledge submission")
            report_id = find_report_id(result)
            if not report_id:
                raise ReportError("Submission lacks a report ID; verify remote outbox manually")
        except (ReportError, OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
            state["status"] = "submission_unknown"
            state["updated_at"] = iso(datetime.now(timezone(cfg)))
            atomic_write(state_path, state)
            raise ReportError("Submission result unknown; inspect remote outbox before any further action")
        state.update(status="submitted", report_id=report_id,
                     submitted_at=iso(datetime.now(timezone(cfg))))
        state["updated_at"] = state["submitted_at"]
        atomic_write(state_path, state)
    return {"state": state, "result": result}


def dws_read(args, cfg):
    allowed = {("auth", "status"), ("report", "template", "list"),
               ("report", "template", "get"), ("report", "outbox", "list"),
               ("report", "entry", "get"), ("chat", "message", "list-all")}
    commands = args.dws_args
    if commands and commands[0] == "--":
        commands = commands[1:]
    if not any(tuple(commands[:len(prefix)]) == prefix for prefix in allowed):
        raise ReportError("Only report source/template/auth-status read commands are allowed")
    if any(flag in commands for flag in ("--debug", "--verbose", "--client-secret")):
        raise ReportError("Do not pass credentials or debug flags through the report helper")
    if "--format" not in commands and "--help" not in commands:
        commands += ["--format", "json"]
    output = run_dws(cfg, commands)
    return {"output": output} if "--help" in commands else json.loads(output)


def doctor(args, cfg):
    try:
        version = run_dws(cfg, ["--version"]).strip()
        dws_ok = True
    except (ReportError, OSError, subprocess.TimeoutExpired):
        version, dws_ok = "unavailable", False
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", version)
    compatible = bool(match and tuple(map(int, match.groups())) >= (1, 0, 15))
    return {"platform": platform.system(), "python": platform.python_version(),
            "dws_available": dws_ok, "dws_version": version,
            "dws_minimum_version_satisfied": compatible,
            "timezone_available": True, "auto_submit": cfg["auto_submit"],
            "windows_acl_required": os.name == "nt",
            "summary_directory_available": (codex_home() / "memories" / "rollout_summaries").is_dir()}


def parser(default_kind=None):
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--kind", choices=FIELDS, default=default_kind or "daily")
    commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser("doctor"); p.set_defaults(handler=doctor)
    p = commands.add_parser("config"); p.set_defaults(handler=lambda args, cfg: {
        **cfg, "dws_path": "configured" if cfg["dws_path"] else None})
    p = commands.add_parser("window")
    p.add_argument("--now"); p.add_argument("--start"); p.add_argument("--end")
    p.add_argument("--scheduled", action="store_true"); p.set_defaults(handler=window)
    p = commands.add_parser("collect-memories")
    p.add_argument("--root"); p.add_argument("--start", required=True); p.add_argument("--end", required=True)
    p.set_defaults(handler=collect)
    p = commands.add_parser("build-contents")
    p.add_argument("--field-files", nargs="+", required=True); p.add_argument("--output", required=True)
    p.set_defaults(handler=build)
    p = commands.add_parser("state-init")
    for name in ("run-key", "start", "end", "template-id", "contents-file"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--now"); p.add_argument("--replace", action="store_true"); p.set_defaults(handler=init_state)
    for name, handler in (("state-show", show_state), ("cancel", cancel)):
        p = commands.add_parser(name); p.add_argument("--run-key", required=True); p.set_defaults(handler=handler)
    p = commands.add_parser("submit")
    p.add_argument("--run-key", required=True); p.add_argument("--mode", choices=("confirmed", "timeout"), required=True)
    p.add_argument("--preflight-checked", action="store_true"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(handler=submit)
    p = commands.add_parser("dws-read"); p.add_argument("dws_args", nargs=argparse.REMAINDER); p.set_defaults(handler=dws_read)
    return root


def main(default_kind=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser(default_kind).parse_args()
    try:
        result = args.handler(args, config())
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    except (ReportError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        # Paths and raw OS errors may reveal machine identity; expose a stable error.
        error = str(exc) if isinstance(exc, ReportError) else "Invalid input, unavailable file, or execution timeout"
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
