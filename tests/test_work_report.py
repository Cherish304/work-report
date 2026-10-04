import argparse
import importlib.util
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import work_report as report

spec = importlib.util.spec_from_file_location("report_installer", ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ReportsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="work-report-test-")
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")})
        self.env.start()
        self.cfg = dict(report.DEFAULTS)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def args(self, command, *extra, kind="daily"):
        return report.parser(kind).parse_args([command, *extra])

    def payload(self, kind="daily"):
        return [{"key": field, "sort": str(index), "content": "核实的结果\n第二行",
                 "contentType": "markdown", "type": "1"}
                for index, field in enumerate(report.FIELDS[kind])]

    def pending(self, cfg=None, kind="daily", now="2000-01-01T18:30:00+08:00"):
        key = "2000-01-01" if kind == "daily" else "2000-01-01_2000-01-01"
        source = self.root / "测试 文件.json"
        report.atomic_write(source, self.payload(kind))
        args = self.args("state-init", "--run-key", key, "--start", "2000-01-01T00:00:00+08:00",
                         "--end", "2000-01-01T18:30:00+08:00", "--now", now,
                         "--template-id", "SYNTHETIC_TEMPLATE", "--contents-file", str(source), kind=kind)
        return args, report.init_state(args, cfg or self.cfg)

    def submission(self, mode="confirmed", **kwargs):
        args = self.args("submit", "--run-key", "2000-01-01", "--mode", mode, "--preflight-checked")
        for key, value in kwargs.items():
            setattr(args, key, value)
        return args

    def test_config_defaults_manual_only(self):
        self.assertFalse(report.config()["auto_submit"])
        self.assertEqual(report.data_root(), (self.root / "codex").resolve() / "work-report")

    def test_config_bad_confirmation_rejected(self):
        for minutes in (0, 4, True, "5", 1441):
            report.atomic_write(report.data_root() / "config.json", {"confirmation_minutes": minutes})
            with self.assertRaises(report.ReportError):
                report.config()

    def test_config_private_keys_rejected(self):
        report.atomic_write(report.data_root() / "config.json", {"token": "SYNTHETIC_NOT_A_SECRET"})
        with self.assertRaises(report.ReportError):
            report.config()

    def test_schedule_time_validation(self):
        for value in ("25:00", "18:75", "6:30"):
            report.atomic_write(report.data_root() / "config.json", {"daily_time": value})
            with self.assertRaises(report.ReportError):
                report.config()

    def test_delayed_daily_has_fixed_cutoff(self):
        value = report.window(self.args("window", "--scheduled", "--now", "2026-07-31T20:00:00+08:00"), self.cfg)
        self.assertEqual(value["end_iso"], "2026-07-31T18:30:00+08:00")

    def test_manual_daily_ends_now(self):
        value = report.window(self.args("window", "--now", "2026-07-31T15:10:00+08:00"), self.cfg)
        self.assertEqual(value["end_iso"], "2026-07-31T15:10:00+08:00")

    def test_early_scheduled_daily_rejected(self):
        with self.assertRaises(report.ReportError):
            report.window(self.args("window", "--scheduled", "--now", "2026-07-31T15:10:00+08:00"), self.cfg)

    def test_monday_weekly_previous_workweek(self):
        value = report.window(self.args("window", "--scheduled", "--now", "2026-08-03T18:00:00+08:00", kind="weekly"), self.cfg)
        self.assertEqual(value["run_key"], "2026-07-27_2026-07-31")
        self.assertEqual(value["end_iso"], "2026-07-31T23:59:59+08:00")

    def test_friday_current_week_configuration(self):
        cfg = dict(self.cfg, weekly_mode="current_workweek")
        value = report.window(self.args("window", "--scheduled", "--now", "2026-07-31T18:00:00+08:00", kind="weekly"), cfg)
        self.assertEqual(value["start_iso"], "2026-07-27T00:00:00+08:00")
        self.assertEqual(value["end_iso"], "2026-07-31T18:00:00+08:00")

    def test_explicit_range(self):
        value = report.window(self.args("window", "--start", "2026-07-28T00:00:00+08:00", "--end", "2026-08-03T12:00:00+08:00"), self.cfg)
        self.assertEqual(value["run_key"], "2026-07-28_2026-08-03")

    def test_bad_ranges_rejected(self):
        for extra in (("--start", "2026-07-28"), ("--start", "2026-07-28", "--end", "2026-07-27")):
            with self.assertRaises(report.ReportError):
                report.window(self.args("window", *extra), self.cfg)

    def test_build_field_contract_and_unicode(self):
        files = []
        for index in range(3):
            path = self.root / (str(index) + ".md")
            path.write_text("成果\n下一行" if index == 0 else "", encoding="utf-8")
            files.append(str(path))
        output = self.root / "drafts" / "contents.json"
        report.build(self.args("build-contents", "--field-files", *files, "--output", str(output)), self.cfg)
        value = report.read_json(output)
        self.assertEqual(value[0]["content"], "成果\n下一行")
        self.assertEqual(value[1]["content"], "暂无明确未完成事项")
        self.assertEqual(len(value), 3)

    def test_reject_invalid_payload(self):
        value = self.payload()
        value[0]["key"] = "Wrong field"
        with self.assertRaises(report.ReportError):
            report.validate_payload(value, "daily")

    def test_pending_wait_and_hash(self):
        args, value = self.pending()
        self.assertEqual(value["state"]["submit_after"], "2000-01-01T18:35:00+08:00")
        shown = report.show_state(self.args("state-show", "--run-key", args.run_key), self.cfg)
        self.assertTrue(shown["contents_hash_matches"])

    def test_replace_resets_confirmation(self):
        args, value = self.pending()
        args.replace, args.now = True, "2000-01-01T19:00:00+08:00"
        value = report.init_state(args, self.cfg)
        self.assertEqual(value["state"]["submit_after"], "2000-01-01T19:05:00+08:00")

    def test_duplicate_init_rejected(self):
        args, _ = self.pending()
        with self.assertRaises(report.ReportError):
            report.init_state(args, self.cfg)

    def test_canceled_cannot_reactivate(self):
        args, _ = self.pending()
        report.cancel(self.args("cancel", "--run-key", args.run_key), self.cfg)
        args.replace = True
        with self.assertRaises(report.ReportError):
            report.init_state(args, self.cfg)

    def test_hash_change_stops_submission(self):
        args, _ = self.pending()
        report.paths("daily", args.run_key)[1].write_text("[]", encoding="utf-8")
        with patch.object(report, "run_dws") as run:
            with self.assertRaises(report.ReportError):
                report.submit(self.submission(), self.cfg)
            run.assert_not_called()

    def test_timeout_not_enabled(self):
        self.pending()
        with patch.object(report, "run_dws") as run:
            with self.assertRaises(report.ReportError):
                report.submit(self.submission("timeout"), self.cfg)
            run.assert_not_called()

    def test_timeout_too_early(self):
        cfg = dict(self.cfg, auto_submit=True)
        self.pending(cfg, now="2099-01-01T18:30:00+08:00")
        with self.assertRaises(report.ReportError):
            report.submit(self.submission("timeout"), cfg)

    def test_preflight_assertion_required(self):
        self.pending()
        with self.assertRaises(report.ReportError):
            report.submit(self.submission(preflight_checked=False), self.cfg)

    def test_submission_success_no_duplicate(self):
        self.pending()
        with patch.object(report, "run_dws", return_value=json.dumps({"success": True, "result": {"reportId": "SYNTHETIC_REPORT"}})) as run:
            value = report.submit(self.submission(), self.cfg)
            self.assertEqual(value["state"]["status"], "submitted")
            raw = run.call_args.args[2]
            self.assertIsInstance(raw, bytes)
            self.assertIn("核实".encode("utf-8"), raw)
            with self.assertRaises(report.ReportError):
                report.submit(self.submission(), self.cfg)
            self.assertEqual(run.call_count, 1)

    def test_submission_timeout_never_retries(self):
        self.pending()
        with patch.object(report, "run_dws", side_effect=subprocess.TimeoutExpired("mock", 1)) as run:
            with self.assertRaises(report.ReportError):
                report.submit(self.submission(), self.cfg)
            self.assertEqual(report.load_state("daily", "2000-01-01")["status"], "submission_unknown")
            with self.assertRaises(report.ReportError):
                report.submit(self.submission(), self.cfg)
            self.assertEqual(run.call_count, 1)

    def test_no_report_id_is_unknown(self):
        self.pending()
        with patch.object(report, "run_dws", return_value='{"success": true}'):
            with self.assertRaises(report.ReportError):
                report.submit(self.submission(), self.cfg)
        self.assertEqual(report.load_state("daily", "2000-01-01")["status"], "submission_unknown")

    def test_dry_run_keeps_pending(self):
        self.pending()
        with patch.object(report, "run_dws", return_value="[DRY-RUN] only") as run:
            value = report.submit(self.submission(dry_run=True), self.cfg)
            self.assertTrue(value["dry_run"])
            self.assertIn("--dry-run", run.call_args.args[1])
        self.assertEqual(report.load_state("daily", "2000-01-01")["status"], "awaiting_confirmation")

    def test_concurrent_lock_stops_second_runner(self):
        self.pending()
        with report.run_lock("daily", "2000-01-01"):
            with self.assertRaises(report.ReportError):
                report.submit(self.submission(), self.cfg)

    def test_invalid_key_cannot_escape_state_directory(self):
        for key in ("../secret", ".", "foo", "2026-99-99"):
            with self.assertRaises((report.ReportError, ValueError)):
                report.paths("daily", key)

    def test_state_key_matches_window(self):
        args, _ = self.pending()
        args.run_key = "2000-01-02"
        with self.assertRaises(report.ReportError):
            report.init_state(args, self.cfg)

    @unittest.skipIf(os.name == "nt", "Unix modes are not Windows ACLs")
    def test_private_unix_permissions(self):
        self.pending()
        state, payload, _ = report.paths("daily", "2000-01-01")
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(payload.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(payload.parent.stat().st_mode), 0o700)

    def test_dws_windows_resolution(self):
        with patch.object(report.shutil, "which", side_effect=lambda name: "C:/Tools/dws.exe" if name == "dws.exe" else None):
            self.assertEqual(report.resolve_dws(self.cfg, "Windows"), "C:/Tools/dws.exe")

    def test_dws_mac_resolution(self):
        with patch.object(report.shutil, "which", return_value="/mock/tools/dws") as which:
            self.assertEqual(report.resolve_dws(self.cfg, "Darwin"), "/mock/tools/dws")
            which.assert_called_once_with("dws")

    def test_dws_explicit_bad_path_fails_closed(self):
        with self.assertRaises(report.ReportError):
            report.resolve_dws(dict(self.cfg, dws_path=str(self.root / "missing")))

    def test_utf8_bytes_no_shell_and_space_paths(self):
        fake = subprocess.CompletedProcess([], 0, "中文输出".encode("utf-8"), b"")
        with patch.object(report, "resolve_dws", return_value="C:/Program Files/Tools/dws.exe"), patch.object(report.subprocess, "run", return_value=fake) as run:
            output = report.run_dws(self.cfg, ["report", "entry", "submit"], "中文输入".encode("utf-8"))
            self.assertEqual(output, "中文输出")
            self.assertFalse(run.call_args.kwargs["shell"])
            self.assertEqual(run.call_args.args[0][0], "C:/Program Files/Tools/dws.exe")
            self.assertEqual(run.call_args.kwargs["input"], "中文输入".encode("utf-8"))

    def test_generic_dws_wrapper_cannot_send(self):
        with self.assertRaises(report.ReportError):
            report.dws_read(self.args("dws-read", "--", "report", "entry", "submit"), self.cfg)

    def test_cli_error_does_not_leak_stderr(self):
        fake = subprocess.CompletedProcess([], 2, b"", b"SYNTHETIC_SENSITIVE_DIAGNOSTIC")
        with patch.object(report, "resolve_dws", return_value="mock"), patch.object(report.subprocess, "run", return_value=fake):
            with self.assertRaises(report.ReportError) as error:
                report.run_dws(self.cfg, ["auth", "status"])
            self.assertNotIn("SYNTHETIC_SENSITIVE", str(error.exception))

    def test_missing_summaries_is_coverage_gap(self):
        value = report.collect(self.args("collect-memories", "--start", "2026-07-31", "--end", "2026-08-01"), self.cfg)
        self.assertEqual(value["count"], 0)
        self.assertTrue(value["diagnostics"])

    def test_summary_utc_filename_and_no_mtime_guessing(self):
        root = self.root / "summaries"
        root.mkdir()
        (root / "2026-07-30T20-00-00-example.md").write_text("A verified work result", encoding="utf-8")
        (root / "unknown.md").write_text("No source timestamp", encoding="utf-8")
        value = report.collect(self.args("collect-memories", "--root", str(root), "--start", "2026-07-31T00:00:00+08:00", "--end", "2026-07-31T18:30:00+08:00"), self.cfg)
        self.assertEqual(value["count"], 1)
        self.assertEqual(value["items"][0]["inferred_at"], "2026-07-31T04:00:00+08:00")
        self.assertTrue(value["diagnostics"])

    def test_install_dry_run_is_non_mutating(self):
        target = self.root / "install-target"
        self.assertTrue(installer.install(target, dry_run=True)["dry_run"])
        self.assertFalse(target.exists())

    def test_install_and_installed_entrypoints(self):
        target = self.root / "installed-codex"
        installer.install(target)
        for name in ("daily-report", "weekly-report"):
            skill = target / "skills" / name
            self.assertIn("references/workflow.md", (skill / "SKILL.md").read_text(encoding="utf-8"))
            result = subprocess.run([sys.executable, str(skill / "scripts" / "report.py"), "window", "--now", "2026-07-31T18:30:00+08:00"], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["kind"], "daily" if name == "daily-report" else "weekly")

    def test_install_conflict_and_recoverable_backup(self):
        target = self.root / "installed-codex"
        installer.install(target)
        original = target / "skills" / "daily-report" / "user-note.md"
        original.write_text("User-owned data", encoding="utf-8")
        with self.assertRaises(report.ReportError):
            installer.install(target)
        self.assertTrue(original.exists())
        value = installer.install(target, replace=True)
        self.assertTrue(value["backup_created"])
        notes = list((target / "work-report" / "backups").rglob("user-note.md"))
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].read_text(encoding="utf-8"), "User-owned data")

    def test_install_does_not_override_existing_config(self):
        target = self.root / "installed-codex"
        installer.install(target)
        installer.install(target, replace=True, auto_submit=True)
        self.assertFalse(report.read_json(target / "work-report" / "config.json")["auto_submit"])

    def test_install_auto_submit_is_explicit(self):
        target = self.root / "installed-codex"
        installer.install(target, auto_submit=True)
        self.assertTrue(report.read_json(target / "work-report" / "config.json")["auto_submit"])

    @unittest.skipUnless(platform.system() == "Darwin", "macOS launcher integration")
    def test_mac_launcher_installs_in_isolated_directory(self):
        target = self.root / "mac launcher" / "codex"
        result = subprocess.run(["bash", str(ROOT / "scripts" / "install-macos.sh"),
                                 "--codex-home", str(target)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["sends_reports"])
        self.assertTrue((target / "skills" / "daily-report" / "scripts" / "work_report.py").is_file())

    def test_install_failure_restores_original_skills(self):
        target = self.root / "installed-codex"
        installer.install(target)
        note = target / "skills" / "daily-report" / "user-note.md"
        note.write_text("Original skill note", encoding="utf-8")
        original_rename = Path.rename

        def fail_once(path, destination):
            if path.name == "weekly-report" and path.parent.name.startswith(".work-report-install-"):
                raise OSError("Synthetic install failure")
            return original_rename(path, destination)

        with patch.object(Path, "rename", fail_once):
            with self.assertRaises(OSError):
                installer.install(target, replace=True)
        self.assertEqual(note.read_text(encoding="utf-8"), "Original skill note")
        self.assertTrue((target / "skills" / "weekly-report" / "SKILL.md").exists())

    def test_native_dws_stdin_dry_run_only(self):
        try:
            report.resolve_dws(self.cfg)
        except report.ReportError:
            self.skipTest("Native DWS unavailable; CI tests use mocks")
        self.pending()
        value = report.submit(self.submission(dry_run=True), self.cfg)
        self.assertTrue(value["dry_run"])
        self.assertIn("核实", value["preview"])
        self.assertEqual(report.load_state("daily", "2000-01-01")["status"], "awaiting_confirmation")


if __name__ == "__main__":
    unittest.main()
