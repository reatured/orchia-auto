#!/usr/bin/env python3
"""Focused validation for handoff intake path safety and lifecycle refresh."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server


def finished_process_id() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=10)
    return process.pid


def with_temp_handoff_globals(callback):
    original_sources = server.HANDOFF_SOURCES
    original_log_dir = server.SPAWN_LOG_DIR
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "handoffs" / "frontend-audits"
            log_dir = tmp_path / "logs"
            source_dir.mkdir(parents=True)
            log_dir.mkdir()
            server.HANDOFF_SOURCES = {"frontend-audits": source_dir}
            server.SPAWN_LOG_DIR = log_dir
            callback(source_dir, log_dir)
    finally:
        server.HANDOFF_SOURCES = original_sources
        server.SPAWN_LOG_DIR = original_log_dir


def test_safe_handoff_path():
    def run(source_dir, _log_dir):
        good = source_dir / "audit.md"
        good.write_text("# Audit\n", encoding="utf-8")
        nested_dir = source_dir / "nested"
        nested_dir.mkdir()
        nested = nested_dir / "audit.md"
        nested.write_text("# Nested\n", encoding="utf-8")

        assert server.safe_handoff_path("frontend-audits", "audit.md") == good.resolve()
        assert server.safe_handoff_path("frontend-audits", "nested/audit.md") == nested.resolve()
        assert server.safe_handoff_path("frontend-audits", "../board.json") is None
        assert server.safe_handoff_path("frontend-audits", "/tmp/audit.md") is None
        assert server.safe_handoff_path("frontend-audits", "nested/../audit.md") is None
        assert server.safe_handoff_path("frontend-audits", "audit.txt") is None
        assert server.safe_handoff_path("unknown", "audit.md") is None
        print("PASS: safe handoff path validation")

    with_temp_handoff_globals(run)


def test_refresh_processed_with_source_tasks():
    def run(_source_dir, log_dir):
        log_path = log_dir / "planner.log"
        log_path.write_text("thinking\nresult (success)\ncreated tasks\n", encoding="utf-8")
        handoff_path = "handoffs/frontend-audits/audit.md"
        board = {
            "columns": {
                "todo": [
                    {
                        "id": "TASK-1",
                        "title": "Fix visual issue",
                        "status": "todo",
                        "sourceHandoffs": [handoff_path],
                    }
                ]
            }
        }
        state = {
            "handoffs": [
                {
                    "path": handoff_path,
                    "status": "planner-working",
                    "processId": finished_process_id(),
                    "spawnedAt": server.now_iso(),
                    "logPath": str(log_path),
                }
            ]
        }

        assert server.refresh_handoff_state(state, board) is True
        entry = state["handoffs"][0]
        assert entry["status"] == "processed"
        assert entry["taskIds"] == ["TASK-1"]
        assert entry["tasks"][0]["title"] == "Fix visual issue"
        print("PASS: completed planner run records source-linked tasks")

    with_temp_handoff_globals(run)


def test_refresh_skipped_without_source_tasks():
    def run(_source_dir, log_dir):
        log_path = log_dir / "planner.log"
        log_path.write_text("thinking\nresult (success)\nno new tasks\n", encoding="utf-8")
        state = {
            "handoffs": [
                {
                    "path": "handoffs/frontend-audits/no-action.md",
                    "status": "planner-working",
                    "processId": finished_process_id(),
                    "spawnedAt": server.now_iso(),
                    "logPath": str(log_path),
                }
            ]
        }

        assert server.refresh_handoff_state(state, {"columns": {"todo": []}}) is True
        entry = state["handoffs"][0]
        assert entry["status"] == "skipped"
        assert "without creating" in entry["error"]
        print("PASS: completed planner run without source-linked tasks becomes skipped")

    with_temp_handoff_globals(run)


def main():
    tests = [
        test_safe_handoff_path,
        test_refresh_processed_with_source_tasks,
        test_refresh_skipped_without_source_tasks,
    ]
    for test in tests:
        test()
    print(f"Results: {len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    main()
