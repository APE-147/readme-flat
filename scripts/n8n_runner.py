#!/usr/bin/env python3
# Lightweight runner for n8n Execute Command or Python Code node
# Usage:
#   python scripts/n8n_runner.py --config /absolute/path/to/config.yaml

import argparse
import json
import os
import sys
import signal
import time
import subprocess
import io
import contextlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run readme-sync from n8n and return JSON")
    parser.add_argument("--config", required=False, help="Path to config.yaml")
    parser.add_argument("--source", action="append", help="Source folder (can be repeated)")
    parser.add_argument("--target", help="Target folder")
    parser.add_argument("--sources-json", help='JSON array of sources, e.g. ["/a","/b"]')
    parser.add_argument("--args-json", help='JSON object with keys {"sources": [...], "target": "..."}')
    parser.add_argument("--args-file", help='Path to a file containing JSON object with keys {"sources": [...], "target": "..."}')
    parser.add_argument(
        "--mode",
        choices=["sync", "clean", "reset", "stop", "reverse", "mappings"],
        default="sync",
        help="Operation mode: sync|clean|reset|stop|reverse|mappings",
    )
    parser.add_argument(
        "--stop-daemon",
        action="store_true",
        help="When used with --mode reset, attempt to stop running daemon and unload LaunchAgent",
    )
    args = parser.parse_args()

    # Ensure src/ is importable when running from repo
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    try:
        from readme_sync.services.config import ConfigManager
        from readme_sync.services.database import DatabaseManager
        from readme_sync.core.sync_engine import SyncEngine
    except Exception as e:
        # Output machine-readable JSON only
        print(json.dumps({
            "success": False,
            "mode": args.mode,
            "error": {
                "type": "ImportError",
                "message": str(e),
            },
            "sys_path": sys.path,
        }, ensure_ascii=False))
        return 1

    config_path = args.config or os.environ.get(
        "READMESYNC_CONFIG",
        "/Users/niceday/Developer/Cloud/Dropbox/-Code-/Data/srv/readme_flat/config.yaml",
    )

    try:
        # Provide runtime overrides (prefer explicit args-json / args-file)
        if args.source:
            os.environ["READMESYNC_SOURCE_DIRS"] = ",".join(args.source)
        if args.sources_json:
            os.environ["READMESYNC_SOURCES_JSON"] = args.sources_json
        override_origin = None
        overrides: dict | None = None
        # 1) Prefer args-file
        if args.args_file:
            try:
                with open(args.args_file, 'r', encoding='utf-8') as f:
                    overrides = json.load(f)
                    override_origin = "args_file"
            except Exception:
                overrides = None
        # 2) Then args-json
        if overrides is None and args.args_json:
            try:
                overrides = json.loads(args.args_json)
                override_origin = "args_json"
            except Exception:
                overrides = None
        # 3) Fallback to CLI --source/--target
        if overrides is None and (args.source or args.target):
            overrides = {}
            override_origin = "cli_args"
            if args.source:
                overrides["sources"] = args.source
            if args.target:
                overrides["target"] = args.target
        # 4) Finally env vars
        if overrides is None:
            try:
                if os.environ.get("READMESYNC_ARGS_JSON"):
                    overrides = json.loads(os.environ["READMESYNC_ARGS_JSON"])  # type: ignore
                    override_origin = "env_args_json"
            except Exception:
                overrides = None
        if overrides is None:
            try:
                if os.environ.get("READMESYNC_SOURCES_JSON"):
                    arr = json.loads(os.environ["READMESYNC_SOURCES_JSON"])  # type: ignore
                    overrides = {"sources": arr}
                    override_origin = "env_sources_json"
            except Exception:
                overrides = None
        if overrides is None:
            if os.environ.get("READMESYNC_SOURCE_DIRS") or os.environ.get("READMESYNC_TARGET_DIR"):
                override_origin = "env_csv"
                sources_csv = os.environ.get("READMESYNC_SOURCE_DIRS", "")
                target_env = os.environ.get("READMESYNC_TARGET_DIR", "")
                srcs = [s.strip() for s in sources_csv.split(',') if s.strip()]
                overrides = {}
                if srcs:
                    overrides["sources"] = srcs
                if target_env:
                    overrides["target"] = target_env

        cfg = ConfigManager(config_path, runtime_overrides=overrides)
        db = DatabaseManager()

        if args.mode == "sync":
            engine = SyncEngine(cfg, db)

            def _do_sync():
                return engine.sync_all()

            result, cap_out, cap_err = None, "", ""
            with contextlib.redirect_stdout(io.StringIO()) as _out, contextlib.redirect_stderr(io.StringIO()) as _err:
                result = _do_sync()
                cap_out = _out.getvalue()
                cap_err = _err.getvalue()

            print(json.dumps({
                "success": True,
                "mode": "sync",
                "result": result,
                "effective_sources": cfg.get_enabled_source_folders(),
                "effective_target": cfg.get_target_folder(),
                "logs": {
                    "stdout": cap_out,
                    "stderr": cap_err,
                },
            }, ensure_ascii=False))

        elif args.mode == "clean":

            def _do_clean():
                orphaned = db.cleanup_orphaned_mappings()
                moved = 0
                target = cfg.get_target_folder()
                if target and os.path.exists(target) and cfg.get_move_unlinked_files():
                    moved = db.move_unlinked_files(target, cfg.get_unlinked_subfolder())
                return {"orphaned_removed": orphaned, "unlinked_moved": moved}

            data, cap_out, cap_err = None, "", ""
            with contextlib.redirect_stdout(io.StringIO()) as _out, contextlib.redirect_stderr(io.StringIO()) as _err:
                data = _do_clean()
                cap_out = _out.getvalue()
                cap_err = _err.getvalue()

            print(json.dumps({
                "success": True,
                "mode": "clean",
                **data,
                "effective_sources": cfg.get_enabled_source_folders(),
                "effective_target": cfg.get_target_folder(),
                "logs": {
                    "stdout": cap_out,
                    "stderr": cap_err,
                },
            }, ensure_ascii=False))

        elif args.mode == "stop":
            conf_dir = Path(cfg.get_config_dir())
            removed = []
            daemon_stopped = False
            unloaded = []

            def _do_stop():
                nonlocal daemon_stopped, unloaded
                # Stop by PID
                pid_file = conf_dir / "daemon.pid"
                try:
                    if pid_file.exists():
                        pid = int(pid_file.read_text().strip())
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        for _ in range(10):
                            try:
                                os.kill(pid, 0)
                                time.sleep(1)
                            except ProcessLookupError:
                                daemon_stopped = True
                                break
                        if not daemon_stopped:
                            try:
                                os.kill(pid, signal.SIGKILL)
                                time.sleep(1)
                                daemon_stopped = True
                            except ProcessLookupError:
                                daemon_stopped = True
                except Exception:
                    pass

                # Unload LaunchAgents
                home = Path.home()
                for plist_name in ("com.readme-sync.daemon.plist", "com.readme-sync.plist"):
                    plist_path = home / "Library" / "LaunchAgents" / plist_name
                    if plist_path.exists():
                        try:
                            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
                        except Exception:
                            pass
                        try:
                            plist_path.unlink()
                            unloaded.append(str(plist_path))
                        except Exception:
                            pass

            def _remove_state():
                names = (
                    "daemon.pid", "daemon.status", "daemon.log",
                    "launchd.out", "launchd.err", "sync_data.db"
                )
                for name in names:
                    p = conf_dir / name
                    try:
                        if p.exists():
                            p.unlink()
                            removed.append(str(p))
                    except Exception:
                        pass
                # Remove sqlite sidecar files
                for pat in ("*.db-wal", "*.db-shm", "*.log"):
                    for fp in conf_dir.glob(pat):
                        try:
                            fp.unlink()
                            removed.append(str(fp))
                        except Exception:
                            pass
                # Remove logs directory if present
                logs_dir = conf_dir / "logs"
                if logs_dir.exists() and logs_dir.is_dir():
                    import shutil
                    try:
                        shutil.rmtree(logs_dir)
                        removed.append(str(logs_dir))
                    except Exception:
                        pass

            cap_out, cap_err = "", ""
            with contextlib.redirect_stdout(io.StringIO()) as _out, contextlib.redirect_stderr(io.StringIO()) as _err:
                _do_stop()
                _remove_state()
                cap_out = _out.getvalue()
                cap_err = _err.getvalue()

            print(json.dumps({
                "success": True,
                "mode": "stop",
                "daemon_stopped": daemon_stopped,
                "launchagents_removed": unloaded,
                "removed": removed,
                "config_dir": str(conf_dir),
                "logs": {"stdout": cap_out, "stderr": cap_err},
            }, ensure_ascii=False))

        elif args.mode == "reverse":
            force = os.environ.get("READMESYNC_FORCE", "false").lower() in ("1","true","yes")
            engine = SyncEngine(cfg, db)

            def _do_rev():
                return engine.reverse_all(force=force)

            data, cap_out, cap_err = None, "", ""
            with contextlib.redirect_stdout(io.StringIO()) as _out, contextlib.redirect_stderr(io.StringIO()) as _err:
                data = _do_rev()
                cap_out = _out.getvalue()
                cap_err = _err.getvalue()

            print(json.dumps({
                "success": True,
                "mode": "reverse",
                **data,
                "force": force,
                "logs": {"stdout": cap_out, "stderr": cap_err},
            }, ensure_ascii=False))

        elif args.mode == "mappings":
            # List all existing mappings as JSON
            rows = db.get_all_mappings()
            print(json.dumps({
                "success": True,
                "mode": "mappings",
                "count": len(rows),
                "mappings": rows,
                "effective_sources": cfg.get_enabled_source_folders(),
                "effective_target": cfg.get_target_folder(),
            }, ensure_ascii=False))
        else:  # reset (stop + wipe + restart)
            conf_dir = Path(cfg.get_config_dir())
            removed = []
            daemon_stopped = False
            unloaded = []
            restarted = False
            start_cmd = None

            # Optionally try to stop daemon by PID and unload LaunchAgents
            def _do_reset_stop():
                nonlocal daemon_stopped, unloaded
                if not args.stop_daemon:
                    # For reset semantics, perform stop by default
                    pass
                pid_file = conf_dir / "daemon.pid"
                try:
                    if pid_file.exists():
                        pid = int(pid_file.read_text().strip())
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        for _ in range(10):
                            try:
                                os.kill(pid, 0)
                                time.sleep(1)
                            except ProcessLookupError:
                                daemon_stopped = True
                                break
                        if not daemon_stopped:
                            try:
                                os.kill(pid, signal.SIGKILL)
                                time.sleep(1)
                                daemon_stopped = True
                            except ProcessLookupError:
                                daemon_stopped = True
                except Exception:
                    pass

                home = Path.home()
                for plist_name in ("com.readme-sync.daemon.plist", "com.readme-sync.plist"):
                    plist_path = home / "Library" / "LaunchAgents" / plist_name
                    if plist_path.exists():
                        try:
                            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
                        except Exception:
                            pass
                        try:
                            plist_path.unlink()
                            unloaded.append(str(plist_path))
                        except Exception:
                            pass

            def _do_reset_remove():
                # Remove database, state and residuals
                names = (
                    "database.db", "sync_data.db",
                    "daemon.pid", "daemon.status", "daemon.log",
                    "launchd.out", "launchd.err",
                    "scan_folders.json"
                )
                for name in names:
                    p = conf_dir / name
                    try:
                        if p.exists():
                            p.unlink()
                            removed.append(str(p))
                    except Exception:
                        pass
                # Remove sqlite sidecar files and generic logs
                for pat in ("*.db-wal", "*.db-shm", "*.log"):
                    for fp in conf_dir.glob(pat):
                        try:
                            fp.unlink()
                            removed.append(str(fp))
                        except Exception:
                            pass
                # Remove logs directory if present
                logs_dir = conf_dir / "logs"
                if logs_dir.exists() and logs_dir.is_dir():
                    import shutil
                    try:
                        shutil.rmtree(logs_dir)
                        removed.append(str(logs_dir))
                    except Exception:
                        pass

            def _do_reset_start():
                nonlocal restarted, start_cmd
                # Try to start via CLI entrypoint
                # Prefer 'readme-sync daemon start'
                cmd = None
                from shutil import which
                if which("readme-sync"):
                    cmd = ["readme-sync", "daemon", "start"]
                else:
                    # Fallback
                    py = which("python3") or which("python") or "python3"
                    cmd = [py, "-m", "readme_sync.cli", "daemon", "start"]
                start_cmd = " ".join(cmd)
                try:
                    env = os.environ.copy()
                    # Ensure overrides propagate to daemon
                    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
                    # Small wait and check pid file appears
                    time.sleep(1.0)
                    if (conf_dir / "daemon.pid").exists() and res.returncode == 0:
                        restarted = True
                except Exception:
                    restarted = False

            cap_out, cap_err = "", ""
            with contextlib.redirect_stdout(io.StringIO()) as _out, contextlib.redirect_stderr(io.StringIO()) as _err:
                _do_reset_stop()
                _do_reset_remove()
                _do_reset_start()
                cap_out = _out.getvalue()
                cap_err = _err.getvalue()

            print(json.dumps({
                "success": True,
                "mode": "reset",
                "daemon_stopped": daemon_stopped,
                "launchagents_removed": unloaded,
                "removed": removed,
                "config_dir": str(conf_dir),
                "restarted": restarted,
                "start_cmd": start_cmd,
                "logs": {
                    "stdout": cap_out,
                    "stderr": cap_err,
                },
            }, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({
            "success": False,
            "mode": args.mode,
            "error": {
                "type": "RuntimeError",
                "message": str(e),
            }
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
