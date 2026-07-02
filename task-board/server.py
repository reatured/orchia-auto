from __future__ import annotations

import json
import copy
import os
import re
import secrets
import signal
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def load_config() -> dict:
    """Project-specific settings live in config.json so this server stays generic.

    Edit task-board/config.json to adapt the starter to a new project; never
    hardcode project names, owners, ports, or paths into this file.
    """
    defaults = {
        "projectName": "Your Project Name",
        "boardTitle": "Project Task Board",
        "owner": "owner",
        "ownerLabel": "the project owner",
        "devServerUrl": "http://localhost:3000",
        "host": "127.0.0.1",
        "port": 4177,
        "projectRoot": "..",
        "spawn": {"claudeCommand": "claude", "codexCommand": "codex"},
    }
    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                if key.startswith("_"):
                    continue
                defaults[key] = value
    except FileNotFoundError:
        print(f"config.json not found at {CONFIG_PATH}; using built-in defaults.")
    except json.JSONDecodeError as error:
        print(f"config.json is invalid JSON ({error}); using built-in defaults.")
    return defaults


CONFIG = load_config()
BOARD_TITLE = str(CONFIG.get("boardTitle") or "Project Task Board")
DEFAULT_REQUESTED_BY = str(CONFIG.get("owner") or "owner")
OWNER_LABEL = str(CONFIG.get("ownerLabel") or DEFAULT_REQUESTED_BY)
DEV_SERVER_URL = str(CONFIG.get("devServerUrl") or "http://localhost:3000").rstrip("/")
SERVER_HOST = str(CONFIG.get("host") or "127.0.0.1")
try:
    SERVER_PORT = int(CONFIG.get("port") or 4177)
except (TypeError, ValueError):
    SERVER_PORT = 4177
_spawn_cfg = CONFIG.get("spawn") if isinstance(CONFIG.get("spawn"), dict) else {}
CLAUDE_COMMAND = str(_spawn_cfg.get("claudeCommand") or "claude")
CODEX_COMMAND = str(_spawn_cfg.get("codexCommand") or "codex")
QWEN_COMMAND = str(_spawn_cfg.get("qwenCommand") or "qwen")
# projectRoot in config.json is resolved relative to this task-board/ folder.
PROJECT_ROOT = (ROOT / str(CONFIG.get("projectRoot") or "..")).resolve()

BOARD_PATH = ROOT / "board.json"
ACTIVE_AGENTS_PATH = ROOT / "active-agents.json"
AGENT_SCHEMA_PATH = ROOT / "agent-color-schema.json"
API_LOG_PATH = ROOT / "task-board-api.log"
VIEWER_LOG_PATH = ROOT / "task-board-viewer.log"
SPAWN_LOG_DIR = ROOT / "spawned-agent-logs"
CODEX_SQLITE_STATE_DIR = ROOT / "codex-sqlite-state"
DISPATCH_SETTINGS_PATH = ROOT / "agent-dispatch-settings.json"
WORKFLOW_MAP_PATH = ROOT / "workflow-map.json"
WORKFLOW_AGENT_CHAT_DIR = ROOT / "workflow-agent-chat"
WORKFLOW_AGENT_CHAT_SESSION_PATH = WORKFLOW_AGENT_CHAT_DIR / "session.json"
PLANNER_CHAT_DIR = ROOT / "planner-chat"
PLANNER_CHAT_SESSION_PATH = PLANNER_CHAT_DIR / "session.json"
PLANNER_CHAT_LOG_DIR = PLANNER_CHAT_DIR / "logs"
PLANNER_CHAT_OUTPUT_LIMIT = 20000
SERVER_STARTED_AT = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
SERVER_STARTED_MONOTONIC = time.monotonic()
BOARD_LOCK = threading.RLock()
API_LOG_LOCK = threading.Lock()
VIEWER_LOG_LOCK = threading.Lock()
ACTIVE_AGENTS_LOCK = threading.Lock()
DISPATCH_SETTINGS_LOCK = threading.Lock()
WORKFLOW_MAP_LOCK = threading.RLock()
WORKFLOW_AGENT_CHAT_LOCK = threading.Lock()
PLANNER_CHAT_LOCK = threading.Lock()
AGENT_LOG_STATE_CACHE_LOCK = threading.Lock()
AGENT_LOG_STATE_BUILD_LOCK = threading.Lock()
AGENT_LOG_STATE_CACHE_TTL_SECONDS = 3.0
AGENT_LOG_STATE_CACHE = {
    "expiresAt": 0.0,
    "state": None,
}
ACTIVE_AGENT_STALE_SECONDS = 10 * 60
AUTO_DISPATCH_INTERVAL_SECONDS = 5
DISPATCH_PENDING_SECONDS = 120
HEALTH_CHECK_TIMEOUT_SECONDS = 90
HEALTH_CHECK_PROMPT = "Reply exactly: OK"
PAUSE_INCREMENT_SECONDS = 60 * 60
PID_START_TOLERANCE_SECONDS = 30
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
PAUSED_RUN_RETRYABLE_STATES = {"waiting", "resume-pending", "resume-failed"}
GET_ACTIONS = {
    "/api/board": "get_board",
    "/api/worker-board": "get_worker_board",
    "/api/review-board": "get_review_board",
    "/api/task": "get_task",
    "/api/task-detail": "get_task_detail",
    "/api/duplicate-scan": "get_duplicate_scan",
    "/api/agents": "get_agents",
    "/api/agent-schema": "get_agent_schema",
    "/api/agent-logs": "get_agent_logs",
    "/api/agent-log-content": "get_agent_log_content",
    "/api/pause": "get_pause_status",
    "/api/pause-status": "get_pause_status",
    "/api/planner-chat": "planner_chat_poll",
    "/api/workflow-map": "get_workflow_map",
    "/api/workflow-handoff-files": "get_workflow_handoff_files",
    "/api/next-worker-task": "next_worker_task",
    "/api/next-review-task": "next_review_task",
    "/api/system-status": "get_system_status",
}
VIEWER_GET_ACTIONS = {
    "/viewer/board": "get_board",
    "/viewer/worker-board": "get_worker_board",
    "/viewer/review-board": "get_review_board",
    "/viewer/task": "get_task",
    "/viewer/task-detail": "get_task_detail",
    "/viewer/duplicate-scan": "get_duplicate_scan",
    "/viewer/agents": "get_agents",
    "/viewer/agent-schema": "get_agent_schema",
    "/viewer/agent-logs": "get_agent_logs",
    "/viewer/agent-log-content": "get_agent_log_content",
    "/viewer/dispatch-settings": "get_dispatch_settings",
    "/viewer/pause": "get_pause_status",
    "/viewer/pause-status": "get_pause_status",
    "/viewer/planner-chat": "planner_chat_poll",
    "/viewer/workflow-map": "get_workflow_map",
    "/viewer/workflow-handoff-files": "get_workflow_handoff_files",
    "/viewer/workflow-chat": "workflow_chat_poll",
    "/viewer/system-status": "get_system_status",
}
POST_ACTIONS = {
    "/api/add-task": "add_task",
    "/api/update-task": "update_task",
    "/api/delete-task": "delete_task",
    "/api/archive": "archive_task",
    "/api/return-to-review": "return_task_to_review",
    "/api/claim-task": "claim_task",
    "/api/unclaim-task": "unclaim_task",
    "/api/move-to-review": "move_to_review",
    "/api/claim-review": "claim_review",
    "/api/approve-review": "approve_review",
    "/api/request-changes": "request_changes",
    "/api/register-agent": "register_agent",
    "/api/heartbeat-agent": "heartbeat_agent",
    "/api/unregister-agent": "unregister_agent",
    "/api/spawn-agent": "spawn_agent",
    "/api/terminate-agent": "terminate_agent",
    "/api/agent-health-check": "agent_health_check",
    "/api/hard-stop": "hard_stop_spawned_agents",
    "/api/hard-stop-spawned-agents": "hard_stop_spawned_agents",
    "/api/pause": "pause_plus_one_hour",
    "/api/pause-plus-one-hour": "pause_plus_one_hour",
    "/api/resume-now": "resume_now",
    "/api/planner-chat-send": "planner_chat_send",
    "/api/planner-chat-clear": "planner_chat_clear",
    "/api/workflow-map-replace": "workflow_map_replace",
    "/api/claim-next-worker": "claim_next_worker",
    "/api/claim-next-review": "claim_next_review",
}
BOARD_WRITE_ACTIONS = {
    "add_task",
    "update_task",
    "delete_task",
    "archive_task",
    "return_task_to_review",
    "claim_task",
    "unclaim_task",
    "terminate_agent",
    "move_to_review",
    "claim_review",
    "approve_review",
    "request_changes",
    "claim_next_worker",
    "claim_next_review",
}
VIEWER_POST_ACTIONS = {
    "/viewer/archive": "archive_task",
    "/viewer/return-to-review": "return_task_to_review",
    "/viewer/unclaim-task": "unclaim_task",
    "/viewer/spawn-agent": "spawn_agent",
    "/viewer/terminate-agent": "terminate_agent",
    "/viewer/agent-health-check": "agent_health_check",
    "/viewer/dispatch-settings": "update_dispatch_settings",
    "/viewer/hard-stop": "hard_stop_spawned_agents",
    "/viewer/hard-stop-spawned-agents": "hard_stop_spawned_agents",
    "/viewer/pause": "pause_plus_one_hour",
    "/viewer/pause-plus-one-hour": "pause_plus_one_hour",
    "/viewer/resume-now": "resume_now",
    "/viewer/planner-chat-send": "planner_chat_send",
    "/viewer/planner-chat-clear": "planner_chat_clear",
    "/viewer/workflow-chat-send": "workflow_chat_send",
    "/viewer/workflow-chat-clear": "workflow_chat_clear",
    "/viewer/workflow-map-replace": "workflow_map_replace",
    "/viewer/workflow-map-reset": "workflow_map_reset",
}
SPAWNABLE_AGENT_ROLES = {"worker", "review"}
SPAWNABLE_TOOLS = {"claude", "codex", "qwen"}
DEFAULT_PLANNER_MODEL = "claude"
DEFAULT_DISPATCH_MODEL = "codex"
BOARD_COLUMN_ORDER = ["todo", "claimed", "review", "reviewing", "done", "archived"]
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
TASK_TERMINAL_COLUMNS = {"done", "archived"}
COMPACT_BOARD_OMITTED_KEYS = [
    "workflowDocs",
    "readerView",
    "transitionApi",
    "roleSeparation",
    "reviewPolicy",
    "conflictPolicy",
    "tasks",
    "apiAuditLog",
]
DUPLICATE_SCAN_DEFAULT_LIMIT = 25
DUPLICATE_SCAN_MAX_LIMIT = 75
TEXT_PREVIEW_LIMIT = 700
TOKEN_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}
AGENT_ROLE_START_PHRASES = {
    "planning": "load as planner",
    "planner": "load as planner",
    "worker": "load as worker",
    "review": "load as reviewer",
    "reviewer": "load as reviewer",
}


class JsonResponseError(Exception):
    def __init__(self, message: str, status: int = 400, payload: dict | None = None):
        super().__init__(message)
        self.status = status
        self.payload = dict(payload or {})
        self.payload.setdefault("error", message)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def compute_elapsed_seconds(start_iso: str, end_iso: str) -> int | None:
    start_dt = parse_iso_datetime(start_iso)
    end_dt = parse_iso_datetime(end_iso)
    if not start_dt or not end_dt:
        return None
    delta = int((end_dt - start_dt).total_seconds())
    return delta if delta >= 0 else None


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m"


def parse_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_count_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = re.sub(r"[\s,._]+", "", text)
    if not normalized.isdigit():
        return None
    parsed = int(normalized)
    return parsed if parsed >= 0 else None


def strip_terminal_control_sequences(text: str) -> str:
    clean = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", str(text or ""))
    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", clean)
    clean = clean.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", clean)


class TerminalSessionMonitor:
    def __init__(self, pid: int, done_path: str, exit_path: str, spawned_at: str):
        self.pid = pid
        self.done_path = str(done_path or "")
        self.exit_path = str(exit_path or "")
        self.spawned_at = str(spawned_at or "")

    def wait(self) -> int:
        while True:
            if self.done_path and Path(self.done_path).exists():
                exit_text = ""
                try:
                    exit_text = Path(self.exit_path).read_text(encoding="utf-8").strip()
                except (FileNotFoundError, OSError):
                    exit_text = ""
                return parse_optional_int(exit_text) or 0
            if self.pid:
                status = spawned_process_status({
                    "processId": self.pid,
                    "spawnedAt": self.spawned_at,
                })
                if not status.get("isRunning"):
                    return 1
            time.sleep(0.5)


def default_dispatch_settings() -> dict:
    return {
        "version": 1,
        "updatedAt": "",
        "commands": {
            "claude": CLAUDE_COMMAND,
            "codex": CODEX_COMMAND,
            "qwen": QWEN_COMMAND,
        },
        "planner": {
            "model": DEFAULT_PLANNER_MODEL,
        },
        "workflow": {
            "model": DEFAULT_DISPATCH_MODEL,
        },
        "worker": {
            "enabled": False,
            "model": DEFAULT_DISPATCH_MODEL,
            "maxAgents": 1,
        },
        "review": {
            "enabled": False,
            "model": DEFAULT_DISPATCH_MODEL,
            "maxAgents": 1,
        },
        "pause": {
            "pausedUntil": "",
            "pausedBy": "",
            "pausedAt": "",
            "pauseReason": "",
        },
        "pausedRuns": [],
        "pendingSpawns": [],
    }


def default_workflow_map() -> dict:
    return {
        "version": 1,
        "updatedAt": "",
        "nodes": [
            {
                "id": "planner",
                "detailKey": "planning-agent",
                "kind": "Agent",
                "label": "Planner",
                "color": "#476f8f",
                "meta": "Turns requirements into todo cards.",
                "acceptsHumanInput": True,
                "locked": True,
                "rules": [],
            },
            {
                "id": "worker",
                "detailKey": "worker-agent",
                "kind": "Agent",
                "label": "Worker",
                "color": "var(--claimed)",
                "meta": "Claims todo work, implements it, and requests review.",
                "locked": True,
                "rules": [],
            },
            {
                "id": "reviewer",
                "detailKey": "review-agent",
                "kind": "Agent",
                "label": "Reviewer",
                "color": "#7f6cae",
                "meta": "Claims review work, validates it, and decides outcome.",
                "locked": True,
                "rules": [],
                "outputs": [
                    {
                        "id": "reviewer-done-output",
                        "type": "human-readable-output",
                        "renderAs": "board-column",
                        "label": "Done",
                        "description": "Accepted work and failed reviewed attempts that the owner can read and archive.",
                        "visualColumnKey": "done",
                        "columnKey": "done",
                        "sourceKeys": ["done"],
                        "color": "var(--done)",
                    }
                ],
            },
        ],
        "rows": [
            ["planner"],
            ["worker"],
            ["reviewer"],
        ],
        "edges": [
            {
                "from": "planner",
                "to": "worker",
                "label": "todo tickets",
                "outputs": [
                    {
                        "id": "planner-worker-todo-tickets",
                        "type": "task-board-ticket",
                        "renderAs": "board-column",
                        "label": "To Do",
                        "description": "Planner-created tickets ready for Workers to claim.",
                        "visualColumnKey": "todo",
                        "columnKey": "todo",
                        "sourceKeys": ["claimed", "todo"],
                        "agentRole": "worker",
                        "agentLabel": "Workers",
                        "color": "var(--todo)",
                    }
                ],
            },
            {
                "from": "worker",
                "to": "reviewer",
                "label": "inspection targets + review request",
                "outputs": [
                    {
                        "id": "worker-reviewer-review-tickets",
                        "type": "task-board-ticket",
                        "renderAs": "board-column",
                        "label": "Review",
                        "description": "Worker-completed tickets waiting for reviewer inspection.",
                        "visualColumnKey": "review",
                        "columnKey": "review",
                        "sourceKeys": ["reviewing", "review"],
                        "agentRole": "review",
                        "agentLabel": "Reviewers",
                        "color": "var(--review)",
                    }
                ],
            },
        ],
        "globalRules": [
            {
                "id": "core-source-of-truth",
                "title": "Source of truth",
                "text": "Workflow map outputs describe agent coordination and drive viewer rendering for task-board lanes and handoff-file sections. Task movement still happens through board.json and the task-board API.",
            }
        ],
    }


def workflow_slug(value: object, fallback: str = "workflow-node") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def compact_workflow_text(value: object, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def workflow_color_for_kind(kind: str, index: int = 0) -> str:
    if kind.lower() == "step":
        return "#8c6f40"
    palette = ["#476f8f", "#0f766e", "#8a6f22", "#7f6cae", "#b35c1e", "#2f855a"]
    return palette[index % len(palette)]


def normalize_dispatch_model(value: object, fallback: str = DEFAULT_DISPATCH_MODEL) -> str:
    model = str(value or "").strip().lower()
    if model in SPAWNABLE_TOOLS:
        return model
    return fallback if fallback in SPAWNABLE_TOOLS else DEFAULT_DISPATCH_MODEL


def normalize_dispatch_role(value: object) -> str:
    role = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if role in {"planner", "planning", "planner-chat", "planning-agent"}:
        return "planner"
    if role in {"workflow", "workflow-agent", "workflow-chat", "workflow-map"}:
        return "workflow"
    if role in {"worker", "worker-agent"}:
        return "worker"
    if role in {"review", "reviewer", "review-agent", "reviewer-agent"}:
        return "review"
    return role


def normalize_max_agents(value: object, fallback: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(0, min(parsed, 8))


def normalize_spawn_command(value: object, fallback: str) -> str:
    command = str(value or "").strip()
    fallback_command = str(fallback or "").strip()
    return command or fallback_command


def normalize_pause_state(value: object) -> dict:
    source = value if isinstance(value, dict) else {}
    return {
        "pausedUntil": str(source.get("pausedUntil", "") or "").strip(),
        "pausedBy": str(source.get("pausedBy", "") or "").strip(),
        "pausedAt": str(source.get("pausedAt", "") or "").strip(),
        "pauseReason": str(source.get("pauseReason", "") or "").strip(),
    }


def seconds_remaining_until(value: datetime, now: datetime) -> int:
    try:
        return max(0, int((local_process_datetime(value) - local_process_datetime(now)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return 0


def format_remaining_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def pause_status_from_settings(settings: dict, now: datetime | None = None) -> dict:
    pause_state = normalize_pause_state(settings.get("pause") if isinstance(settings, dict) else {})
    current_time = now or datetime.now(timezone.utc).astimezone()
    paused_until = parse_iso_datetime(pause_state.get("pausedUntil"))
    remaining_seconds = 0
    is_paused = False
    if paused_until:
        remaining_seconds = seconds_remaining_until(paused_until, current_time)
        is_paused = remaining_seconds > 0
    message = ""
    if is_paused:
        message = (
            f"Task board is paused until {pause_state['pausedUntil']} "
            f"({format_remaining_time(remaining_seconds)} remaining)."
        )
    return {
        "isPaused": is_paused,
        "pausedUntil": pause_state["pausedUntil"] if is_paused else "",
        "pausedBy": pause_state["pausedBy"] if is_paused else "",
        "pausedAt": pause_state["pausedAt"] if is_paused else "",
        "pauseReason": pause_state["pauseReason"] if is_paused else "",
        "remainingSeconds": remaining_seconds if is_paused else 0,
        "remainingText": format_remaining_time(remaining_seconds) if is_paused else "0s",
        "message": message,
    }


def active_pause_status(now: datetime | None = None) -> dict:
    return pause_status_from_settings(load_dispatch_settings(), now=now)


def paused_error_payload(status: dict) -> dict:
    return {
        "error": status.get("message") or "Task board is paused.",
        "paused": True,
        "isPaused": bool(status.get("isPaused")),
        "pausedUntil": status.get("pausedUntil", ""),
        "remainingSeconds": status.get("remainingSeconds", 0),
        "remainingText": status.get("remainingText", "0s"),
        "pauseReason": status.get("pauseReason", ""),
    }


def common_executable_search_path() -> str:
    paths = [
        os.environ.get("PATH", ""),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".npm-global" / "bin"),
        str(Path.home() / ".yarn" / "bin"),
        str(Path.home() / ".bun" / "bin"),
        str(Path.home() / "AppData" / "Roaming" / "npm"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")
    program_files = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramW6432"),
    ]
    if local_app_data:
        paths.append(str(Path(local_app_data) / "Programs" / "OpenAI" / "Codex" / "bin"))
        paths.append(str(Path(local_app_data) / "Programs" / "nodejs"))
    if app_data:
        paths.append(str(Path(app_data) / "npm"))
    for root in program_files:
        if root:
            paths.append(str(Path(root) / "nodejs"))
    seen = set()
    cleaned = []
    for raw_path in paths:
        for part in str(raw_path or "").split(os.pathsep):
            path = part.strip()
            if path and path not in seen:
                seen.add(path)
                cleaned.append(path)
    return os.pathsep.join(cleaned)


def agent_subprocess_env(tool: str = "") -> dict:
    env = os.environ.copy()
    if tool == "codex" and not str(env.get("CODEX_SQLITE_HOME", "") or "").strip():
        CODEX_SQLITE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        env["CODEX_SQLITE_HOME"] = str(CODEX_SQLITE_STATE_DIR)
    if tool == "qwen":
        env["FORCE_COLOR"] = "0"
        env["NO_COLOR"] = "1"
        env["QWEN_CODE_DEBUG"] = "1"
    return env


def _qwen_process_isolation_kwargs() -> dict:
    """Return Popen kwargs that isolate Qwen child processes from backend signals.

    On POSIX, start_new_session=True puts the child in a new session and process
    group so backend SIGINT/SIGTERM (e.g. Ctrl-C in the backend terminal) does
    not propagate to spawned Qwen agents or their formatter subprocesses.
    Hard-stop sends SIGTERM directly to the child PID, so explicit termination
    still works regardless of process-group isolation.

    Returns an empty dict on Windows where process groups work differently.
    """
    if os.name == "nt":
        return {}
    return {"start_new_session": True}


def _signal_name(returncode: int) -> str:
    """Return a human-readable signal name for a negative return code."""
    sig_num = -returncode
    try:
        return signal.Signals(sig_num).name
    except (ValueError, AttributeError):
        return f"signal {sig_num}"


def _run_qwen_formatter_pipe(
    qwen_proc: "subprocess.Popen",
    log_fh,
    fmt_script: str,
):
    """Pipe Qwen stream-json stdout through the formatter, logging exit status.

    Runs in a daemon thread started by the caller.  Both the Qwen process and the
    formatter are launched with process-session isolation so backend Ctrl-C does
    not propagate.  Explicit hard-stop still targets the Qwen PID directly.

    After both processes exit, writes a clear final-status block to the log so the
    owner does not have to infer from a dangling traceback.
    """
    isolation = _qwen_process_isolation_kwargs()
    fmt_proc = None
    try:
        fmt_proc = subprocess.Popen(
            [sys.executable, "-u", fmt_script],
            stdin=qwen_proc.stdout,
            stdout=log_fh,
            stderr=log_fh,
            **isolation,
        )
        fmt_proc.wait()
    except Exception:
        pass
    finally:
        try:
            qwen_proc.stdout.close()
        except Exception:
            pass

    qwen_rc = qwen_proc.wait()
    qwen_status = f"return code {qwen_rc}" if qwen_rc >= 0 else f"{_signal_name(qwen_rc)} (code {qwen_rc})"
    fmt_rc = fmt_proc.returncode if fmt_proc is not None else None
    fmt_status = (
        f"return code {fmt_rc}" if fmt_rc is not None and fmt_rc >= 0
        else (f"{_signal_name(fmt_rc)} (code {fmt_rc})" if fmt_rc is not None else "unknown")
    )

    try:
        log_fh.write(f"\n--- Process exit status ---\n")
        log_fh.write(f"qwen:      {qwen_status}\n")
        log_fh.write(f"formatter: {fmt_status}\n")
        log_fh.flush()
    except Exception:
        pass
    try:
        log_fh.close()
    except Exception:
        pass


def health_check_suggestion(tool: str, status: str, error: object, output: object) -> str:
    text = f"{error or ''}\n{output or ''}".lower()
    if status == "not-found" or "no such file or directory" in text:
        return f"Install {tool}, or set the full command path in Settings."
    if "not in a trusted directory" in text or "trusted directory" in text:
        return f"Open regular {tool} once inside the project folder and approve/trust the directory."
    if "readonly database" in text or "read-only database" in text:
        return "Codex state is read-only. The workflow now uses a local writable SQLite state folder; restart the backend and test again."
    if (
        "access token" in text
        or "not authenticated" in text
        or "not signed in" in text
        or "authentication" in text
        or "api key" in text
        or "unauthorized" in text
        or "login" in text
        or "sign in" in text
    ):
        return f"Sign in to {tool} on this laptop, then run the health check again."
    if status == "timeout":
        return f"{tool} started but did not finish the tiny test prompt. Try running it once manually in Terminal."
    return ""


def normalize_dispatch_settings(settings: dict | None) -> dict:
    normalized = default_dispatch_settings()
    if not isinstance(settings, dict):
        return normalized
    normalized["version"] = settings.get("version") or 1
    normalized["updatedAt"] = str(settings.get("updatedAt", "") or "").strip()
    source_commands = settings.get("commands")
    if not isinstance(source_commands, dict):
        source_commands = {}
    normalized["commands"] = {
        "claude": normalize_spawn_command(source_commands.get("claude"), CLAUDE_COMMAND),
        "codex": normalize_spawn_command(source_commands.get("codex"), CODEX_COMMAND),
        "qwen": normalize_spawn_command(source_commands.get("qwen"), QWEN_COMMAND),
    }
    planner_source = settings.get("planner")
    if not isinstance(planner_source, dict):
        planner_source = settings.get("planning")
    if not isinstance(planner_source, dict):
        planner_source = {}
    normalized["planner"] = {
        "model": normalize_dispatch_model(planner_source.get("model"), normalized["planner"]["model"]),
    }
    workflow_source = settings.get("workflow")
    if not isinstance(workflow_source, dict):
        workflow_source = {}
    normalized["workflow"] = {
        "model": normalize_dispatch_model(workflow_source.get("model"), normalized["workflow"]["model"]),
    }
    for role in ("worker", "review"):
        source = settings.get(role)
        if not isinstance(source, dict):
            source = {}
        normalized[role] = {
            "enabled": bool(source.get("enabled", normalized[role]["enabled"])),
            "model": normalize_dispatch_model(source.get("model"), normalized[role]["model"]),
            "maxAgents": normalize_max_agents(source.get("maxAgents"), normalized[role]["maxAgents"]),
        }
    normalized["pause"] = normalize_pause_state(settings.get("pause"))
    paused_runs = settings.get("pausedRuns")
    normalized["pausedRuns"] = paused_runs if isinstance(paused_runs, list) else []
    pending = settings.get("pendingSpawns")
    normalized["pendingSpawns"] = pending if isinstance(pending, list) else []
    return normalized


def load_dispatch_settings() -> dict:
    with DISPATCH_SETTINGS_LOCK:
        if DISPATCH_SETTINGS_PATH.exists():
            try:
                raw = json.loads(DISPATCH_SETTINGS_PATH.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                raw = {}
        else:
            raw = {}
        return normalize_dispatch_settings(raw)


def clear_agent_log_state_cache() -> None:
    with AGENT_LOG_STATE_CACHE_LOCK:
        AGENT_LOG_STATE_CACHE["expiresAt"] = 0.0
        AGENT_LOG_STATE_CACHE["state"] = None


def persist_dispatch_settings(settings: dict) -> None:
    normalized = normalize_dispatch_settings(settings)
    with DISPATCH_SETTINGS_LOCK:
        temp_path = DISPATCH_SETTINGS_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, DISPATCH_SETTINGS_PATH)
    clear_agent_log_state_cache()


def parse_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_process_id(value: object) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def filetime_to_datetime(filetime: wintypes.FILETIME) -> datetime | None:
    value = (int(filetime.dwHighDateTime) << 32) + int(filetime.dwLowDateTime)
    if value <= 0:
        return None
    unix_seconds = (value - 116444736000000000) / 10000000
    try:
        return datetime.fromtimestamp(unix_seconds, timezone.utc).astimezone()
    except (OSError, OverflowError, ValueError):
        return None


def local_process_datetime(value: datetime) -> datetime:
    local_tz = datetime.now(timezone.utc).astimezone().tzinfo
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=local_tz)
    return value.astimezone(local_tz)


def process_started_before_spawn(created_at: datetime | None, spawned_at: datetime | None) -> bool:
    if not created_at or not spawned_at:
        return False
    try:
        created = local_process_datetime(created_at)
        spawned = local_process_datetime(spawned_at)
        return (spawned - created).total_seconds() > PID_START_TOLERANCE_SECONDS
    except (TypeError, OverflowError, ValueError):
        return False


def parse_ps_lstart(value: str) -> datetime | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    return local_process_datetime(parsed)


def posix_process_started_at(pid: int) -> datetime | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return parse_ps_lstart(result.stdout)


def posix_process_stat(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def windows_process_status(pid: int, spawned_at: datetime | None) -> dict:
    checked_at = now_iso()
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            error_code = ctypes.get_last_error()
            state = "unknown" if error_code == 5 else "exited"
            return {
                "processId": pid,
                "isRunning": False,
                "state": state,
                "checkedAt": checked_at,
                "errorCode": error_code,
            }

        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return {
                    "processId": pid,
                    "isRunning": False,
                    "state": "unknown",
                    "checkedAt": checked_at,
                    "errorCode": ctypes.get_last_error(),
                }

            running = int(exit_code.value) == STILL_ACTIVE
            creation_time = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            created_at = None
            if kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation_time),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                created_at = filetime_to_datetime(creation_time)

            if running and created_at and spawned_at:
                if process_started_before_spawn(created_at, spawned_at):
                    return {
                        "processId": pid,
                        "isRunning": False,
                        "state": "pid-reused",
                        "checkedAt": checked_at,
                        "createdAt": created_at.isoformat(timespec="seconds"),
                    }

            return {
                "processId": pid,
                "isRunning": running,
                "state": "running" if running else "exited",
                "checkedAt": checked_at,
                "createdAt": created_at.isoformat(timespec="seconds") if created_at else "",
                "exitCode": "" if running else int(exit_code.value),
            }
        finally:
            kernel32.CloseHandle(handle)
    except Exception as error:
        return {
            "processId": pid,
            "isRunning": False,
            "state": "unknown",
            "checkedAt": checked_at,
            "error": str(error),
        }


def generic_process_status(pid: int, spawned_at: datetime | None = None) -> dict:
    checked_at = now_iso()
    warning = ""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {
            "processId": pid,
            "isRunning": False,
            "state": "exited",
            "checkedAt": checked_at,
        }
    except PermissionError:
        warning = "permission-limited"
    except Exception as error:
        return {
            "processId": pid,
            "isRunning": False,
            "state": "unknown",
            "checkedAt": checked_at,
            "error": str(error),
        }

    created_at = posix_process_started_at(pid)
    if spawned_at and not created_at:
        status = {
            "processId": pid,
            "isRunning": False,
            "state": "unknown",
            "checkedAt": checked_at,
            "error": "process-start-time-unavailable",
        }
        if warning:
            status["warning"] = warning
        return status
    if process_started_before_spawn(created_at, spawned_at):
        return {
            "processId": pid,
            "isRunning": False,
            "state": "pid-reused",
            "checkedAt": checked_at,
            "createdAt": created_at.isoformat(timespec="seconds") if created_at else "",
        }
    process_stat = posix_process_stat(pid)
    if "Z" in process_stat.upper():
        return {
            "processId": pid,
            "isRunning": False,
            "state": "exited",
            "checkedAt": checked_at,
            "createdAt": created_at.isoformat(timespec="seconds") if created_at else "",
            "processState": process_stat,
        }

    status = {
        "processId": pid,
        "isRunning": True,
        "state": "running",
        "checkedAt": checked_at,
        "createdAt": created_at.isoformat(timespec="seconds") if created_at else "",
    }
    if process_stat:
        status["processState"] = process_stat
    if warning:
        status["warning"] = warning
    return status


def spawned_process_status(spawn: object) -> dict:
    if not isinstance(spawn, dict):
        return {
            "processId": 0,
            "isRunning": False,
            "state": "unknown",
            "checkedAt": now_iso(),
        }
    pid = parse_process_id(spawn.get("processId"))
    if not pid:
        if str(spawn.get("mode") or "").strip().lower() == "interactive":
            return {
                "processId": 0,
                "isRunning": True,
                "state": "interactive-terminal",
                "checkedAt": now_iso(),
            }
        return {
            "processId": 0,
            "isRunning": False,
            "state": "missing-pid",
            "checkedAt": now_iso(),
        }
    spawned_at = parse_iso_datetime(spawn.get("spawnedAt"))
    if os.name == "nt":
        return windows_process_status(pid, spawned_at)
    return generic_process_status(pid, spawned_at)


def wait_for_spawn_exit(spawn: dict, timeout_seconds: float) -> dict:
    deadline = time.monotonic() + max(0, timeout_seconds)
    latest_status = spawned_process_status(spawn)
    while time.monotonic() < deadline:
        if not is_live_pending_spawn(spawn, process_status=latest_status):
            return latest_status
        time.sleep(0.1)
        latest_status = spawned_process_status(spawn)
    return latest_status


def terminate_spawned_process(spawn: dict, status_before: dict | None = None) -> dict:
    pid = parse_process_id(spawn.get("processId") if isinstance(spawn, dict) else "")
    before = status_before if isinstance(status_before, dict) else spawned_process_status(spawn)
    result = {
        "processId": pid,
        "attempted": False,
        "terminated": False,
        "forceKilled": False,
        "stateBefore": before.get("state", "unknown"),
        "stateAfter": before.get("state", "unknown"),
        "error": "",
    }
    if not pid:
        result["error"] = "missing processId"
        return result
    if not is_live_pending_spawn(spawn, process_status=before):
        result["stateAfter"] = before.get("state", "unknown")
        return result

    result["attempted"] = True
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            after_grace = wait_for_spawn_exit(spawn, 3)
            if is_live_pending_spawn(spawn, process_status=after_grace):
                result["forceKilled"] = True
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                after_grace = wait_for_spawn_exit(spawn, 3)
            result["stateAfter"] = after_grace.get("state", "unknown")
            result["terminated"] = not is_live_pending_spawn(spawn, process_status=after_grace)
        except Exception as error:
            result["error"] = str(error)
            result["stateAfter"] = spawned_process_status(spawn).get("state", "unknown")
        return result

    try:
        os.kill(pid, signal.SIGTERM)
        after_grace = wait_for_spawn_exit(spawn, 3)
        if is_live_pending_spawn(spawn, process_status=after_grace):
            result["forceKilled"] = True
            os.kill(pid, signal.SIGKILL)
            after_grace = wait_for_spawn_exit(spawn, 2)
        result["stateAfter"] = after_grace.get("state", "unknown")
        result["terminated"] = not is_live_pending_spawn(spawn, process_status=after_grace)
    except ProcessLookupError:
        result["terminated"] = True
        result["stateAfter"] = "exited"
    except PermissionError as error:
        result["error"] = f"permission denied: {error}"
        result["stateAfter"] = spawned_process_status(spawn).get("state", "unknown")
    except OSError as error:
        result["error"] = str(error)
        result["stateAfter"] = spawned_process_status(spawn).get("state", "unknown")
    return result


def is_live_pending_spawn(
    spawn: object,
    role: str = "",
    now: datetime | None = None,
    process_status: dict | None = None,
) -> bool:
    if not isinstance(spawn, dict):
        return False
    spawn_role = str(spawn.get("role", "") or "").strip().lower()
    if role and spawn_role != role:
        return False
    if spawn_role not in SPAWNABLE_AGENT_ROLES:
        return False
    spawned_at = parse_iso_datetime(spawn.get("spawnedAt"))
    if not spawned_at:
        return False
    spawned_at = local_process_datetime(spawned_at)
    if now and (local_process_datetime(now) - spawned_at).total_seconds() > DISPATCH_PENDING_SECONDS:
        return False
    status = process_status if isinstance(process_status, dict) else spawned_process_status(spawn)
    process_state = str(status.get("state") or "").strip().lower()
    return bool(status.get("isRunning")) and process_state in {"running", "interactive-terminal"}


def is_recent_spawn(spawn: object, role: str, now: datetime) -> bool:
    del now
    return is_live_pending_spawn(spawn, role=role)


def is_active_agent_record(agent: object, role: str, now: datetime) -> bool:
    if not isinstance(agent, dict):
        return False
    if str(agent.get("role", "") or "").strip().lower() != role:
        return False
    if str(agent.get("status", "active") or "active").strip().lower() != "active":
        return False
    last_seen = parse_iso_datetime(agent.get("lastHeartbeatAt") or agent.get("registeredAt"))
    if not last_seen:
        return False
    return (now - last_seen).total_seconds() <= ACTIVE_AGENT_STALE_SECONDS


class TaskBoardHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        message = format % args
        client = self.client_address[0] if self.client_address else "-"
        print(
            f"[task-board http] {client} - {self.log_date_time_string()} {message}",
            file=sys.stderr,
            flush=True,
        )

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        if self.should_log_default_access(code):
            self.log_message('"%s" %s %s', self.requestline, str(code), str(size))

    def should_log_default_access(self, code: int | str) -> bool:
        try:
            status = int(code)
        except (TypeError, ValueError):
            status = 0
        if status < 400:
            return False
        path = urlsplit(self.path).path.rstrip("/") or "/"
        return not path.startswith("/api/") and not path.startswith("/viewer/")

    def _send_json_error(self, message: str, status: int) -> None:
        try:
            self.send_json({"error": message}, status=status)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed_url = urlsplit(self.path)
        path = parsed_url.path.rstrip("/") or "/"
        is_viewer_request = path.startswith("/viewer/")
        action = VIEWER_GET_ACTIONS.get(path) if is_viewer_request else GET_ACTIONS.get(path)
        if not action:
            if path.startswith("/api/") or is_viewer_request:
                request_at = now_iso()
                self.append_api_log({
                    "at": request_at,
                    "method": "GET",
                    "path": path,
                    "action": "",
                    "status": "error",
                    "httpStatus": 404,
                    "agentName": self.agent_name(
                        self.query_payload(parsed_url.query),
                        "Task board viewer" if is_viewer_request else "Unknown API caller",
                    ),
                    "taskIds": self.payload_task_ids(self.query_payload(parsed_url.query)),
                    "error": "Unknown endpoint",
                }, viewer=is_viewer_request)
                self.send_error(404, "Unknown endpoint")
                return
            super().do_GET()
            return

        request_at = now_iso()
        payload = self.query_payload(parsed_url.query)
        try:
            board = self.load_board()
            result = getattr(self, action)(board, payload) or {}
            self.log_api_success(request_at, path, action, payload, result, method="GET", viewer=is_viewer_request)
            self.send_json(result)
        except FileNotFoundError:
            self.log_api_error(request_at, path, action, payload, "Board file not found", 500, method="GET", viewer=is_viewer_request)
            self._send_json_error("Board file not found", status=500)
        except json.JSONDecodeError:
            self.log_api_error(request_at, path, action, payload, "Board file is not valid JSON", 500, method="GET", viewer=is_viewer_request)
            self._send_json_error("Board file is not valid JSON", status=500)
        except JsonResponseError as error:
            self.log_api_error(request_at, path, action, payload, str(error), error.status, method="GET", viewer=is_viewer_request)
            self.send_json(error.payload, status=error.status)
        except ValueError as error:
            self.log_api_error(request_at, path, action, payload, str(error), 400, method="GET", viewer=is_viewer_request)
            self._send_json_error(str(error), status=400)
        except LookupError as error:
            self.log_api_error(request_at, path, action, payload, str(error), 404, method="GET", viewer=is_viewer_request)
            self._send_json_error(str(error), status=404)
        except Exception as error:
            self.log_api_error(request_at, path, action, payload, str(error), 500, method="GET", viewer=is_viewer_request)
            self._send_json_error(str(error), status=500)

    def do_POST(self) -> None:
        parsed_url = urlsplit(self.path)
        path = parsed_url.path.rstrip("/") or "/"
        is_viewer_request = path.startswith("/viewer/")
        action = VIEWER_POST_ACTIONS.get(path) if is_viewer_request else POST_ACTIONS.get(path)
        request_at = now_iso()
        if not action:
            self.append_api_log({
                "at": request_at,
                "method": "POST",
                "path": path,
                "action": "",
                "status": "error",
                "httpStatus": 404,
                "agentName": "Task board viewer" if is_viewer_request else "Unknown API caller",
                "taskIds": [],
                "error": "Unknown endpoint",
            }, viewer=is_viewer_request)
            self.send_error(404, "Unknown endpoint")
            return

        payload = {}
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload_raw = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(payload_raw or "{}")
        except json.JSONDecodeError:
            self.log_api_error(request_at, path, action, payload, "Invalid JSON request body", 400, viewer=is_viewer_request)
            self._send_json_error("Invalid JSON request body", status=400)
            return
        except Exception:
            self.log_api_error(request_at, path, action, payload, "Unable to read request body", 400, viewer=is_viewer_request)
            self._send_json_error("Unable to read request body", status=400)
            return
        if not isinstance(payload, dict):
            self.log_api_error(request_at, path, action, {}, "JSON request body must be an object", 400, viewer=is_viewer_request)
            self._send_json_error("JSON request body must be an object", status=400)
            return

        try:
            if action in BOARD_WRITE_ACTIONS:
                with BOARD_LOCK:
                    board = self.load_board()
                    columns = self.get_columns(board)
                    result = getattr(self, action)(board, columns, payload) or {}
            else:
                board = self.load_board()
                columns = self.get_columns(board)
                result = getattr(self, action)(board, columns, payload) or {}
            self.log_api_success(request_at, path, action, payload, result, viewer=is_viewer_request)
            self.send_json(result)
        except FileNotFoundError:
            self.log_api_error(request_at, path, action, payload, "Board file not found", 500, viewer=is_viewer_request)
            self._send_json_error("Board file not found", status=500)
        except json.JSONDecodeError:
            self.log_api_error(request_at, path, action, payload, "Board file is not valid JSON", 500, viewer=is_viewer_request)
            self._send_json_error("Board file is not valid JSON", status=500)
        except JsonResponseError as error:
            self.log_api_error(request_at, path, action, payload, str(error), error.status, viewer=is_viewer_request)
            self.send_json(error.payload, status=error.status)
        except ValueError as error:
            self.log_api_error(request_at, path, action, payload, str(error), 400, viewer=is_viewer_request)
            self._send_json_error(str(error), status=400)
        except LookupError as error:
            self.log_api_error(request_at, path, action, payload, str(error), 404, viewer=is_viewer_request)
            self._send_json_error(str(error), status=404)
        except Exception as error:
            self.log_api_error(request_at, path, action, payload, str(error), 500, viewer=is_viewer_request)
            self._send_json_error(str(error), status=500)

    def query_payload(self, query: str) -> dict:
        parsed = parse_qs(query, keep_blank_values=True)
        payload = {}
        for key, values in parsed.items():
            if not values:
                payload[key] = ""
            elif len(values) == 1:
                payload[key] = values[0]
            else:
                payload[key] = values
        return payload

    def get_board(self, board: dict, payload: dict) -> dict:
        return board

    def truthy_query(self, payload: dict, field: str, default: bool = False) -> bool:
        if field not in payload:
            return default
        value = payload.get(field)
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def query_int(self, payload: dict, field: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(str(payload.get(field, default)).strip())
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(value, maximum))

    def value_list(self, value: object) -> list[str]:
        if isinstance(value, list):
            raw_values = value
        elif isinstance(value, tuple):
            raw_values = list(value)
        elif isinstance(value, str):
            raw_values = re.split(r"[,;\n]+", value)
        elif value is None:
            raw_values = []
        else:
            raw_values = [value]
        result: list[str] = []
        for item in raw_values:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    def preview_text(self, value: object, limit: int = TEXT_PREVIEW_LIMIT) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "..."

    def copy_selected_task_fields(self, task: dict, fields: list[str]) -> dict:
        summary: dict = {}
        for field in fields:
            if field not in task:
                continue
            value = task.get(field)
            if value in ("", None, [], {}):
                continue
            summary[field] = value
        return summary

    def task_summary(self, task: dict, column_name: str = "", view: str = "generic") -> dict:
        fields = [
            "id",
            "title",
            "project",
            "priority",
            "type",
            "status",
            "summary",
            "requirements",
            "acceptanceCriteria",
            "files",
            "blockers",
            "relatedTaskIds",
            "dependsOn",
            "sourceReviewTaskId",
            "redoCount",
            "claimedBy",
            "claimedAt",
            "reviewClaimedBy",
            "reviewClaimedAt",
            "reviewRequestedAt",
            "completedBy",
            "reviewedBy",
            "reviewedAt",
            "ownerFeedback",
            "returnedToReviewAt",
            "referenceImages",
            "inspectionTargets",
            "lastApiAction",
            "lastApiActor",
            "lastApiAt",
        ]
        summary = self.copy_selected_task_fields(task, fields)
        if column_name:
            summary["column"] = column_name
        if view:
            summary["view"] = view
        notes_preview = self.preview_text(task.get("notes"))
        if notes_preview:
            summary["notesPreview"] = notes_preview
        task_id = str(task.get("id", "") or "").strip()
        if task_id:
            summary["detailEndpoint"] = f"/api/task-detail?taskId={task_id}"
        return summary

    def task_detail(self, task: dict, include_history: bool = False) -> dict:
        detail = dict(task)
        if not include_history:
            detail.pop("apiHistory", None)
        return detail

    def filtered_board(self, board: dict, column_names: list[str], view: str) -> dict:
        columns = self.get_columns(board)
        compact_columns = {
            column_name: [
                self.task_summary(task, column_name, view)
                for task in columns.get(column_name, [])
                if isinstance(task, dict) and self.is_valid_task(task)
            ]
            for column_name in column_names
        }
        return {
            "schemaVersion": board.get("schemaVersion", ""),
            "boardName": board.get("boardName", BOARD_TITLE),
            "updatedAt": board.get("updatedAt", ""),
            "view": view,
            "compact": True,
            "columns": compact_columns,
            "visibleColumns": column_names,
            "detailEndpoint": "/api/task-detail?taskId=TASK-YYYYMMDD-###",
            "omittedTopLevelKeys": COMPACT_BOARD_OMITTED_KEYS,
        }

    def get_worker_board(self, board: dict, payload: dict) -> dict:
        return self.filtered_board(board, ["todo", "claimed"], "worker")

    def get_review_board(self, board: dict, payload: dict) -> dict:
        return self.filtered_board(board, ["review", "reviewing"], "review")

    def get_task(self, board: dict, payload: dict) -> dict:
        return self.get_task_detail(board, payload)

    def get_task_detail(self, board: dict, payload: dict) -> dict:
        task_id = self.require_task_id(payload)
        column_name, _, _, task = self.find_task_location(self.get_columns(board), task_id)
        include_history = self.truthy_query(payload, "includeHistory", False)
        return {
            "column": column_name,
            "task": self.task_detail(task, include_history=include_history),
            "taskIds": [task_id],
            "includes": {
                "apiHistory": include_history,
            },
        }

    def text_blob(self, value: object) -> str:
        if isinstance(value, dict):
            return " ".join(self.text_blob(item) for item in value.values())
        if isinstance(value, list):
            return " ".join(self.text_blob(item) for item in value)
        return str(value or "")

    def task_duplicate_text(self, task: dict) -> str:
        parts = [
            task.get("title"),
            task.get("project"),
            task.get("type"),
            task.get("summary"),
            task.get("requirements"),
            task.get("acceptanceCriteria"),
            task.get("notes"),
            task.get("ownerFeedback"),
        ]
        return " ".join(self.text_blob(part) for part in parts)

    def tokenize_for_duplicate_scan(self, value: object) -> set[str]:
        words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,}", self.text_blob(value).lower())
        return {
            word
            for word in words
            if word not in TOKEN_STOP_WORDS and not word.startswith("task-")
        }

    def normalized_title(self, value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    def ordered_column_names(self, columns: dict, include_archived: bool) -> list[str]:
        names = [name for name in BOARD_COLUMN_ORDER if name in columns and (include_archived or name != "archived")]
        for name in columns:
            if name not in names and (include_archived or name != "archived"):
                names.append(name)
        return names

    def duplicate_source_from_payload(self, board: dict, payload: dict) -> tuple[dict, str]:
        columns = self.get_columns(board)
        task_id = str(payload.get("taskId") or payload.get("id") or "").strip()
        if task_id:
            column_name, _, _, task = self.find_task_location(columns, task_id)
            return task, column_name
        title = str(payload.get("title") or "").strip()
        source_review_id = str(payload.get("sourceReviewTaskId") or "").strip()
        files = self.value_list(payload.get("files"))
        if not title and not source_review_id and not files:
            raise ValueError("Duplicate scan requires taskId, title, sourceReviewTaskId, or files")
        return {
            "id": "",
            "title": title,
            "summary": str(payload.get("summary") or "").strip(),
            "requirements": self.value_list(payload.get("requirements")),
            "acceptanceCriteria": self.value_list(payload.get("acceptanceCriteria")),
            "files": files,
            "sourceReviewTaskId": source_review_id,
        }, ""

    def duplicate_candidate_match(self, source_task: dict, task: dict, source_ids: set[str], source_tokens: set[str], source_files: set[str]) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        task_id = str(task.get("id") or "").strip()
        if task_id and task_id in source_ids:
            return 0, []

        candidate_source = str(task.get("sourceReviewTaskId") or "").strip()
        if candidate_source and candidate_source in source_ids:
            score += 9
            reasons.append(f"same sourceReviewTaskId {candidate_source}")

        for field in ("replacedByTaskId", "latestFollowUpTaskId"):
            value = str(task.get(field) or "").strip()
            if value and value in source_ids:
                score += 6
                reasons.append(f"{field} points to source")

        for field in ("relatedTaskIds", "dependsOn"):
            overlap = sorted(set(self.value_list(task.get(field))) & source_ids)
            if overlap:
                score += 4
                reasons.append(f"{field} overlaps {', '.join(overlap[:3])}")

        source_title = self.normalized_title(source_task.get("title"))
        candidate_title = self.normalized_title(task.get("title"))
        if source_title and candidate_title and source_title == candidate_title:
            score += 7
            reasons.append("same normalized title")

        candidate_files = set(self.value_list(task.get("files")))
        file_overlap = sorted(source_files & candidate_files)
        if file_overlap:
            score += min(4, len(file_overlap))
            reasons.append(f"file overlap: {', '.join(file_overlap[:4])}")

        candidate_tokens = self.tokenize_for_duplicate_scan(self.task_duplicate_text(task))
        token_overlap = sorted(source_tokens & candidate_tokens)
        if len(token_overlap) >= 5:
            score += 5
            reasons.append(f"text overlap: {', '.join(token_overlap[:8])}")
        elif len(token_overlap) >= 3:
            score += 3
            reasons.append(f"text overlap: {', '.join(token_overlap[:5])}")

        if file_overlap and len(token_overlap) >= 2:
            score += 3
            reasons.append("same files plus related scope text")

        return score, reasons

    def get_duplicate_scan(self, board: dict, payload: dict) -> dict:
        source_task, source_column = self.duplicate_source_from_payload(board, payload)
        columns = self.get_columns(board)
        include_archived = self.truthy_query(payload, "includeArchived", True)
        limit = self.query_int(payload, "limit", DUPLICATE_SCAN_DEFAULT_LIMIT, 1, DUPLICATE_SCAN_MAX_LIMIT)
        source_task_id = str(source_task.get("id") or "").strip()
        source_review_id = str(source_task.get("sourceReviewTaskId") or payload.get("sourceReviewTaskId") or "").strip()
        source_ids = {
            value
            for value in [
                source_task_id,
                source_review_id,
                *self.value_list(source_task.get("relatedTaskIds")),
                *self.value_list(source_task.get("dependsOn")),
            ]
            if value
        }
        source_tokens = self.tokenize_for_duplicate_scan(self.task_duplicate_text(source_task))
        source_files = set(self.value_list(source_task.get("files")))
        candidates: list[dict] = []
        columns_scanned = self.ordered_column_names(columns, include_archived)

        for column_name in columns_scanned:
            column = columns.get(column_name)
            if not isinstance(column, list):
                continue
            for task in column:
                if not isinstance(task, dict) or not self.is_valid_task(task):
                    continue
                score, reasons = self.duplicate_candidate_match(source_task, task, source_ids, source_tokens, source_files)
                if score <= 0:
                    continue
                candidates.append({
                    "column": column_name,
                    "score": score,
                    "matchReasons": reasons,
                    "task": self.task_summary(task, column_name, "duplicate-scan"),
                })

        candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
        limited_candidates = candidates[:limit]
        task_ids = [source_task_id] if source_task_id else []
        for candidate in limited_candidates:
            candidate_id = str(candidate.get("task", {}).get("id") or "").strip()
            if candidate_id and candidate_id not in task_ids:
                task_ids.append(candidate_id)
        return {
            "scan": {
                "sourceTaskId": source_task_id,
                "sourceColumn": source_column,
                "sourceReviewTaskId": source_review_id,
                "title": source_task.get("title", ""),
                "files": sorted(source_files),
                "includeArchived": include_archived,
                "limit": limit,
            },
            "columnsScanned": columns_scanned,
            "candidateCount": len(candidates),
            "candidates": limited_candidates,
            "taskIds": task_ids,
        }

    def get_agents(self, board: dict, payload: dict) -> dict:
        state = self.load_active_agents_state()
        return self.with_agent_log_state(state)

    def parse_spawn_log_filename(self, filename: str) -> dict:
        match = re.match(
            r"^(\d{8})-(\d{6})-(\w+)-(\w+)-(.+)\.log$", filename
        )
        if not match:
            return {}
        date_part, time_part, role, model, name = match.groups()
        timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
        return {
            "date": date_part,
            "time": time_part,
            "timestamp": timestamp,
            "role": role,
            "model": model,
            "personalName": name,
        }

    def get_agent_logs(self, board: dict, payload: dict) -> dict:
        if not SPAWN_LOG_DIR.exists():
            return {
                "logs": [],
                "agents": [],
                "pendingSpawns": [],
                "pausedRuns": [],
                "totalLogCount": 0,
                "truncated": False,
                "limit": 0,
            }
        limit = self.query_int(payload, "limit", 250, 1, 500)
        log_files: list[dict] = []
        log_entries: list[tuple[float, Path, os.stat_result]] = []
        for entry in SPAWN_LOG_DIR.iterdir():
            if not entry.is_file() or not entry.name.endswith(".log"):
                continue
            if not self.spawn_log_dir_entry_is_safe(entry):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            log_entries.append((stat.st_mtime, entry, stat))
        sorted_entries = sorted(log_entries, key=lambda item: item[0], reverse=True)
        total_log_count = len(sorted_entries)
        for _, entry, stat in sorted_entries[:limit]:
            parsed = self.parse_spawn_log_filename(entry.name)
            modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().isoformat(timespec="seconds")
            log_entry: dict = {
                "fileName": entry.name,
                "size": stat.st_size,
                "modifiedAt": modified_at,
            }
            if parsed:
                log_entry.update(parsed)
            log_files.append(log_entry)
        state = self.load_active_agents_state()
        enriched = self.with_agent_log_state(state)
        agents_summary = []
        for agent in enriched.get("agents", []):
            if not isinstance(agent, dict):
                continue
            agents_summary.append({
                "agentId": agent.get("agentId", ""),
                "personalName": agent.get("personalName", ""),
                "model": self.normalize_agent_model(agent.get("model")),
                "role": self.normalize_agent_role(agent.get("role")),
                "status": agent.get("status", ""),
                "currentTaskId": agent.get("currentTaskId", ""),
                "registeredAt": agent.get("registeredAt", ""),
                "lastHeartbeatAt": agent.get("lastHeartbeatAt", ""),
                "notes": agent.get("notes", ""),
                "latestLog": agent.get("latestLog", {}),
            })
        pending = enriched.get("pendingSpawns", [])
        paused_runs = enriched.get("pausedRuns", [])
        return {
            "logs": log_files,
            "agents": agents_summary,
            "pendingSpawns": pending if isinstance(pending, list) else [],
            "pausedRuns": paused_runs if isinstance(paused_runs, list) else [],
            "totalLogCount": total_log_count,
            "truncated": total_log_count > len(log_files),
            "limit": limit,
        }

    def get_agent_log_content(self, board: dict, payload: dict) -> dict:
        filename = str(payload.get("fileName") or "").strip()
        if not filename:
            raise JsonResponseError("fileName is required", status=400)
        if "/" in filename or "\\" in filename or ".." in filename or filename.startswith("."):
            raise JsonResponseError("Invalid fileName", status=400)
        path = SPAWN_LOG_DIR / filename
        if not self.spawn_log_path_is_safe(path):
            raise JsonResponseError("Invalid fileName", status=400)
        if not path.is_file():
            raise JsonResponseError("Log file not found", status=404)
        try:
            stat = path.stat()
            content = path.read_text(encoding="utf-8", errors="replace")
            modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().isoformat(timespec="seconds")
            parsed = self.parse_spawn_log_filename(filename)
            result: dict = {
                "fileName": filename,
                "size": stat.st_size,
                "modifiedAt": modified_at,
                "content": content,
            }
            if parsed:
                result.update(parsed)
            return result
        except OSError as error:
            raise JsonResponseError(f"Could not read log file: {error}", status=500)

    def spawn_log_path_is_safe(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            root = SPAWN_LOG_DIR.resolve()
            return resolved == root or root in resolved.parents
        except OSError:
            return False

    def spawn_log_dir_entry_is_safe(self, path: Path) -> bool:
        return path.parent == SPAWN_LOG_DIR and not path.is_symlink()

    def build_latest_spawn_log_index(self) -> dict:
        exact: dict[tuple[str, str, str], tuple[float, Path]] = {}
        role_name: dict[tuple[str, str], tuple[float, Path]] = {}
        if not SPAWN_LOG_DIR.exists():
            return {"exact": {}, "roleName": {}}
        for entry in SPAWN_LOG_DIR.iterdir():
            if not entry.is_file() or not entry.name.endswith(".log"):
                continue
            if not self.spawn_log_dir_entry_is_safe(entry):
                continue
            parsed = self.parse_spawn_log_filename(entry.name)
            if not parsed:
                continue
            role = self.normalize_agent_role(parsed.get("role"))
            model = self.normalize_agent_model(parsed.get("model"))
            personal_name = self.safe_spawn_log_name_part(parsed.get("personalName")).lower()
            if not role or not personal_name:
                continue
            try:
                modified_at = entry.stat().st_mtime
            except OSError:
                continue
            exact_key = (role, model, personal_name)
            role_name_key = (role, personal_name)
            if modified_at > exact.get(exact_key, (-1.0, entry))[0]:
                exact[exact_key] = (modified_at, entry)
            if modified_at > role_name.get(role_name_key, (-1.0, entry))[0]:
                role_name[role_name_key] = (modified_at, entry)
        return {
            "exact": {key: value[1] for key, value in exact.items()},
            "roleName": {key: value[1] for key, value in role_name.items()},
        }

    def read_spawn_log_preview(self, log_path: object, max_bytes: int = 6000, max_lines: int = 18) -> dict:
        raw_path = str(log_path or "").strip()
        if not raw_path:
            return {}
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        if not self.spawn_log_path_is_safe(path) or not path.is_file():
            return {}
        try:
            size = path.stat().st_size
            with path.open("rb") as log_file:
                if size > max_bytes:
                    log_file.seek(size - max_bytes)
                    raw = log_file.read(max_bytes)
                else:
                    raw = log_file.read()
            text = raw.decode("utf-8", errors="replace")
            if size > max_bytes:
                text = text.split("\n", 1)[-1]
            lines = [line.rstrip() for line in text.splitlines() if line.strip()]
            preview = "\n".join(lines[-max_lines:])
            updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone().isoformat(timespec="seconds")
            return {
                "path": str(path),
                "fileName": path.name,
                "updatedAt": updated_at,
                "size": size,
                "preview": preview,
            }
        except OSError:
            return {}

    def safe_spawn_log_name_part(self, value: object) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")

    def latest_spawn_log_for_agent(
        self,
        agent: dict,
        log_index: dict | None = None,
        preview_cache: dict[str, dict] | None = None,
    ) -> dict:
        role = self.normalize_agent_role(agent.get("role"))
        model = self.normalize_agent_model(agent.get("model"))
        personal_name = self.safe_spawn_log_name_part(agent.get("personalName") or agent.get("agentName")).lower()
        if not role or not personal_name or not SPAWN_LOG_DIR.exists():
            return {}
        if isinstance(log_index, dict):
            exact_index = log_index.get("exact") if isinstance(log_index.get("exact"), dict) else {}
            role_name_index = log_index.get("roleName") if isinstance(log_index.get("roleName"), dict) else {}
            latest_path = None
            if model and model != "unknown":
                latest_path = exact_index.get((role, model, personal_name))
            if latest_path is None:
                latest_path = role_name_index.get((role, personal_name))
            if latest_path is None:
                return {}
            cache_key = str(latest_path)
            if preview_cache is not None:
                if cache_key not in preview_cache:
                    preview_cache[cache_key] = self.read_spawn_log_preview(latest_path)
                return dict(preview_cache[cache_key])
            return self.read_spawn_log_preview(latest_path)
        patterns = []
        if model and model != "unknown":
            patterns.append(f"*-{role}-{model}-{personal_name}.log")
        patterns.append(f"*-{role}-*-{personal_name}.log")
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(SPAWN_LOG_DIR.glob(pattern))
        safe_candidates = [
            path
            for path in candidates
            if path.is_file() and self.spawn_log_path_is_safe(path)
        ]
        if not safe_candidates:
            return {}
        latest = max(safe_candidates, key=lambda path: path.stat().st_mtime)
        return self.read_spawn_log_preview(latest)

    def pending_spawn_matches_active_agent(self, spawn: dict, active_agents: list[dict]) -> bool:
        spawn_role = self.normalize_agent_role(spawn.get("role"))
        spawn_model = self.normalize_agent_model(spawn.get("model"))
        spawn_name = str(spawn.get("personalName") or "").strip().lower()
        if not spawn_role or not spawn_name:
            return False
        for agent in active_agents:
            if not isinstance(agent, dict):
                continue
            if self.normalize_agent_role(agent.get("role")) != spawn_role:
                continue
            if self.normalize_agent_model(agent.get("model")) != spawn_model:
                continue
            agent_name = str(agent.get("personalName") or agent.get("agentName") or "").strip().lower()
            if agent_name == spawn_name:
                return True
        return False

    def with_agent_log_state(self, state: dict) -> dict:
        now_monotonic = time.monotonic()
        with AGENT_LOG_STATE_CACHE_LOCK:
            cached = AGENT_LOG_STATE_CACHE.get("state")
            expires_at = float(AGENT_LOG_STATE_CACHE.get("expiresAt") or 0)
            if isinstance(cached, dict) and expires_at > now_monotonic:
                return cached

        with AGENT_LOG_STATE_BUILD_LOCK:
            now_monotonic = time.monotonic()
            with AGENT_LOG_STATE_CACHE_LOCK:
                cached = AGENT_LOG_STATE_CACHE.get("state")
                expires_at = float(AGENT_LOG_STATE_CACHE.get("expiresAt") or 0)
                if isinstance(cached, dict) and expires_at > now_monotonic:
                    return cached

            enriched = self.build_agent_log_state(state)
            with AGENT_LOG_STATE_CACHE_LOCK:
                AGENT_LOG_STATE_CACHE["state"] = enriched
                AGENT_LOG_STATE_CACHE["expiresAt"] = time.monotonic() + AGENT_LOG_STATE_CACHE_TTL_SECONDS
            return enriched

    def build_agent_log_state(self, state: dict) -> dict:
        enriched = dict(state)
        now = datetime.now(timezone.utc).astimezone()
        settings = load_dispatch_settings()
        latest_log_index = self.build_latest_spawn_log_index()
        preview_cache: dict[str, dict] = {}
        pending_spawn_records = [
            s for s in (settings.get("pendingSpawns", []) or [])
            if isinstance(s, dict)
        ]
        agents = []
        for agent in state.get("agents", []) or []:
            if not isinstance(agent, dict):
                continue
            enriched_agent = dict(agent)
            latest_log = self.latest_spawn_log_for_agent(enriched_agent, latest_log_index, preview_cache)
            if latest_log:
                enriched_agent["latestLog"] = latest_log
            if not str(enriched_agent.get("spawnedAt") or "").strip():
                for spawn in pending_spawn_records:
                    if self.pending_spawn_matches_active_agent(spawn, [enriched_agent]):
                        spawned_at = str(spawn.get("spawnedAt") or "").strip()
                        if spawned_at:
                            enriched_agent["spawnedAt"] = spawned_at
                        break
            agents.append(enriched_agent)
        active_agents = [
            agent
            for agent in agents
            if agent.get("status") == "active"
            and is_active_agent_record(agent, str(agent.get("role") or "").strip().lower(), now)
        ]
        pending_spawns = []
        for spawn in pending_spawn_records:
            if not isinstance(spawn, dict):
                continue
            if self.pending_spawn_matches_active_agent(spawn, active_agents):
                continue
            process_status = spawned_process_status(spawn)
            if not is_live_pending_spawn(spawn, process_status=process_status):
                continue
            process_state = str(process_status.get("state") or "unknown")
            if process_state == "running":
                pending_status = "spawned-running"
            elif process_state == "exited":
                pending_status = "spawned-exited"
            elif process_state == "pid-reused":
                pending_status = "spawned-pid-reused"
            else:
                pending_status = f"spawned-{process_state}"
            pending = {
                "role": self.normalize_agent_role(spawn.get("role")),
                "model": self.normalize_agent_model(spawn.get("model")),
                "personalName": str(spawn.get("personalName", "") or "").strip(),
                "spawnedAt": str(spawn.get("spawnedAt", "") or "").strip(),
                "processId": spawn.get("processId", ""),
                "status": pending_status,
                "processStatus": process_status,
                "latestLog": self.read_spawn_log_preview(spawn.get("logPath")),
            }
            if pending["role"] in {"worker", "review"}:
                pending_spawns.append(pending)
        paused_runs = [
            run
            for run in settings.get("pausedRuns", []) or []
            if isinstance(run, dict)
        ]
        enriched["agents"] = agents
        enriched["activeAgents"] = active_agents
        enriched["pendingSpawns"] = pending_spawns
        enriched["pausedRuns"] = paused_runs
        return enriched

    def agent_presence_summary(self) -> dict:
        state = self.load_active_agents_state()
        now = datetime.now(timezone.utc).astimezone()
        settings = load_dispatch_settings()
        agents = [
            agent for agent in state.get("agents", [])
            if isinstance(agent, dict)
        ]
        active_agents = [
            agent for agent in agents
            if agent.get("status") == "active"
            and is_active_agent_record(agent, str(agent.get("role") or "").strip().lower(), now)
        ]
        pending_spawn_records = [
            spawn for spawn in (settings.get("pendingSpawns", []) or [])
            if isinstance(spawn, dict)
        ]
        pending_spawns = []
        for spawn in pending_spawn_records:
            if self.pending_spawn_matches_active_agent(spawn, active_agents):
                continue
            if is_live_pending_spawn(spawn):
                pending_spawns.append(spawn)
        paused_runs = [
            run for run in (settings.get("pausedRuns", []) or [])
            if isinstance(run, dict)
        ]
        return {
            "agents": agents,
            "activeAgents": active_agents,
            "pendingSpawns": pending_spawns,
            "pausedRuns": paused_runs,
        }

    def load_board(self) -> dict:
        with BOARD_LOCK:
            board = json.loads(BOARD_PATH.read_text(encoding="utf-8-sig"))
            self.normalize_board_columns(board)
            return board

    def load_active_agents_state(self) -> dict:
        with ACTIVE_AGENTS_LOCK:
            if ACTIVE_AGENTS_PATH.exists():
                try:
                    state = json.loads(ACTIVE_AGENTS_PATH.read_text(encoding="utf-8-sig"))
                except json.JSONDecodeError:
                    state = {}
            else:
                state = {}

            if not isinstance(state, dict):
                state = {}
            agents = state.get("agents")
            if not isinstance(agents, list):
                agents = []

            normalized_agents = []
            for agent in agents:
                if not isinstance(agent, dict):
                    continue
                agent_id = str(agent.get("agentId", "") or "").strip()
                personal_name = str(agent.get("personalName", "") or "").strip()
                agent_name = str(agent.get("agentName", "") or "").strip()
                if not agent_name and personal_name:
                    agent_name = personal_name
                if not agent_id and not agent_name:
                    continue
                normalized = {
                    "agentId": agent_id,
                    "personalName": personal_name,
                    "model": self.normalize_agent_model(agent.get("model")),
                    "agentName": agent_name or personal_name,
                    "role": self.normalize_agent_role(agent.get("role")),
                    "startPhrase": str(agent.get("startPhrase", "") or "").strip(),
                    "registeredAt": str(agent.get("registeredAt", "") or "").strip(),
                    "lastHeartbeatAt": str(agent.get("lastHeartbeatAt", "") or "").strip(),
                    "currentTaskId": str(agent.get("currentTaskId", "") or "").strip(),
                    "status": str(agent.get("status", "active") or "active").strip().lower(),
                    "notes": str(agent.get("notes", "") or "").strip(),
                }
                if not normalized["startPhrase"]:
                    normalized["startPhrase"] = self.start_phrase_for_role(normalized["role"])
                if self.is_stale_agent(normalized):
                    normalized["status"] = "stale"
                normalized_agents.append(normalized)

            state["agents"] = normalized_agents
            state["activeAgents"] = [
                agent
                for agent in normalized_agents
                if agent.get("status") == "active"
            ]
            state["updatedAt"] = str(state.get("updatedAt", "") or "").strip()
            return state

    def persist_active_agents_state(self, state: dict) -> None:
        with ACTIVE_AGENTS_LOCK:
            temp_path = ACTIVE_AGENTS_PATH.with_suffix(".json.tmp")
            persisted_state = {
                "updatedAt": str(state.get("updatedAt", "") or "").strip(),
                "agents": state.get("agents") if isinstance(state.get("agents"), list) else [],
            }
            temp_path.write_text(json.dumps(persisted_state, indent=2) + "\n", encoding="utf-8")
            os.replace(temp_path, ACTIVE_AGENTS_PATH)
        clear_agent_log_state_cache()

    def clear_active_agents_for_task(self, task_id: str, role: str, timestamp: str, note: str) -> None:
        state = self.load_active_agents_state()
        agents = state.get("agents")
        if not isinstance(agents, list):
            return
        changed = False
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            if self.normalize_agent_role(agent.get("role")) != role:
                continue
            if str(agent.get("currentTaskId", "") or "").strip() != task_id:
                continue
            agent["currentTaskId"] = ""
            agent["status"] = "stale"
            existing_notes = str(agent.get("notes", "") or "").strip()
            agent["notes"] = f"{existing_notes}\n{note}".strip() if existing_notes else note
            agent["lastHeartbeatAt"] = timestamp
            changed = True
        if changed:
            state["updatedAt"] = timestamp
            self.persist_active_agents_state(state)

    def parse_iso_timestamp(self, value: str) -> datetime | None:
        value = str(value or "").strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def is_stale_agent(self, agent: dict) -> bool:
        if str(agent.get("status", "")).lower() != "active":
            return False
        last_seen = self.parse_iso_timestamp(str(agent.get("lastHeartbeatAt") or agent.get("registeredAt") or ""))
        if not last_seen:
            return False
        age_seconds = (datetime.now(timezone.utc).astimezone() - last_seen).total_seconds()
        return age_seconds > ACTIVE_AGENT_STALE_SECONDS

    def normalize_agent_role(self, value: object) -> str:
        role = str(value or "").strip().lower().replace(" ", "-")
        if role in {"review-agent", "reviewer-agent", "reviewer"}:
            return "review"
        if role in {"worker-agent"}:
            return "worker"
        if role in {"planning-agent", "planner"}:
            return "planning"
        return role or "unknown"

    def normalize_agent_model(self, value: object) -> str:
        model = str(value or "").strip().lower()
        if model in {"claude", "cc", "claude-code"}:
            return "claude"
        if model in {"codex", "openai-codex"}:
            return "codex"
        if model in {"qwen", "qwen-code"}:
            return "qwen"
        return model or "unknown"

    def start_phrase_for_role(self, role: str) -> str:
        return AGENT_ROLE_START_PHRASES.get(role, "")

    def spawn_command_for_tool(self, tool: str) -> str:
        settings = load_dispatch_settings()
        commands = settings.get("commands")
        if not isinstance(commands, dict):
            commands = {}
        if tool == "claude":
            fallback = CLAUDE_COMMAND
        elif tool == "qwen":
            fallback = QWEN_COMMAND
        else:
            fallback = CODEX_COMMAND
        return normalize_spawn_command(commands.get(tool), fallback)

    def spawn_command_args(self, tool: str, command_override: object = None) -> list[str]:
        if command_override is None:
            command_text = self.spawn_command_for_tool(tool)
        else:
            command_text = normalize_spawn_command(command_override, "")
        try:
            parts = shlex.split(command_text, posix=os.name != "nt")
        except ValueError as error:
            raise ValueError(f"Invalid {tool} command: {error}") from error
        if not parts:
            raise ValueError(f"Missing {tool} command")
        resolved = shutil.which(parts[0], path=common_executable_search_path()) or parts[0]
        return [resolved, *parts[1:]]

    def load_agent_schema(self) -> dict:
        try:
            return json.loads(AGENT_SCHEMA_PATH.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"modelBackground": {}, "roleBorder": {}, "personalNamePool": []}

    def get_agent_schema(self, board: dict, payload: dict) -> dict:
        return self.load_agent_schema()

    def get_dispatch_settings(self, board: dict, payload: dict) -> dict:
        return load_dispatch_settings()

    def clone_default_workflow_map(self) -> dict:
        return copy.deepcopy(default_workflow_map())

    def normalize_workflow_rule(self, rule: object, index: int = 0) -> dict | None:
        if isinstance(rule, str):
            text = compact_workflow_text(rule, limit=420)
            if not text:
                return None
            return {
                "id": workflow_slug(text[:40], f"rule-{index + 1}"),
                "title": "Rule",
                "text": text,
            }
        if not isinstance(rule, dict):
            return None
        text = compact_workflow_text(rule.get("text") or rule.get("summary") or rule.get("rule"), limit=420)
        if not text:
            return None
        title = compact_workflow_text(rule.get("title") or "Rule", limit=80)
        return {
            "id": workflow_slug(rule.get("id") or title or text[:40], f"rule-{index + 1}"),
            "title": title or "Rule",
            "text": text,
        }

    def normalize_workflow_string_list(self, value: object, limit: int = 140) -> list[str]:
        raw_values = value if isinstance(value, list) else [value]
        result: list[str] = []
        for raw_value in raw_values:
            text = compact_workflow_text(raw_value, limit=limit)
            if text and text not in result:
                result.append(text)
        return result

    def normalize_workflow_output_type(self, value: object, fallback: str = "handoff") -> str:
        text = workflow_slug(value or fallback, fallback)
        aliases = {
            "board": "task-board-ticket",
            "board-column": "task-board-ticket",
            "task": "task-board-ticket",
            "task-board": "task-board-ticket",
            "task-board-column": "task-board-ticket",
            "task-board-ticket": "task-board-ticket",
            "ticket": "task-board-ticket",
            "tickets": "task-board-ticket",
            "todo-ticket": "task-board-ticket",
            "review-ticket": "task-board-ticket",
            "handoff-file": "handoff-markdown",
            "handoff-files": "handoff-markdown",
            "handoff-markdown-file": "handoff-markdown",
            "markdown": "handoff-markdown",
            "markdown-file": "handoff-markdown",
            "human": "human-readable-output",
            "human-output": "human-readable-output",
            "human-readable": "human-readable-output",
            "human-readable-output": "human-readable-output",
            "owner-output": "human-readable-output",
        }
        return aliases.get(text, text)

    def normalize_workflow_render_as(self, value: object, output_type: str) -> str:
        text = workflow_slug(value, "")
        aliases = {
            "board": "board-column",
            "board-column": "board-column",
            "column": "board-column",
            "task-board": "board-column",
            "task-board-column": "board-column",
            "handoff": "handoff-files",
            "handoff-file": "handoff-files",
            "handoff-files": "handoff-files",
            "markdown": "handoff-files",
            "markdown-files": "handoff-files",
            "file": "handoff-files",
            "files": "handoff-files",
        }
        if text in aliases:
            return aliases[text]
        if output_type == "handoff-markdown":
            return "handoff-files"
        if output_type in {"task-board-ticket", "human-readable-output"}:
            return "board-column"
        return text or "detail"

    def default_workflow_handoff_patterns(self, from_id: str = "", to_id: str = "") -> list[str]:
        source = workflow_slug(from_id, "handoff-source")
        target = workflow_slug(to_id, "handoff-target")
        return [
            f"workflow/handoffs/{source}-to-{target}.md",
            f"workflow/handoffs/{source}-to-{target}-*.md",
        ]

    def normalize_workflow_output(self, output: object, index: int = 0, context: dict | None = None) -> dict | None:
        context = context or {}
        if isinstance(output, str):
            label = compact_workflow_text(output, limit=90)
            if not label:
                return None
            output = {"label": label}
        if not isinstance(output, dict):
            return None

        label = compact_workflow_text(output.get("label") or output.get("title") or output.get("name") or "Output", limit=90)
        if not label:
            return None
        inferred_type = "handoff-markdown" if re.search(r"\b(?:markdown|file|handoff)\b", label, re.IGNORECASE) else "handoff"
        output_type = self.normalize_workflow_output_type(
            output.get("type") or output.get("outputType") or output.get("kind") or output.get("channel"),
            inferred_type,
        )
        render_as = self.normalize_workflow_render_as(output.get("renderAs") or output.get("render") or output.get("view"), output_type)
        output_id = workflow_slug(
            output.get("id") or f"{context.get('from') or context.get('nodeId') or 'output'}-{context.get('to') or label}-{index + 1}",
            f"output-{index + 1}",
        )

        normalized = {
            "id": output_id,
            "type": output_type,
            "renderAs": render_as,
            "label": label,
            "description": compact_workflow_text(output.get("description") or output.get("summary") or "", limit=220),
            "color": compact_workflow_text(output.get("color") or "", limit=40),
        }

        source_keys = self.normalize_workflow_string_list(
            output.get("sourceKeys") or output.get("columnKeys") or output.get("columns") or output.get("sourceColumnKeys"),
            limit=60,
        )
        column_key = workflow_slug(output.get("columnKey") or output.get("column") or output.get("status"), "")
        visual_column_key = workflow_slug(output.get("visualColumnKey") or output.get("visualKey") or output.get("laneKey") or column_key, "")
        if render_as == "board-column":
            if column_key and column_key not in source_keys:
                source_keys.append(column_key)
            if not visual_column_key:
                visual_column_key = column_key or workflow_slug(label, f"output-{index + 1}")
            if not column_key:
                column_key = source_keys[-1] if source_keys else visual_column_key
            normalized.update({
                "visualColumnKey": visual_column_key,
                "columnKey": column_key,
                "sourceKeys": [workflow_slug(key, "") for key in source_keys if workflow_slug(key, "")],
                "agentRole": workflow_slug(output.get("agentRole") or output.get("role") or "", ""),
                "agentLabel": compact_workflow_text(output.get("agentLabel") or "", limit=60),
            })

        file_patterns = self.normalize_workflow_string_list(
            output.get("filePatterns")
            or output.get("patterns")
            or output.get("paths")
            or output.get("files")
            or output.get("path")
            or output.get("file"),
            limit=220,
        )
        if render_as == "handoff-files":
            if not file_patterns:
                file_patterns = self.default_workflow_handoff_patterns(str(context.get("from") or ""), str(context.get("to") or ""))
            normalized["filePatterns"] = file_patterns

        return normalized

    def normalize_workflow_node(self, node: object, index: int = 0) -> dict | None:
        if not isinstance(node, dict):
            return None
        label = compact_workflow_text(node.get("label") or node.get("title") or node.get("id"), limit=80)
        if not label:
            return None
        node_id = workflow_slug(node.get("id") or label)
        kind = compact_workflow_text(node.get("kind") or "Agent", limit=40) or "Agent"
        color = compact_workflow_text(node.get("color") or workflow_color_for_kind(kind, index), limit=40)
        rules = []
        raw_rules = node.get("rules")
        if isinstance(raw_rules, list):
            for rule_index, raw_rule in enumerate(raw_rules):
                rule = self.normalize_workflow_rule(raw_rule, rule_index)
                if rule:
                    rules.append(rule)
        outputs = []
        raw_outputs = node.get("outputs")
        if isinstance(raw_outputs, list):
            for output_index, raw_output in enumerate(raw_outputs):
                output = self.normalize_workflow_output(raw_output, output_index, {"nodeId": node_id})
                if output:
                    outputs.append(output)
        return {
            "id": node_id,
            "detailKey": compact_workflow_text(node.get("detailKey") or node_id, limit=80),
            "kind": kind,
            "label": label,
            "color": color or workflow_color_for_kind(kind, index),
            "meta": compact_workflow_text(node.get("meta") or node.get("summary") or f"Custom {kind.lower()} in the workflow.", limit=220),
            "acceptsHumanInput": bool(node.get("acceptsHumanInput")),
            "locked": bool(node.get("locked")),
            "rules": rules,
            "outputs": outputs,
        }

    def unique_workflow_node_id(self, workflow_map: dict, desired: str) -> str:
        existing = {
            str(node.get("id") or "").strip()
            for node in workflow_map.get("nodes", [])
            if isinstance(node, dict)
        }
        base = workflow_slug(desired)
        if base not in existing:
            return base
        index = 2
        while f"{base}-{index}" in existing:
            index += 1
        return f"{base}-{index}"

    def normalize_workflow_map(self, data: object) -> dict:
        defaults = self.clone_default_workflow_map()
        source = data if isinstance(data, dict) else {}
        normalized = {
            "version": int(source.get("version") or defaults["version"]) if isinstance(source, dict) else 1,
            "updatedAt": compact_workflow_text(source.get("updatedAt") if isinstance(source, dict) else "", limit=80),
            "nodes": [],
            "rows": [],
            "edges": [],
            "globalRules": [],
        }

        node_by_id: dict[str, dict] = {}
        raw_nodes = source.get("nodes") if isinstance(source.get("nodes"), list) else defaults["nodes"]
        for index, raw_node in enumerate(raw_nodes):
            node = self.normalize_workflow_node(raw_node, index)
            if not node:
                continue
            if node["id"] in node_by_id:
                node["id"] = self.unique_workflow_node_id({"nodes": normalized["nodes"]}, node["id"])
                node["detailKey"] = node["id"]
            node_by_id[node["id"]] = node
            normalized["nodes"].append(node)

        default_node_by_id = {
            node["id"]: self.normalize_workflow_node(node, index)
            for index, node in enumerate(defaults["nodes"])
        }
        for default_id in ("planner", "worker", "reviewer"):
            if default_id not in node_by_id and default_node_by_id.get(default_id):
                normalized["nodes"].insert(len([n for n in normalized["nodes"] if n.get("locked")]), default_node_by_id[default_id])
                node_by_id[default_id] = default_node_by_id[default_id]

        for node in normalized["nodes"]:
            node_id = str(node.get("id") or "").strip()
            default_node = default_node_by_id.get(node_id)
            if default_node and not node.get("outputs") and default_node.get("outputs"):
                node["outputs"] = copy.deepcopy(default_node["outputs"])

        raw_rows = source.get("rows") if isinstance(source.get("rows"), list) else defaults["rows"]
        seen_in_rows: set[str] = set()
        for raw_row in raw_rows:
            raw_ids = raw_row if isinstance(raw_row, list) else [raw_row]
            row = []
            for raw_id in raw_ids:
                node_id = workflow_slug(raw_id)
                if node_id in node_by_id and node_id not in seen_in_rows:
                    row.append(node_id)
                    seen_in_rows.add(node_id)
            if row:
                normalized["rows"].append(row)
        for node in normalized["nodes"]:
            node_id = node["id"]
            if node_id not in seen_in_rows:
                normalized["rows"].append([node_id])

        raw_edges = source.get("edges") if isinstance(source.get("edges"), list) else defaults["edges"]
        seen_edges: set[tuple[str, str]] = set()
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, dict):
                continue
            from_id = workflow_slug(raw_edge.get("from"))
            to_id = workflow_slug(raw_edge.get("to"))
            if from_id not in node_by_id or to_id not in node_by_id or from_id == to_id:
                continue
            edge_key = (from_id, to_id)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            outputs = []
            raw_outputs = raw_edge.get("outputs") if isinstance(raw_edge.get("outputs"), list) else []
            for output_index, raw_output in enumerate(raw_outputs):
                output = self.normalize_workflow_output(raw_output, output_index, {"from": from_id, "to": to_id})
                if output:
                    outputs.append(output)
            if not outputs:
                for default_edge in defaults["edges"]:
                    if default_edge.get("from") == from_id and default_edge.get("to") == to_id:
                        default_outputs = default_edge.get("outputs") if isinstance(default_edge.get("outputs"), list) else []
                        for output_index, raw_output in enumerate(default_outputs):
                            output = self.normalize_workflow_output(raw_output, output_index, {"from": from_id, "to": to_id})
                            if output:
                                outputs.append(output)
                        break
            if not outputs and re.search(r"\b(?:handoff\s+(?:markdown\s+)?files?|handoff\s+brief|research\s+brief)\b", str(raw_edge.get("label") or ""), re.IGNORECASE):
                output = self.normalize_workflow_output(
                    {
                        "type": "handoff-markdown",
                        "renderAs": "handoff-files",
                        "label": compact_workflow_text(raw_edge.get("label") or "Handoff Markdown", limit=90),
                    },
                    0,
                    {"from": from_id, "to": to_id},
                )
                if output:
                    outputs.append(output)
            normalized["edges"].append({
                "from": from_id,
                "to": to_id,
                "label": compact_workflow_text(raw_edge.get("label") or "handoff", limit=90),
                "rules": [
                    rule for idx, rule in enumerate(
                        self.normalize_workflow_rule(raw_rule, idx)
                        for idx, raw_rule in enumerate(raw_edge.get("rules") if isinstance(raw_edge.get("rules"), list) else [])
                    ) if rule
                ],
                "outputs": outputs,
            })
        if not normalized["edges"]:
            normalized["edges"] = copy.deepcopy(defaults["edges"])

        raw_global_rules = source.get("globalRules") if isinstance(source.get("globalRules"), list) else defaults["globalRules"]
        for index, raw_rule in enumerate(raw_global_rules):
            rule = self.normalize_workflow_rule(raw_rule, index)
            if rule:
                normalized["globalRules"].append(rule)

        return normalized

    def load_workflow_map(self) -> dict:
        try:
            data = json.loads(WORKFLOW_MAP_PATH.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = self.clone_default_workflow_map()
        return self.normalize_workflow_map(data)

    def persist_workflow_map(self, workflow_map: dict) -> None:
        normalized = self.normalize_workflow_map(workflow_map)
        normalized["updatedAt"] = now_iso()
        try:
            with WORKFLOW_MAP_LOCK:
                temp_path = WORKFLOW_MAP_PATH.with_suffix(".json.tmp")
                temp_path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
                os.replace(temp_path, WORKFLOW_MAP_PATH)
        except Exception as error:
            raise RuntimeError(f"Unable to persist workflow map: {error}") from error

    def get_workflow_map(self, board: dict, payload: dict) -> dict:
        del board, payload
        with WORKFLOW_MAP_LOCK:
            return self.load_workflow_map()

    def workflow_handoff_output_refs(self, workflow_map: dict) -> list[dict]:
        lookup = self.workflow_node_by_id(workflow_map)
        refs: list[dict] = []
        for edge in workflow_map.get("edges", []):
            if not isinstance(edge, dict):
                continue
            from_id = str(edge.get("from") or "").strip()
            to_id = str(edge.get("to") or "").strip()
            source_label = str(lookup.get(from_id, {}).get("label") or from_id).strip()
            target_label = str(lookup.get(to_id, {}).get("label") or to_id).strip()
            outputs = edge.get("outputs") if isinstance(edge.get("outputs"), list) else []
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                output_type = self.normalize_workflow_output_type(output.get("type") or output.get("kind"), "")
                render_as = self.normalize_workflow_render_as(output.get("renderAs") or output.get("render"), output_type)
                if output_type != "handoff-markdown" and render_as != "handoff-files":
                    continue
                refs.append({
                    "id": str(output.get("id") or f"{from_id}-{to_id}-handoff").strip(),
                    "type": output_type or "handoff-markdown",
                    "renderAs": "handoff-files",
                    "label": str(output.get("label") or edge.get("label") or "Handoff Markdown").strip(),
                    "description": str(output.get("description") or "").strip(),
                    "from": from_id,
                    "to": to_id,
                    "fromLabel": source_label,
                    "toLabel": target_label,
                    "filePatterns": output.get("filePatterns") if isinstance(output.get("filePatterns"), list) else [],
                })
        for node in workflow_map.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "").strip()
            outputs = node.get("outputs") if isinstance(node.get("outputs"), list) else []
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                output_type = self.normalize_workflow_output_type(output.get("type") or output.get("kind"), "")
                render_as = self.normalize_workflow_render_as(output.get("renderAs") or output.get("render"), output_type)
                if output_type != "handoff-markdown" and render_as != "handoff-files":
                    continue
                refs.append({
                    "id": str(output.get("id") or f"{node_id}-handoff").strip(),
                    "type": output_type or "handoff-markdown",
                    "renderAs": "handoff-files",
                    "label": str(output.get("label") or "Handoff Markdown").strip(),
                    "description": str(output.get("description") or "").strip(),
                    "from": node_id,
                    "to": "",
                    "fromLabel": str(node.get("label") or node_id).strip(),
                    "toLabel": "",
                    "filePatterns": output.get("filePatterns") if isinstance(output.get("filePatterns"), list) else [],
                })
        return refs

    def safe_workflow_handoff_matches(self, pattern: object, limit: int = 25) -> list[Path]:
        pattern_text = str(pattern or "").strip().replace("\\", "/")
        if not pattern_text or pattern_text.startswith("/") or re.match(r"^[A-Za-z]:", pattern_text):
            return []
        if ".." in Path(pattern_text).parts:
            return []
        try:
            matches = sorted(PROJECT_ROOT.glob(pattern_text), key=lambda item: str(item).lower())
        except (OSError, ValueError):
            return []
        safe_matches: list[Path] = []
        for path in matches:
            if len(safe_matches) >= limit:
                break
            try:
                resolved = path.resolve()
                resolved.relative_to(PROJECT_ROOT)
            except (OSError, ValueError):
                continue
            if not resolved.is_file() or resolved.suffix.lower() not in {".md", ".markdown"}:
                continue
            safe_matches.append(resolved)
        return safe_matches

    def workflow_handoff_file_info(self, path: Path) -> dict | None:
        try:
            stat = path.stat()
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            relative = path.relative_to(PROJECT_ROOT).as_posix()
        except (OSError, UnicodeError, ValueError):
            return None
        preview = re.sub(r"\s+", " ", text).strip()
        if len(preview) > 700:
            preview = preview[:700].rstrip() + "..."
        modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().isoformat(timespec="seconds")
        return {
            "path": relative,
            "name": path.name,
            "size": stat.st_size,
            "modifiedAt": modified_at,
            "preview": preview,
        }

    def get_workflow_handoff_files(self, board: dict, payload: dict) -> dict:
        del board, payload
        with WORKFLOW_MAP_LOCK:
            workflow_map = self.load_workflow_map()
        outputs = []
        for output in self.workflow_handoff_output_refs(workflow_map):
            files_by_path: dict[str, dict] = {}
            patterns = output.get("filePatterns") if isinstance(output.get("filePatterns"), list) else []
            for pattern in patterns:
                for path in self.safe_workflow_handoff_matches(pattern):
                    info = self.workflow_handoff_file_info(path)
                    if info:
                        files_by_path[info["path"]] = info
            files = sorted(files_by_path.values(), key=lambda item: (item.get("modifiedAt") or "", item.get("path") or ""), reverse=True)
            outputs.append({
                **output,
                "files": files,
            })
        return {
            "updatedAt": now_iso(),
            "projectRoot": str(PROJECT_ROOT),
            "outputs": outputs,
        }

    def workflow_node_by_id(self, workflow_map: dict) -> dict[str, dict]:
        return {
            str(node.get("id") or "").strip(): node
            for node in workflow_map.get("nodes", [])
            if isinstance(node, dict) and str(node.get("id") or "").strip()
        }

    def workflow_find_node(self, workflow_map: dict, query: object) -> dict | None:
        text = compact_workflow_text(query, limit=100)
        if not text:
            return None
        text = re.sub(r"^(?:(?:the|a|an|current|existing)\s+)+", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s+(?:agent|step|node)$", "", text, flags=re.IGNORECASE).strip()
        normalized_query = workflow_slug(text)
        aliases = {
            "planner-agent": "planner",
            "planning": "planner",
            "planning-agent": "planner",
            "researcher": "research",
            "researcher-agent": "research",
            "resort": "research",
            "resort-agent": "research",
            "review": "reviewer",
            "review-agent": "reviewer",
            "reviewer-agent": "reviewer",
            "worker-agent": "worker",
        }
        normalized_query = aliases.get(normalized_query, normalized_query)
        for node in workflow_map.get("nodes", []):
            if not isinstance(node, dict):
                continue
            candidates = {
                workflow_slug(node.get("id")),
                workflow_slug(node.get("detailKey")),
                workflow_slug(node.get("label")),
            }
            if normalized_query in candidates:
                return node
        for node in workflow_map.get("nodes", []):
            if not isinstance(node, dict):
                continue
            label = workflow_slug(node.get("label"))
            if normalized_query and (normalized_query in label or label in normalized_query):
                return node
        return None

    def workflow_row_index(self, workflow_map: dict, node_id: str) -> int:
        for index, row in enumerate(workflow_map.get("rows", [])):
            if isinstance(row, list) and node_id in row:
                return index
        return -1

    def workflow_add_edge(self, workflow_map: dict, from_id: str, to_id: str, label: str = "handoff") -> bool:
        if not from_id or not to_id or from_id == to_id:
            return False
        next_label = compact_workflow_text(label or "handoff", limit=90) or "handoff"
        for edge in workflow_map.get("edges", []):
            if isinstance(edge, dict) and edge.get("from") == from_id and edge.get("to") == to_id:
                previous_label = str(edge.get("label") or "").strip()
                edge["label"] = next_label
                return previous_label != next_label
        workflow_map.setdefault("edges", []).append({
            "from": from_id,
            "to": to_id,
            "label": next_label,
            "rules": [],
            "outputs": [],
        })
        return True

    def workflow_find_edge(self, workflow_map: dict, from_id: str, to_id: str) -> dict | None:
        for edge in workflow_map.get("edges", []):
            if isinstance(edge, dict) and edge.get("from") == from_id and edge.get("to") == to_id:
                return edge
        return None

    def workflow_ensure_handoff_file_output(self, workflow_map: dict, from_id: str, to_id: str, label: str = "Handoff Markdown") -> bool:
        edge = self.workflow_find_edge(workflow_map, from_id, to_id)
        if not edge:
            return False
        outputs = edge.setdefault("outputs", [])
        if not isinstance(outputs, list):
            outputs = []
            edge["outputs"] = outputs
        for output in outputs:
            if not isinstance(output, dict):
                continue
            output_type = self.normalize_workflow_output_type(output.get("type") or output.get("kind"), "")
            render_as = self.normalize_workflow_render_as(output.get("renderAs") or output.get("render"), output_type)
            if output_type == "handoff-markdown" or render_as == "handoff-files":
                return False
        output = self.normalize_workflow_output(
            {
                "type": "handoff-markdown",
                "renderAs": "handoff-files",
                "label": label or "Handoff Markdown",
            },
            len(outputs),
            {"from": from_id, "to": to_id},
        )
        if not output:
            return False
        outputs.append(output)
        return True

    def workflow_remove_edges(self, workflow_map: dict, predicate) -> list[dict]:
        removed = []
        remaining = []
        for edge in workflow_map.get("edges", []):
            if isinstance(edge, dict) and predicate(edge):
                removed.append(edge)
            else:
                remaining.append(edge)
        workflow_map["edges"] = remaining
        return removed

    def workflow_insert_row(self, workflow_map: dict, node_id: str, index: int) -> None:
        rows = workflow_map.setdefault("rows", [])
        clamped = max(0, min(index, len(rows)))
        rows.insert(clamped, [node_id])

    def workflow_add_node_after(self, workflow_map: dict, node: dict, target_id: str, label: str) -> None:
        target_row = self.workflow_row_index(workflow_map, target_id)
        self.workflow_insert_row(workflow_map, node["id"], target_row + 1 if target_row >= 0 else len(workflow_map.get("rows", [])))
        outgoing = self.workflow_remove_edges(workflow_map, lambda edge: edge.get("from") == target_id)
        self.workflow_add_edge(workflow_map, target_id, node["id"], label or "handoff")
        for edge in outgoing:
            self.workflow_add_edge(workflow_map, node["id"], str(edge.get("to") or ""), str(edge.get("label") or "handoff"))

    def workflow_add_node_before(self, workflow_map: dict, node: dict, target_id: str, label: str) -> None:
        target_row = self.workflow_row_index(workflow_map, target_id)
        self.workflow_insert_row(workflow_map, node["id"], target_row if target_row >= 0 else 0)
        incoming = self.workflow_remove_edges(workflow_map, lambda edge: edge.get("to") == target_id)
        for edge in incoming:
            self.workflow_add_edge(workflow_map, str(edge.get("from") or ""), node["id"], str(edge.get("label") or "handoff"))
        self.workflow_add_edge(workflow_map, node["id"], target_id, label or "handoff")

    def clean_workflow_label(self, value: str, kind: str) -> str:
        label = compact_workflow_text(value.strip(" \"'`"), limit=80)
        label = re.sub(r"^(?:new|custom)\s+", "", label, flags=re.IGNORECASE).strip()
        label = re.sub(r"\s+row$", "", label, flags=re.IGNORECASE).strip()
        label = re.sub(r"\s+(?:agent|step)$", "", label, flags=re.IGNORECASE).strip()
        if not label:
            label = kind
        return label[:1].upper() + label[1:]

    def workflow_extract_handoff_label(self, message: str) -> str:
        patterns = [
            r"\bwith\s+(?:handoff\s+)?label\s+(.+?)(?=[.;]|$)",
            r"\blabeled\s+(?:for\s+)?(.+?)(?=[.;]|$)",
            r"\bcalled\s+(.+?)(?=[.;]|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return compact_workflow_text(match.group(1).strip(" .,:;\"'`"), limit=90)
        return "handoff"

    def workflow_infer_handoff_label(self, message: str) -> str:
        explicit_label = self.workflow_extract_handoff_label(message)
        if explicit_label != "handoff":
            return explicit_label
        if re.search(r"\bresearch\s+brief\b", message, re.IGNORECASE):
            return "research brief"
        if re.search(r"\bhandoff\s+markdown\s+files?\b", message, re.IGNORECASE):
            return "handoff markdown file"
        if re.search(r"\bhandoff\s+files?\b", message, re.IGNORECASE):
            return "handoff files"
        if re.search(r"\bresearch\s+handoff\b", message, re.IGNORECASE):
            return "research handoff"
        return "handoff"

    def workflow_add_edge_rule(self, workflow_map: dict, from_id: str, to_id: str, rule_text: str, title: str = "Handoff rule") -> bool:
        text = compact_workflow_text(rule_text, limit=420)
        if not text:
            return False
        edge = self.workflow_find_edge(workflow_map, from_id, to_id)
        if not edge:
            return False
        rules = edge.setdefault("rules", [])
        if any(isinstance(item, dict) and item.get("text") == text for item in rules):
            return False
        rules.append({
            "id": workflow_slug(text[:48], "handoff-rule"),
            "title": title,
            "text": text,
        })
        return True

    def workflow_maybe_add_handoff_file_rule(self, workflow_map: dict, from_id: str, to_id: str, message: str) -> bool:
        if not re.search(r"\b(?:handoff\s+(?:markdown\s+)?files?|handoff\s+brief|research\s+brief)\b", message, re.IGNORECASE):
            return False
        if to_id == "planner":
            if re.search(r"\bmarkdown\b", message, re.IGNORECASE):
                rule_text = "Planner reads the handoff Markdown file before creating small claimable todo tasks."
            else:
                rule_text = "Planner reads the handoff file and turns useful findings into small claimable todo tasks."
        else:
            rule_text = "The receiving agent reads the handoff file before acting on downstream work."
        rule_changed = self.workflow_add_edge_rule(workflow_map, from_id, to_id, rule_text)
        output_changed = self.workflow_ensure_handoff_file_output(workflow_map, from_id, to_id, "Handoff Markdown")
        return rule_changed or output_changed

    def workflow_extract_rule_text(self, message: str) -> str:
        if ":" in message:
            return compact_workflow_text(message.split(":", 1)[1], limit=420)
        match = re.search(r"\b(?:that|to|must|should)\s+(.+)$", message, re.IGNORECASE)
        if match:
            return compact_workflow_text(match.group(1), limit=420)
        return ""

    def workflow_agent_help(self) -> str:
        return (
            "Try: add research agent after Planner; add audit step before Reviewer; "
            "add handoff from Research to Worker with label research brief; "
            "update rules for Reviewer: require BrowserOS visual testing; "
            "add global rule: Workers include inspection targets; reset workflow map."
        )

    def workflow_apply_add_handoff(self, workflow_map: dict, message: str) -> tuple[bool, str] | None:
        match = re.search(r"\bhandoff\b.*?\bfrom\s+(.+?)\s+\bto\s+(.+?)(?=\s+\bwith\b|\s+\blabeled\b|\s+\bcalled\b|[.;]|$)", message, re.IGNORECASE)
        if not match:
            return None
        source = self.workflow_find_node(workflow_map, match.group(1))
        target = self.workflow_find_node(workflow_map, match.group(2))
        if not source or not target:
            return False, "I could not find both ends of that handoff. Use existing node names like Planner, Worker, Reviewer, or a custom node name."
        label = self.workflow_infer_handoff_label(message)
        changed = self.workflow_add_edge(workflow_map, source["id"], target["id"], label)
        if re.search(r"\b(?:handoff\s+(?:markdown\s+)?files?|handoff\s+brief|research\s+brief)\b", message, re.IGNORECASE):
            changed = self.workflow_maybe_add_handoff_file_rule(workflow_map, source["id"], target["id"], message) or changed
        verb = "Added" if changed else "Updated"
        return changed, f"{verb} handoff from {source['label']} to {target['label']} labeled \"{label}\"."

    def workflow_apply_handoff_rule(self, workflow_map: dict, message: str) -> tuple[bool, str] | None:
        if not re.search(r"\bhandoff\b.*\brules?\b", message, re.IGNORECASE):
            return None
        match = re.search(r"\bfrom\s+(.+?)\s+\bto\s+(.+?)(?=[:,;]|\s+\bwith\b|\s+\bthat\b|\s+\bmust\b|\s+\bshould\b|$)", message, re.IGNORECASE)
        if not match:
            return False, "Name the handoff endpoints, for example: add handoff rule from Worker to Reviewer: include inspection targets."
        source = self.workflow_find_node(workflow_map, match.group(1))
        target = self.workflow_find_node(workflow_map, match.group(2))
        if not source or not target:
            return False, "I could not find both ends of that handoff rule."
        rule_text = self.workflow_extract_rule_text(message)
        if not rule_text:
            return False, "Tell me the handoff rule after a colon."
        edge = self.workflow_find_edge(workflow_map, source["id"], target["id"])
        if not edge:
            self.workflow_add_edge(workflow_map, source["id"], target["id"], "handoff")
            edge = self.workflow_find_edge(workflow_map, source["id"], target["id"])
        if not edge:
            return False, "I could not update that handoff rule."
        rules = edge.setdefault("rules", [])
        if not any(isinstance(item, dict) and item.get("text") == rule_text for item in rules):
            rules.append({
                "id": workflow_slug(rule_text[:48], "handoff-rule"),
                "title": "Handoff rule",
                "text": rule_text,
            })
        return True, f"Updated handoff rules from {source['label']} to {target['label']}."

    def workflow_apply_rule(self, workflow_map: dict, message: str) -> tuple[bool, str] | None:
        if not re.search(r"\brules?\b", message, re.IGNORECASE):
            return None
        rule_text = self.workflow_extract_rule_text(message)
        if not rule_text:
            return False, "Tell me the rule after a colon, for example: update rules for Reviewer: require BrowserOS visual testing."

        target_match = re.search(r"\brules?\s+(?:for|to|on)\s+(.+?)(?=[:,;]|\s+\bthat\b|\s+\bto\b|\s+\bmust\b|\s+\bshould\b|$)", message, re.IGNORECASE)
        node = self.workflow_find_node(workflow_map, target_match.group(1)) if target_match else None
        rule = {
            "id": workflow_slug(rule_text[:48], "workflow-rule"),
            "title": "Workflow rule",
            "text": rule_text,
        }
        if node:
            existing = node.setdefault("rules", [])
            if not any(isinstance(item, dict) and item.get("text") == rule_text for item in existing):
                existing.append(rule)
            return True, f"Updated rules for {node['label']}."

        existing_global = workflow_map.setdefault("globalRules", [])
        if not any(isinstance(item, dict) and item.get("text") == rule_text for item in existing_global):
            existing_global.append(rule)
        return True, "Added a global workflow rule."

    def workflow_apply_remove_node(self, workflow_map: dict, message: str) -> tuple[bool, str] | None:
        match = re.search(r"\b(?:remove|delete)\s+(?:the\s+)?(?:agent|step|node)?\s*(.+)$", message, re.IGNORECASE)
        if not match:
            return None
        node = self.workflow_find_node(workflow_map, match.group(1).strip(" .,:;"))
        if not node:
            return False, "I could not find that workflow node."
        if node.get("locked"):
            return False, f"{node['label']} is a locked core node, so I left it in place."
        node_id = node["id"]
        workflow_map["nodes"] = [item for item in workflow_map.get("nodes", []) if not (isinstance(item, dict) and item.get("id") == node_id)]
        workflow_map["rows"] = [
            [item for item in row if item != node_id]
            for row in workflow_map.get("rows", [])
            if isinstance(row, list)
        ]
        workflow_map["rows"] = [row for row in workflow_map["rows"] if row]
        self.workflow_remove_edges(workflow_map, lambda edge: edge.get("from") == node_id or edge.get("to") == node_id)
        return True, f"Removed {node['label']} and its handoffs."

    def workflow_apply_add_node(self, workflow_map: dict, message: str) -> tuple[bool, str] | None:
        if not re.search(r"\badd\b", message, re.IGNORECASE):
            return None
        if re.search(r"\brules?\b", message, re.IGNORECASE):
            return None
        if re.search(r"\badd\s+(?:a|an|the\s+)?handoff\b", message, re.IGNORECASE):
            return None

        add_match = re.search(r"\badd\s+(?:(?:a|an|the)\s+)?(.+)$", message, re.IGNORECASE)
        if not add_match:
            return None
        body = add_match.group(1).strip()
        kind = "Agent"
        if re.match(r"step\b", body, re.IGNORECASE):
            kind = "Step"
            body = re.sub(r"^step\b", "", body, flags=re.IGNORECASE).strip()
        elif re.match(r"agent\b", body, re.IGNORECASE):
            body = re.sub(r"^agent\b", "", body, flags=re.IGNORECASE).strip()

        placement_split = re.split(r"\s+(?:after|before|above|below|between|in\s+front\s+of|ahead\s+of|upstream\s+of|with|that|to|for)\b", body, maxsplit=1, flags=re.IGNORECASE)
        label_seed = placement_split[0].strip()
        if re.search(r"\bstep$", label_seed, re.IGNORECASE):
            kind = "Step"
        elif re.search(r"\bagent$", label_seed, re.IGNORECASE):
            kind = "Agent"
        label = self.clean_workflow_label(label_seed, kind)
        if workflow_slug(label) in {"researcher", "researcher-agent"}:
            label = "Research"
        if not label:
            return False, "Tell me the name of the agent or step to add."
        existing_node = self.workflow_find_node(workflow_map, label)
        if existing_node:
            return False, f"{existing_node['label']} already exists in the workflow map."

        node_id = self.unique_workflow_node_id(workflow_map, label)
        node_count = len(workflow_map.get("nodes", []))
        meta_match = re.search(r"\b(?:that|to|for)\s+(.+?)(?=\s+\bafter\b|\s+\bbefore\b|\s+\bwith\b|[.;]|$)", message, re.IGNORECASE)
        if re.search(r"\bhandoff\s+(?:markdown\s+)?files?\b", message, re.IGNORECASE):
            recipient = "Planner" if re.search(r"\bplanner\b", message, re.IGNORECASE) else "downstream agents"
            if workflow_slug(label) == "research":
                file_kind = "Markdown files" if re.search(r"\bmarkdown\b", message, re.IGNORECASE) else "files"
                meta = f"Researches context and writes handoff {file_kind} for {recipient}."
            else:
                meta = f"Prepares handoff files for {recipient}."
        else:
            meta = compact_workflow_text(meta_match.group(1), limit=220) if meta_match else f"Custom {kind.lower()} in the workflow."
        node = {
            "id": node_id,
            "detailKey": node_id,
            "kind": kind,
            "label": label,
            "color": workflow_color_for_kind(kind, node_count),
            "meta": meta,
            "acceptsHumanInput": False,
            "locked": False,
            "rules": [],
        }
        workflow_map.setdefault("nodes", []).append(node)

        label_for_edge = self.workflow_infer_handoff_label(message)
        between_match = re.search(r"\bbetween\s+(?:the\s+)?(.+?)\s+\band\s+(?:the\s+)?(.+?)(?=\s+\bwith\b|[.;,]|$)", message, re.IGNORECASE)
        after_match = re.search(r"\b(?:after|below)\s+(?:the\s+)?(?:current\s+|existing\s+)?(.+?)(?=\s+\bwith\b|\s+\bthat\b|\s+\bto\b|\s+\bfor\b|\s+\band\b|[.;,]|$)", message, re.IGNORECASE)
        before_match = re.search(r"\b(?:before|above|in\s+front\s+of|ahead\s+of|upstream\s+of)\s+(?:the\s+)?(?:current\s+|existing\s+)?(.+?)(?=\s+\bwith\b|\s+\bthat\b|\s+\bto\b|\s+\bfor\b|\s+\band\b|[.;,]|$)", message, re.IGNORECASE)

        if between_match:
            source = self.workflow_find_node(workflow_map, between_match.group(1))
            target = self.workflow_find_node(workflow_map, between_match.group(2))
            if not source or not target:
                workflow_map["nodes"].pop()
                return False, "I could not find both nodes for that between placement."
            source_row = self.workflow_row_index(workflow_map, source["id"])
            self.workflow_insert_row(workflow_map, node_id, source_row + 1 if source_row >= 0 else len(workflow_map.get("rows", [])))
            removed = self.workflow_remove_edges(workflow_map, lambda edge: edge.get("from") == source["id"] and edge.get("to") == target["id"])
            self.workflow_add_edge(workflow_map, source["id"], node_id, label_for_edge)
            self.workflow_add_edge(workflow_map, node_id, target["id"], str(removed[0].get("label") if removed else "handoff"))
            self.workflow_maybe_add_handoff_file_rule(workflow_map, node_id, target["id"], message)
            return True, f"Added {label} between {source['label']} and {target['label']}."

        prefer_before = before_match and (not after_match or before_match.start() > after_match.start())
        if prefer_before:
            target = self.workflow_find_node(workflow_map, before_match.group(1))
            if not target:
                workflow_map["nodes"].pop()
                return False, "I could not find the node that should come after this new node."
            self.workflow_add_node_before(workflow_map, node, target["id"], label_for_edge)
            self.workflow_maybe_add_handoff_file_rule(workflow_map, node_id, target["id"], message)
            return True, f"Added {label} before {target['label']}."

        if after_match:
            target = self.workflow_find_node(workflow_map, after_match.group(1))
            if not target:
                workflow_map["nodes"].pop()
                return False, "I could not find the node that should come before this new node."
            self.workflow_add_node_after(workflow_map, node, target["id"], label_for_edge)
            self.workflow_maybe_add_handoff_file_rule(workflow_map, target["id"], node_id, message)
            return True, f"Added {label} after {target['label']}."

        if before_match:
            target = self.workflow_find_node(workflow_map, before_match.group(1))
            if not target:
                workflow_map["nodes"].pop()
                return False, "I could not find the node that should come after this new node."
            self.workflow_add_node_before(workflow_map, node, target["id"], label_for_edge)
            self.workflow_maybe_add_handoff_file_rule(workflow_map, node_id, target["id"], message)
            return True, f"Added {label} before {target['label']}."

        workflow_map.setdefault("rows", []).append([node_id])
        if len(workflow_map["rows"]) >= 2:
            previous_row = workflow_map["rows"][-2]
            previous_id = previous_row[-1] if previous_row else ""
            if previous_id:
                self.workflow_add_edge(workflow_map, previous_id, node_id, label_for_edge)
        return True, f"Added {label} to the end of the workflow map."

    def workflow_apply_message(self, workflow_map: dict, message: str) -> tuple[bool, str]:
        text = compact_workflow_text(message, limit=1000)
        if not text:
            return False, "Send a workflow map change first."
        lowered = text.lower()
        if lowered in {"hi", "hello", "hey"} or re.search(r"\b(?:no|nothing|none)\b.*\b(?:workflow|map|change|update)\b", lowered) or "no map change" in lowered or "remain unchanged" in lowered:
            return False, "No workflow-map update is needed."
        if "help" in lowered or lowered in {"examples", "example"}:
            return False, self.workflow_agent_help()
        if "reset" in lowered and "workflow" in lowered:
            workflow_map.clear()
            workflow_map.update(self.clone_default_workflow_map())
            return True, "Reset the workflow map to the core Planner, Worker, and Reviewer flow."

        for handler in (
            self.workflow_apply_handoff_rule,
            self.workflow_apply_add_node,
            self.workflow_apply_add_handoff,
            self.workflow_apply_rule,
            self.workflow_apply_remove_node,
        ):
            result = handler(workflow_map, text)
            if result is not None:
                return result
        return False, self.workflow_agent_help()

    def workflow_result_allows_interpretation_retry(self, reply: str) -> bool:
        lowered = str(reply or "").lower()
        if not lowered:
            return True
        if reply == self.workflow_agent_help():
            return True
        return any(fragment in lowered for fragment in (
            "could not find",
            "already exists",
            "tell me",
            "name the",
            "send a workflow",
            "left it in place",
        ))

    def workflow_apply_interpreted_message(self, workflow_map: dict, owner_message: str, model_reply: str = "") -> tuple[bool, str]:
        changed, reply = self.workflow_apply_message(workflow_map, owner_message)
        clean_reply = compact_workflow_text(model_reply, limit=1000)
        if changed or not clean_reply or not self.workflow_result_allows_interpretation_retry(reply):
            return changed, reply
        interpreted_changed, interpreted_reply = self.workflow_apply_message(workflow_map, clean_reply)
        if interpreted_changed or not self.workflow_result_allows_interpretation_retry(interpreted_reply):
            return interpreted_changed, interpreted_reply
        return changed, reply

    WORKFLOW_AGENT_OUTPUT_MARKER = "===WORKFLOW-AGENT-OUTPUT==="

    def load_workflow_agent_chat(self) -> dict:
        try:
            data = json.loads(WORKFLOW_AGENT_CHAT_SESSION_PATH.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        if not isinstance(data.get("messages"), list):
            data["messages"] = []
        return data

    def save_workflow_agent_chat(self, data: dict) -> None:
        WORKFLOW_AGENT_CHAT_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = WORKFLOW_AGENT_CHAT_SESSION_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, WORKFLOW_AGENT_CHAT_SESSION_PATH)

    def read_workflow_agent_output(self, log_path: str, truncate: bool = True) -> str:
        if not log_path:
            return ""
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, OSError):
            return ""
        marker = self.WORKFLOW_AGENT_OUTPUT_MARKER
        if marker in text:
            text = text.split(marker, 1)[1]
        text = strip_terminal_control_sequences(text)
        text = text.strip()
        if truncate and len(text) > PLANNER_CHAT_OUTPUT_LIMIT:
            text = "...(truncated)...\n" + text[-PLANNER_CHAT_OUTPUT_LIMIT:]
        return text

    def workflow_clean_tool_reply(self, tool: str, raw: str, limit: int = PLANNER_CHAT_OUTPUT_LIMIT) -> str:
        tool = str(tool or "").strip().lower()
        if tool == "claude" and raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                reply = str(parsed.get("result") or "").strip()
                if reply:
                    clean_reply = self._extract_clean_reply(reply) or reply
                    return clean_reply[:limit]
        if tool == "codex" and raw:
            codex_matches = list(re.finditer(r"(?:^|\n)codex\s*\n", raw, re.IGNORECASE))
            if codex_matches:
                tail = raw[codex_matches[-1].end():].strip()
                tail = re.split(r"\ntokens used\b", tail, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                if tail:
                    return tail[:limit]
        clean = self._extract_clean_reply(raw)
        if clean:
            return clean[:limit]
        return raw[:limit]

    def workflow_agent_token_usage_from_text(self, text: str) -> dict:
        raw = str(text or "")
        usage: dict = {}
        if not raw:
            return usage

        codex_counts = [
            parsed
            for parsed in (
                parse_count_int(match.group(1))
                for match in re.finditer(
                    r"(?im)^\s*tokens used\s*(?::\s*|\s+|\r?\n\s*)([0-9][0-9,._ ]*)\s*$",
                    raw,
                )
            )
            if parsed is not None
        ]
        if codex_counts:
            usage["total"] = sum(codex_counts)
            usage["source"] = "tokens used"
            usage["turns"] = len(codex_counts)
            return usage

        total_counts = [
            parsed
            for parsed in (
                parse_count_int(match.group(1))
                for match in re.finditer(r'(?i)"?total_tokens"?\s*[:=]\s*([0-9][0-9,._ ]*)', raw)
            )
            if parsed is not None
        ]
        if total_counts:
            usage["total"] = sum(total_counts)
            usage["source"] = "total_tokens"
            usage["turns"] = len(total_counts)
            return usage

        input_counts = [
            parsed
            for parsed in (
                parse_count_int(match.group(1))
                for match in re.finditer(r'(?i)"?input_tokens"?\s*[:=]\s*([0-9][0-9,._ ]*)', raw)
            )
            if parsed is not None
        ]
        output_counts = [
            parsed
            for parsed in (
                parse_count_int(match.group(1))
                for match in re.finditer(r'(?i)"?output_tokens"?\s*[:=]\s*([0-9][0-9,._ ]*)', raw)
            )
            if parsed is not None
        ]
        input_total = sum(input_counts)
        output_total = sum(output_counts)
        if input_total or output_total:
            usage["input"] = input_total
            usage["output"] = output_total
            usage["total"] = input_total + output_total
            usage["source"] = "input/output tokens"
            usage["turns"] = max(len(input_counts), len(output_counts))
        return usage

    def workflow_agent_token_usage(self, message: dict) -> dict:
        stored = message.get("tokenUsage")
        if isinstance(stored, dict) and parse_count_int(stored.get("total")) is not None:
            return stored
        raw = self.read_workflow_agent_output(str(message.get("logPath") or ""), truncate=False)
        return self.workflow_agent_token_usage_from_text(raw)

    def workflow_agent_clean_model_reply(self, message: dict) -> str:
        raw = self.read_workflow_agent_output(str(message.get("logPath") or ""), truncate=False)
        tool = str(message.get("tool") or "").strip().lower()
        try:
            proposal = self.workflow_extract_json_object(raw)
            return json.dumps(proposal, indent=2)
        except ValueError:
            pass
        return self.workflow_clean_tool_reply(tool, raw)

    def workflow_extract_json_object(self, text: str) -> dict:
        raw = strip_terminal_control_sequences(str(text or "")).strip()
        if not raw:
            raise ValueError("Workflow Agent returned an empty proposal.")
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.IGNORECASE | re.DOTALL)
        candidates = [fence_match.group(1)] if fence_match else []
        candidates.append(raw)
        decoder = json.JSONDecoder()
        matches: list[dict] = []
        for candidate in candidates:
            candidate = candidate.strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    matches.append(parsed)
            except json.JSONDecodeError:
                pass
            for index, char in enumerate(candidate):
                if char != "{":
                    continue
                try:
                    parsed, _ = decoder.raw_decode(candidate[index:])
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    matches.append(parsed)
        for parsed in reversed(matches):
            source = parsed
            for envelope_key in ("workflowMap", "workflow_map", "map"):
                if isinstance(source.get(envelope_key), dict):
                    source = source[envelope_key]
                    break
            if all(key in source for key in ("nodes", "rows", "edges", "globalRules")):
                return parsed
        if matches:
            return matches[-1]
        raise ValueError("Workflow Agent proposal did not contain a valid JSON object.")

    def workflow_validate_full_map_proposal(self, proposal: object) -> dict:
        if not isinstance(proposal, dict):
            raise ValueError("Workflow map proposal must be a JSON object.")
        source = proposal
        for envelope_key in ("workflowMap", "workflow_map", "map"):
            if isinstance(source.get(envelope_key), dict):
                source = source[envelope_key]
                break
        if not isinstance(source, dict):
            raise ValueError("Workflow map proposal must contain a workflow map object.")
        for key in ("nodes", "rows", "edges", "globalRules"):
            if key not in source:
                raise ValueError(f"Workflow map proposal is missing '{key}'.")
            if not isinstance(source.get(key), list):
                raise ValueError(f"Workflow map field '{key}' must be a list.")

        raw_node_ids: set[str] = set()
        required_node_fields = ("id", "detailKey", "kind", "label", "color", "meta", "acceptsHumanInput", "locked", "rules", "outputs")
        for index, raw_node in enumerate(source.get("nodes", [])):
            if not isinstance(raw_node, dict):
                raise ValueError(f"nodes[{index}] must be an object.")
            for field in required_node_fields:
                if field not in raw_node:
                    raise ValueError(f"nodes[{index}] is missing '{field}'.")
            if not isinstance(raw_node.get("rules"), list):
                raise ValueError(f"nodes[{index}].rules must be a list.")
            if not isinstance(raw_node.get("outputs"), list):
                raise ValueError(f"nodes[{index}].outputs must be a list.")
            node_id = workflow_slug(raw_node.get("id") or raw_node.get("label"), "")
            if not node_id:
                raise ValueError(f"nodes[{index}] is missing id/label.")
            if node_id in raw_node_ids:
                raise ValueError(f"Duplicate node id '{node_id}'.")
            raw_node_ids.add(node_id)

        for row_index, raw_row in enumerate(source.get("rows", [])):
            if not isinstance(raw_row, list):
                raise ValueError(f"rows[{row_index}] must be a list of node ids.")
            if not raw_row:
                raise ValueError(f"rows[{row_index}] must not be empty.")
            for raw_id in raw_row:
                node_id = workflow_slug(raw_id)
                if node_id not in raw_node_ids:
                    raise ValueError(f"rows[{row_index}] references unknown node id '{node_id}'.")

        required_edge_fields = ("from", "to", "label", "rules", "outputs")
        for edge_index, raw_edge in enumerate(source.get("edges", [])):
            if not isinstance(raw_edge, dict):
                raise ValueError(f"edges[{edge_index}] must be an object.")
            for field in required_edge_fields:
                if field not in raw_edge:
                    raise ValueError(f"edges[{edge_index}] is missing '{field}'.")
            if not isinstance(raw_edge.get("rules"), list):
                raise ValueError(f"edges[{edge_index}].rules must be a list.")
            if not isinstance(raw_edge.get("outputs"), list):
                raise ValueError(f"edges[{edge_index}].outputs must be a list.")
            from_id = workflow_slug(raw_edge.get("from"))
            to_id = workflow_slug(raw_edge.get("to"))
            if from_id not in raw_node_ids:
                raise ValueError(f"edges[{edge_index}].from references unknown node id '{from_id}'.")
            if to_id not in raw_node_ids:
                raise ValueError(f"edges[{edge_index}].to references unknown node id '{to_id}'.")
            if from_id == to_id:
                raise ValueError(f"edges[{edge_index}] cannot connect a node to itself.")

        for rule_index, raw_rule in enumerate(source.get("globalRules", [])):
            if not isinstance(raw_rule, (dict, str)):
                raise ValueError(f"globalRules[{rule_index}] must be a string or object.")

        normalized = self.normalize_workflow_map(source)
        normalized_nodes = self.workflow_node_by_id(normalized)
        defaults = self.clone_default_workflow_map()
        default_nodes = {
            str(node.get("id") or ""): node
            for node in defaults.get("nodes", [])
            if isinstance(node, dict)
        }
        for core_id in ("planner", "worker", "reviewer"):
            node = normalized_nodes.get(core_id)
            if not node:
                raise ValueError(f"Locked core node '{core_id}' is missing.")
            if not node.get("locked"):
                raise ValueError(f"Locked core node '{core_id}' must keep locked=true.")
            default_node = default_nodes.get(core_id, {})
            default_label = str(default_node.get("label") or "").strip()
            if default_label and str(node.get("label") or "").strip() != default_label:
                raise ValueError(f"Locked core node '{core_id}' must keep label '{default_label}'.")

        seen_row_ids: set[str] = set()
        for row_index, row in enumerate(normalized.get("rows", [])):
            if not isinstance(row, list) or not row:
                raise ValueError(f"Normalized rows[{row_index}] is invalid.")
            for node_id in row:
                if node_id in seen_row_ids:
                    raise ValueError(f"Node id '{node_id}' appears in more than one row.")
                if node_id not in normalized_nodes:
                    raise ValueError(f"Row references unknown node id '{node_id}'.")
                seen_row_ids.add(node_id)
        missing_from_rows = set(normalized_nodes) - seen_row_ids
        if missing_from_rows:
            missing = ", ".join(sorted(missing_from_rows))
            raise ValueError(f"Rows are missing node id(s): {missing}.")
        return normalized

    def workflow_parse_full_map_proposal(self, text: str) -> dict:
        return self.workflow_validate_full_map_proposal(self.workflow_extract_json_object(text))

    def workflow_canonical_map_for_compare(self, workflow_map: dict) -> dict:
        canonical = self.normalize_workflow_map(workflow_map)
        canonical["updatedAt"] = ""
        return canonical

    def workflow_maps_equal(self, left: dict, right: dict) -> bool:
        return json.dumps(self.workflow_canonical_map_for_compare(left), sort_keys=True) == json.dumps(
            self.workflow_canonical_map_for_compare(right),
            sort_keys=True,
        )

    def workflow_apply_full_map_proposal_once(self, proposal_text: str) -> tuple[bool, str, str, list[dict]]:
        proposed_map = self.workflow_parse_full_map_proposal(proposal_text)
        current_map = self.load_workflow_map()
        changed = not self.workflow_maps_equal(current_map, proposed_map)
        if changed:
            self.persist_workflow_map(proposed_map)
            node_count = len(proposed_map.get("nodes", []))
            edge_count = len(proposed_map.get("edges", []))
            return True, f"Workflow map updated from JSON proposal ({node_count} nodes, {edge_count} handoffs).", proposal_text, []
        return False, "No workflow-map update is needed.", proposal_text, []

    def public_workflow_agent_messages(self, messages: list) -> list[dict]:
        public_messages = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            if role == "owner":
                public_messages.append({
                    "id": message.get("id", ""),
                    "role": "owner",
                    "text": message.get("text", ""),
                    "createdAt": message.get("createdAt", ""),
                    "tool": message.get("tool", ""),
                })
                continue
            if role != "workflow-agent":
                continue
            diagnostics = self.read_workflow_agent_output(str(message.get("logPath") or ""))
            err_diagnostics = self.read_text_tail(str(message.get("errPath") or ""), limit=3000)
            if err_diagnostics:
                diagnostics = f"{diagnostics}\n\n[stderr]\n{err_diagnostics}".strip()
            public = {
                "id": message.get("id", ""),
                "role": "workflow-agent",
                "tool": message.get("tool", ""),
                "status": message.get("status", ""),
                "changed": bool(message.get("changed")),
                "result": message.get("result", ""),
                "modelReply": message.get("modelReply", ""),
                "diagnostics": diagnostics,
                "proposalAttempts": message.get("proposalAttempts", []),
                "tokenUsage": self.workflow_agent_token_usage(message),
                "createdAt": message.get("createdAt", ""),
                "spawnedAt": message.get("spawnedAt", ""),
                "finishedAt": message.get("finishedAt", ""),
                "processId": message.get("processId", ""),
                "processState": message.get("processState", ""),
                "exitCode": message.get("exitCode", ""),
                "terminalInfo": message.get("terminalInfo", {}),
                "isError": bool(message.get("isError")),
            }
            public_messages.append(public)
        return public_messages

    def workflow_compact_map_for_prompt(self, workflow_map: dict) -> str:
        compact_map = json.dumps({
            "version": workflow_map.get("version", 1),
            "nodes": workflow_map.get("nodes", []),
            "rows": workflow_map.get("rows", []),
            "edges": workflow_map.get("edges", []),
            "globalRules": workflow_map.get("globalRules", []),
        }, indent=2)
        if len(compact_map) > 10000:
            compact_map = compact_map[:10000] + "\n...(truncated)..."
        return compact_map

    def workflow_agent_phrase(self, message: str, workflow_map: dict) -> str:
        compact_map = self.workflow_compact_map_for_prompt(workflow_map)
        return (
            "You are the Workflow Agent for this local task-board viewer. "
            "Your job is to propose the entire workflow-map JSON after applying the owner's requested change. "
            "Do not edit files, run tools, create task-board cards, claim work, implement code, or review work. "
            "The backend will validate and persist your JSON after your turn exits. "
            "You are running in a visible interactive CLI; print the final JSON in the terminal, then the owner can inspect it and exit the CLI so the backend can apply it. "
            "Return ONLY one valid JSON object and no markdown, no prose, and no code fence. "
            "The JSON object must be the full workflow map with keys: version, nodes, rows, edges, globalRules. "
            "Every node needs id, detailKey, kind, label, color, meta, acceptsHumanInput, locked, rules, and outputs. "
            "Every edge needs from, to, label, rules, and outputs. "
            "Preserve the locked core nodes planner, worker, and reviewer with locked=true. "
            "Rows must reference existing node ids, and edges must connect existing node ids. "
            "If the owner supplies a complete workflow spec, convert it into suitable agent nodes, rows, handoff edges, node rules, edge rules, outputs, and global rules. "
            "Use type=handoff-markdown and renderAs=handoff-files for handoff file outputs. "
            "If no workflow-map change is needed, return the current map unchanged. "
            "Current workflow map:\n"
            f"{compact_map}\n\n"
            "Owner request:\n"
            f"{message}\n"
        )

    def workflow_agent_terminal_done_path(self, message_id: str, tool: str) -> Path:
        safe_tool = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(tool or "agent")).strip("-") or "agent"
        return WORKFLOW_AGENT_CHAT_DIR / f"{message_id}-{safe_tool}.done"

    def mark_workflow_agent_terminal_done(self, message_id: str, tool: str) -> None:
        try:
            WORKFLOW_AGENT_CHAT_DIR.mkdir(parents=True, exist_ok=True)
            self.workflow_agent_terminal_done_path(message_id, tool).write_text(
                f"{now_iso()}\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def launch_workflow_agent_process(
        self,
        tool: str,
        phrase: str,
        message_id: str,
        spawned_at: str,
    ) -> tuple[TerminalSessionMonitor, str, str, dict, str]:
        args = self.interactive_spawn_command_args(tool, phrase)

        WORKFLOW_AGENT_CHAT_DIR.mkdir(parents=True, exist_ok=True)
        log_path = WORKFLOW_AGENT_CHAT_DIR / f"{message_id}-{tool}.log"
        done_path = self.workflow_agent_terminal_done_path(message_id, tool)
        try:
            done_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        err_path = ""
        working_dir = str(PROJECT_ROOT)
        log_file = log_path.open("a", encoding="utf-8")
        log_file.write(f"Workflow Agent ({tool}) at {spawned_at}\n")
        log_file.write(f"Working directory: {working_dir}\n")
        log_file.write(f"{self.WORKFLOW_AGENT_OUTPUT_MARKER}\n")
        log_file.flush()
        log_file.close()

        process, terminal_info, _, _ = self.launch_recorded_interactive_terminal(
            args,
            working_dir,
            tool,
            str(log_path),
            str(done_path),
            f"Workflow Agent {tool}",
        )
        return process, str(log_path), err_path, terminal_info, str(done_path)

    def finalize_workflow_agent_message(
        self,
        message_id: str,
        return_code: int | None = None,
        process_state: str = "",
    ) -> bool:
        with WORKFLOW_AGENT_CHAT_LOCK:
            data = self.load_workflow_agent_chat()
            target = None
            for message in data.get("messages", []):
                if isinstance(message, dict) and message.get("id") == message_id:
                    target = message
                    break
            if not target or target.get("role") != "workflow-agent" or target.get("status") != "running":
                return False

            if str(target.get("tool") or "").strip().lower() == "qwen":
                time.sleep(0.5)
            model_reply = self.workflow_agent_clean_model_reply(target)
            token_usage = self.workflow_agent_token_usage(target)
            err_tail = ""
            if target.get("errPath"):
                err_tail = self.read_text_tail(str(target.get("errPath") or ""), limit=3000)
            owner_message = str(target.get("ownerMessage") or "").strip()
            target["finishedAt"] = now_iso()
            target["processState"] = process_state or target.get("processState", "")
            target["tokenUsage"] = token_usage
            if return_code is not None:
                target["exitCode"] = return_code

            if return_code not in (None, 0):
                target["status"] = "terminated"
                target["isError"] = True
                target["modelReply"] = model_reply
                detail = f" Exit code {return_code}." if return_code is not None else ""
                stderr_detail = f" {err_tail}" if err_tail else ""
                target["result"] = f"Workflow Agent terminated before applying the map update.{detail}{stderr_detail}".strip()
                self.save_workflow_agent_chat(data)
                self.mark_workflow_agent_terminal_done(message_id, str(target.get("tool") or ""))
                return True

            try:
                changed, reply, model_reply, proposal_attempts = self.workflow_apply_full_map_proposal_once(model_reply)
                target["status"] = "done"
                target["changed"] = changed
                target["result"] = reply
                target["modelReply"] = model_reply
                target["proposalAttempts"] = proposal_attempts
                target["isError"] = False
            except Exception as error:
                target["status"] = "terminated"
                target["changed"] = False
                target["isError"] = True
                target["modelReply"] = model_reply
                target["result"] = f"Workflow Agent terminated while applying the map update: {error}"
            self.save_workflow_agent_chat(data)
            self.mark_workflow_agent_terminal_done(message_id, str(target.get("tool") or ""))
            return True

    def wait_for_workflow_agent_process(self, message_id: str, process: subprocess.Popen) -> None:
        try:
            return_code = process.wait()
            process_state = "exited"
        except Exception as error:
            return_code = 1
            process_state = f"wait-error: {error}"
        self.finalize_workflow_agent_message(message_id, return_code=return_code, process_state=process_state)

    def refresh_workflow_agent_chat(self, data: dict) -> bool:
        changed = False
        for message in data.get("messages", []):
            if not isinstance(message, dict):
                continue
            if message.get("role") != "workflow-agent" or message.get("status") != "running":
                continue
            terminal_done_path = str(message.get("terminalDonePath") or "")
            terminal_done = bool(terminal_done_path and Path(terminal_done_path).exists())
            terminal_info = message.get("terminalInfo") if isinstance(message.get("terminalInfo"), dict) else {}
            status = spawned_process_status({
                "processId": message.get("processId"),
                "spawnedAt": message.get("spawnedAt"),
                "mode": "interactive" if str(terminal_info.get("mode") or "") == "interactive-terminal" else "",
            })
            message["processState"] = status.get("state", "")
            changed = True
            if terminal_done or not status.get("isRunning"):
                # Recovery path for backend restarts where the waiter thread is gone.
                model_reply = self.workflow_agent_clean_model_reply(message)
                message["finishedAt"] = now_iso()
                message["modelReply"] = model_reply
                message["tokenUsage"] = self.workflow_agent_token_usage(message)
                if model_reply:
                    try:
                        applied, reply, final_reply, proposal_attempts = self.workflow_apply_full_map_proposal_once(model_reply)
                        message["status"] = "done"
                        message["changed"] = applied
                        message["result"] = reply
                        message["modelReply"] = final_reply
                        message["proposalAttempts"] = proposal_attempts
                        message["isError"] = False
                    except Exception as error:
                        message["status"] = "terminated"
                        message["changed"] = False
                        message["result"] = f"Workflow Agent terminated while applying the map update: {error}"
                        message["isError"] = True
                else:
                    message["status"] = "terminated"
                    message["changed"] = False
                    message["result"] = "Workflow Agent process is no longer running and produced no reply."
                    message["isError"] = True
                self.mark_workflow_agent_terminal_done(
                    str(message.get("id") or ""),
                    str(message.get("tool") or ""),
                )
        return changed

    def workflow_chat_poll(self, board: dict, payload: dict) -> dict:
        del board, payload
        with WORKFLOW_AGENT_CHAT_LOCK:
            data = self.load_workflow_agent_chat()
            if self.refresh_workflow_agent_chat(data):
                self.save_workflow_agent_chat(data)
            return {"messages": self.public_workflow_agent_messages(data.get("messages", []))}

    def workflow_chat_clear(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns, payload
        with WORKFLOW_AGENT_CHAT_LOCK:
            self.save_workflow_agent_chat({"messages": []})
        return {"messages": []}

    def workflow_chat_send(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ValueError("Workflow chat message must not be blank")
        settings = load_dispatch_settings()
        workflow_settings = settings.get("workflow") if isinstance(settings.get("workflow"), dict) else {}
        saved_tool = normalize_dispatch_model(workflow_settings.get("model"), DEFAULT_DISPATCH_MODEL)
        requested_tool = str(payload.get("tool") or payload.get("model") or saved_tool).strip().lower()
        tool = requested_tool if requested_tool in SPAWNABLE_TOOLS else saved_tool
        if tool != saved_tool:
            settings["workflow"] = {"model": tool}
            settings["updatedAt"] = now_iso()
            persist_dispatch_settings(settings)

        timestamp = now_iso()
        with WORKFLOW_AGENT_CHAT_LOCK:
            data = self.load_workflow_agent_chat()
            if self.refresh_workflow_agent_chat(data):
                self.save_workflow_agent_chat(data)
            for existing in data.get("messages", []):
                if isinstance(existing, dict) and existing.get("role") == "workflow-agent" and existing.get("status") == "running":
                    raise ValueError("The Workflow Agent is still working. Wait for it to finish before sending another map change.")

        with WORKFLOW_MAP_LOCK:
            workflow_map = self.load_workflow_map()
            phrase = self.workflow_agent_phrase(message, workflow_map)

        message_id = f"wa_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"
        try:
            process, log_path, err_path, terminal_info, terminal_done_path = self.launch_workflow_agent_process(tool, phrase, message_id, timestamp)
        except FileNotFoundError as error:
            raise RuntimeError(f"Could not launch Workflow Agent ({tool}): {error}") from error
        except Exception as error:
            raise RuntimeError(f"Workflow Agent send failed: {error}") from error

        with WORKFLOW_AGENT_CHAT_LOCK:
            data = self.load_workflow_agent_chat()
            data["messages"].append({
                "id": f"wc_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}",
                "role": "owner",
                "text": message,
                "tool": tool,
                "createdAt": timestamp,
            })
            data["messages"].append({
                "id": message_id,
                "role": "workflow-agent",
                "tool": tool,
                "status": "running",
                "processId": process.pid,
                "processState": "running",
                "spawnedAt": timestamp,
                "createdAt": timestamp,
                "finishedAt": "",
                "ownerMessage": message,
                "logPath": log_path,
                "errPath": err_path,
                "terminalInfo": terminal_info,
                "terminalDonePath": terminal_done_path,
                "result": "",
                "modelReply": "",
                "changed": False,
                "proposalAttempts": [],
            })
            self.save_workflow_agent_chat(data)
            messages = data.get("messages", [])
        threading.Thread(
            target=self.wait_for_workflow_agent_process,
            args=(message_id, process),
            daemon=True,
        ).start()
        return {
            "sent": True,
            "status": "running",
            "tool": tool,
            "processId": process.pid,
            "terminalInfo": terminal_info,
            "messages": self.public_workflow_agent_messages(messages),
            "workflowMap": workflow_map,
        }

    def workflow_map_reset(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns, payload
        with WORKFLOW_MAP_LOCK:
            workflow_map = self.clone_default_workflow_map()
            self.persist_workflow_map(workflow_map)
            workflow_map = self.load_workflow_map()
        return {"workflowMap": workflow_map}

    def workflow_map_replace(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns
        proposal = payload.get("workflowMap") or payload.get("workflow_map") or payload.get("map") or payload
        with WORKFLOW_MAP_LOCK:
            current_map = self.load_workflow_map()
            workflow_map = self.workflow_validate_full_map_proposal(proposal)
            changed = not self.workflow_maps_equal(current_map, workflow_map)
            if changed:
                self.persist_workflow_map(workflow_map)
                workflow_map = self.load_workflow_map()
        return {
            "changed": changed,
            "workflowMap": workflow_map,
        }

    def get_pause_status(self, board: dict, payload: dict) -> dict:
        del board, payload
        return active_pause_status()

    def read_recent_jsonl_entries(self, path: Path, limit: int = 40, max_bytes: int = 160000) -> list[dict]:
        if limit <= 0 or not path.exists() or not path.is_file():
            return []
        try:
            size = path.stat().st_size
            with path.open("rb") as log_file:
                if size > max_bytes:
                    log_file.seek(size - max_bytes)
                    raw = log_file.read(max_bytes)
                else:
                    raw = log_file.read()
        except OSError:
            return []
        text = raw.decode("utf-8", errors="replace")
        if size > max_bytes:
            text = text.split("\n", 1)[-1]
        entries: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries[-limit:]

    def recent_log_summary(self) -> dict:
        entries = []
        for label, path in (("api", API_LOG_PATH), ("viewer", VIEWER_LOG_PATH)):
            for entry in self.read_recent_jsonl_entries(path, limit=50):
                entry = dict(entry)
                entry["log"] = label
                entries.append(entry)
        entries.sort(key=lambda entry: str(entry.get("at") or ""))
        recent = entries[-50:]
        errors = [
            entry for entry in recent
            if str(entry.get("status") or "").strip().lower() == "error"
        ]
        latest_error = errors[-1] if errors else {}
        latest_entry = recent[-1] if recent else {}
        return {
            "recentCount": len(recent),
            "errorCount": len(errors),
            "latestAt": latest_entry.get("at", ""),
            "latestAction": latest_entry.get("action", ""),
            "latestError": {
                "at": latest_error.get("at", ""),
                "path": latest_error.get("path", ""),
                "action": latest_error.get("action", ""),
                "httpStatus": latest_error.get("httpStatus", ""),
                "agentName": latest_error.get("agentName", ""),
                "error": latest_error.get("error", ""),
                "log": latest_error.get("log", ""),
            } if latest_error else {},
            "recentErrors": [
                {
                    "at": entry.get("at", ""),
                    "path": entry.get("path", ""),
                    "action": entry.get("action", ""),
                    "httpStatus": entry.get("httpStatus", ""),
                    "agentName": entry.get("agentName", ""),
                    "error": entry.get("error", ""),
                    "log": entry.get("log", ""),
                }
                for entry in errors[-5:]
            ],
        }

    def board_health_summary(self, board: dict) -> dict:
        columns = self.get_columns(board)
        counts = {
            column_name: len(column) if isinstance(column, list) else 0
            for column_name, column in columns.items()
        }
        for column_name in BOARD_COLUMN_ORDER:
            counts.setdefault(column_name, 0)

        ids_by_task: dict[str, list[str]] = {}
        malformed_tasks = 0
        dependency_edges: list[tuple[str, str]] = []
        for column_name, column in columns.items():
            if not isinstance(column, list):
                continue
            for task in column:
                if not isinstance(task, dict) or not self.is_valid_task(task):
                    malformed_tasks += 1
                    continue
                task_id = str(task.get("id") or "").strip()
                ids_by_task.setdefault(task_id, []).append(column_name)
                depends_on = task.get("dependsOn")
                if isinstance(depends_on, list):
                    for dep_id in depends_on:
                        dep_text = str(dep_id or "").strip()
                        if dep_text:
                            dependency_edges.append((task_id, dep_text))

        duplicate_task_ids = [
            {"taskId": task_id, "columns": locations}
            for task_id, locations in sorted(ids_by_task.items())
            if len(locations) > 1
        ]
        missing_dependencies = [
            {"taskId": task_id, "missingTaskId": dep_id}
            for task_id, dep_id in dependency_edges
            if dep_id not in ids_by_task
        ]
        active_locks = {
            "claimed": counts.get("claimed", 0),
            "reviewing": counts.get("reviewing", 0),
        }
        warnings = []
        if duplicate_task_ids:
            warnings.append(f"{len(duplicate_task_ids)} duplicate task id(s)")
        if malformed_tasks:
            warnings.append(f"{malformed_tasks} malformed task record(s)")
        if missing_dependencies:
            warnings.append(f"{len(missing_dependencies)} missing dependency reference(s)")
        return {
            "counts": counts,
            "activeLocks": active_locks,
            "totalTasks": sum(counts.values()),
            "duplicateTaskIds": duplicate_task_ids[:20],
            "malformedTasks": malformed_tasks,
            "missingDependencies": missing_dependencies[:20],
            "warningCount": len(warnings),
            "warnings": warnings,
        }

    def stale_agent_status_summary(self, board: dict, stale_agents: list[dict]) -> dict:
        columns = self.get_columns(board)
        active_lock_columns = {
            "worker": ("claimed", "claimedBy"),
            "review": ("reviewing", "reviewClaimedBy"),
        }
        now = datetime.now(timezone.utc).astimezone()
        records = []
        lock_records = []

        def agent_name_matches(left: str, right: str) -> bool:
            return bool(left and right and left.strip().lower() == right.strip().lower())

        for agent in stale_agents:
            if not isinstance(agent, dict):
                continue
            role = self.normalize_agent_role(agent.get("role"))
            personal_name = str(agent.get("personalName") or agent.get("agentName") or "").strip()
            current_task_id = str(agent.get("currentTaskId") or "").strip()
            last_heartbeat_at = str(agent.get("lastHeartbeatAt") or "").strip()
            record = {
                "agentId": str(agent.get("agentId") or "").strip(),
                "personalName": personal_name,
                "role": role,
                "model": self.normalize_agent_model(agent.get("model")),
                "lastHeartbeatAt": last_heartbeat_at,
                "currentTaskId": current_task_id,
                "currentColumn": "",
                "lockOwner": "",
                "lockMatchesAgent": False,
                "requiresAction": False,
                "reason": "No active task lock is recorded for this stale agent.",
            }
            last_seen = self.parse_iso_timestamp(last_heartbeat_at)
            if last_seen:
                record["lastSeenSecondsAgo"] = max(0, int((now - last_seen).total_seconds()))

            expected_column, owner_field = active_lock_columns.get(role, ("", ""))
            if current_task_id:
                search_columns = [expected_column] if expected_column else []
                for fallback_column in ("claimed", "reviewing"):
                    if fallback_column not in search_columns:
                        search_columns.append(fallback_column)
                found_task = None
                found_column = ""
                for column_name in search_columns:
                    column = columns.get(column_name) if isinstance(columns.get(column_name), list) else []
                    for task in column:
                        if isinstance(task, dict) and str(task.get("id") or "").strip() == current_task_id:
                            found_task = task
                            found_column = column_name
                            break
                    if found_task:
                        break

                if found_task:
                    lock_owner = str(found_task.get(owner_field) or "").strip() if owner_field else ""
                    matches_agent = agent_name_matches(personal_name, lock_owner)
                    record.update({
                        "currentColumn": found_column,
                        "lockOwner": lock_owner,
                        "lockMatchesAgent": matches_agent,
                    })
                    if expected_column and found_column == expected_column and matches_agent:
                        record["requiresAction"] = True
                        record["reason"] = f"Stale {role} still owns an active {found_column} lock."
                    else:
                        record["reason"] = "Task reference no longer matches an active lock owned by this stale agent."
                else:
                    record["reason"] = "Task reference is historical; the task is not in an active lock column."

            records.append(record)
            if record["requiresAction"]:
                lock_records.append(record)

        return {
            "records": records[:12],
            "lockRecords": lock_records[:12],
            "lockCount": len(lock_records),
            "historyCount": max(0, len(records) - len(lock_records)),
            "policy": "Stale agent records are retained as history. Owner action is only needed when a stale record still owns a claimed or reviewing task lock.",
        }

    def get_system_status(self, board: dict, payload: dict) -> dict:
        del payload
        checked_at = now_iso()
        now = datetime.now(timezone.utc).astimezone()
        settings = load_dispatch_settings()
        pause = pause_status_from_settings(settings, now=now)
        agent_state = self.agent_presence_summary()
        agents = [
            agent for agent in agent_state.get("agents", [])
            if isinstance(agent, dict)
        ]
        active_agents = [
            agent for agent in agent_state.get("activeAgents", [])
            if isinstance(agent, dict)
        ]
        stale_agents = [
            agent for agent in agents
            if str(agent.get("status") or "").strip().lower() == "stale"
        ]
        pending_spawns = [
            spawn for spawn in agent_state.get("pendingSpawns", [])
            if isinstance(spawn, dict)
        ]
        paused_runs = [
            run for run in agent_state.get("pausedRuns", [])
            if isinstance(run, dict)
        ]
        board_health = self.board_health_summary(board)
        logs = self.recent_log_summary()
        stale_summary = self.stale_agent_status_summary(board, stale_agents)

        warning_items = []
        notice_items = []
        if board_health["warningCount"]:
            warning_items.extend(board_health["warnings"])
        if stale_summary["lockCount"]:
            stale_names = [
                str(record.get("personalName") or record.get("agentId") or "agent")
                for record in stale_summary["lockRecords"][:4]
            ]
            warning_items.append(
                f"{stale_summary['lockCount']} stale agent lock(s) need attention"
                + (f": {', '.join(stale_names)}" if stale_names else "")
            )
        elif stale_agents:
            notice_items.append(
                f"{len(stale_agents)} stale agent record(s) retained as history; no active locks need action"
            )
        if logs["errorCount"]:
            warning_items.append(f"{logs['errorCount']} recent API/viewer error(s)")

        status = "ok"
        if logs["errorCount"] or board_health["duplicateTaskIds"] or board_health["malformedTasks"]:
            status = "attention"
        elif pause.get("isPaused") or warning_items:
            status = "watch"

        dispatch = {}
        planner_settings = settings.get("planner") if isinstance(settings.get("planner"), dict) else {}
        dispatch["planner"] = {
            "model": normalize_dispatch_model(planner_settings.get("model"), DEFAULT_PLANNER_MODEL),
        }
        for role in ("worker", "review"):
            role_settings = settings.get(role) if isinstance(settings.get(role), dict) else {}
            dispatch[role] = {
                "enabled": bool(role_settings.get("enabled")),
                "model": normalize_dispatch_model(role_settings.get("model"), DEFAULT_DISPATCH_MODEL),
                "maxAgents": normalize_max_agents(role_settings.get("maxAgents"), 1),
                "activeAgents": len([
                    agent for agent in active_agents
                    if str(agent.get("role") or "").strip().lower() == role
                ]),
                "pendingSpawns": len([
                    spawn for spawn in pending_spawns
                    if str(spawn.get("role") or "").strip().lower() == role
                ]),
            }

        return {
            "ok": status == "ok",
            "status": status,
            "checkedAt": checked_at,
            "server": {
                "startedAt": SERVER_STARTED_AT,
                "uptimeSeconds": max(0, int(time.monotonic() - SERVER_STARTED_MONOTONIC)),
                "host": SERVER_HOST,
                "port": SERVER_PORT,
                "projectRoot": str(PROJECT_ROOT),
            },
            "board": board_health,
            "pause": pause,
            "agents": {
                "total": len(agents),
                "active": len(active_agents),
                "stale": len(stale_agents),
                "staleWithLocks": stale_summary["lockCount"],
                "staleHistory": stale_summary["historyCount"],
                "staleRecords": stale_summary["records"],
                "stalePolicy": stale_summary["policy"],
                "pendingSpawns": len(pending_spawns),
                "pausedRuns": len(paused_runs),
            },
            "dispatch": dispatch,
            "logs": logs,
            "warnings": warning_items[:12],
            "notices": notice_items[:12],
        }

    def pause_plus_one_hour(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns
        settings = load_dispatch_settings()
        timestamp = now_iso()
        now = datetime.now(timezone.utc).astimezone()
        existing_until = parse_iso_datetime(normalize_pause_state(settings.get("pause")).get("pausedUntil"))
        base_time = now
        if existing_until and seconds_remaining_until(existing_until, now) > 0:
            base_time = local_process_datetime(existing_until)
        paused_until = base_time + timedelta(seconds=PAUSE_INCREMENT_SECONDS)
        settings["pause"] = {
            "pausedUntil": paused_until.isoformat(timespec="seconds"),
            "pausedBy": self.agent_name(payload, "Task board viewer"),
            "pausedAt": timestamp,
            "pauseReason": str(
                payload.get("pauseReason")
                or payload.get("reason")
                or "Manual task-board pause"
            ).strip(),
        }
        settings["updatedAt"] = timestamp
        persist_dispatch_settings(settings)
        status = active_pause_status(now=now)
        status["addedSeconds"] = PAUSE_INCREMENT_SECONDS
        status["ok"] = True
        return status

    def resume_now(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns
        settings = load_dispatch_settings()
        settings["pause"] = default_dispatch_settings()["pause"]
        settings["updatedAt"] = now_iso()
        persist_dispatch_settings(settings)
        status = active_pause_status()
        status["resumedBy"] = self.agent_name(payload, "Task board viewer")
        status["ok"] = True
        return status

    def require_not_paused(self, action: str) -> None:
        status = active_pause_status()
        if not status.get("isPaused"):
            return
        payload = paused_error_payload(status)
        payload["action"] = action
        raise JsonResponseError(str(payload["error"]), status=423, payload=payload)

    def active_agent_for_spawn(self, spawn: dict, agents: list[dict]) -> dict | None:
        spawn_role = self.normalize_agent_role(spawn.get("role"))
        spawn_model = self.normalize_agent_model(spawn.get("model"))
        spawn_name = str(spawn.get("personalName") or "").strip().lower()
        matches = []
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            if self.normalize_agent_role(agent.get("role")) != spawn_role:
                continue
            if self.normalize_agent_model(agent.get("model")) != spawn_model:
                continue
            agent_name = str(agent.get("personalName") or agent.get("agentName") or "").strip().lower()
            if agent_name != spawn_name:
                continue
            matches.append(agent)
        if len(matches) == 1:
            return matches[0]
        return None

    def task_column_for_id(self, board: dict, task_id: str) -> str:
        if not task_id:
            return ""
        try:
            column_name, _, _, _ = self.find_task_location(self.get_columns(board), task_id)
            return column_name
        except (LookupError, ValueError):
            return ""

    def infer_task_from_board_lock(self, board: dict, role: str, personal_name: str) -> dict:
        columns = self.get_columns(board)
        if role == "worker":
            column_name = "claimed"
            owner_fields = ("claimedBy",)
        elif role == "review":
            column_name = "reviewing"
            owner_fields = ("reviewClaimedBy", "reviewedBy")
        else:
            return {"currentTaskId": "", "currentColumn": "", "taskInference": "unsupported-role"}

        matches = []
        normalized_name = personal_name.strip().lower()
        for task in columns.get(column_name, []) or []:
            if not isinstance(task, dict):
                continue
            owners = {
                str(task.get(field) or "").strip().lower()
                for field in owner_fields
            }
            if normalized_name and normalized_name in owners:
                matches.append(task)
        if len(matches) == 1:
            return {
                "currentTaskId": str(matches[0].get("id") or "").strip(),
                "currentColumn": column_name,
                "taskInference": "board-lock",
            }
        if len(matches) > 1:
            return {"currentTaskId": "", "currentColumn": column_name, "taskInference": "ambiguous-board-lock"}
        return {"currentTaskId": "", "currentColumn": "", "taskInference": "none"}

    def infer_spawn_task_context(self, board: dict, spawn: dict, agents: list[dict]) -> dict:
        role = self.normalize_agent_role(spawn.get("role"))
        personal_name = str(spawn.get("personalName") or "").strip()
        active_agent = self.active_agent_for_spawn(spawn, agents)
        if active_agent:
            task_id = str(active_agent.get("currentTaskId") or "").strip()
            if task_id:
                return {
                    "currentTaskId": task_id,
                    "currentColumn": self.task_column_for_id(board, task_id),
                    "taskInference": "active-agent",
                    "activeAgentId": str(active_agent.get("agentId") or "").strip(),
                }
        inferred = self.infer_task_from_board_lock(board, role, personal_name)
        inferred["activeAgentId"] = str(active_agent.get("agentId") or "").strip() if active_agent else ""
        return inferred

    def upsert_paused_run(self, paused_runs: list, entry: dict) -> None:
        process_id = str(entry.get("processId") or "").strip()
        log_path = str(entry.get("logPath") or "").strip()
        for index, existing in enumerate(paused_runs):
            if not isinstance(existing, dict):
                continue
            same_process = process_id and str(existing.get("processId") or "").strip() == process_id
            same_log = log_path and str(existing.get("logPath") or "").strip() == log_path
            if same_process or same_log:
                paused_runs[index] = {**existing, **entry}
                return
        paused_runs.append(entry)

    def hard_stop_spawned_agents(self, board: dict, columns: dict, payload: dict) -> dict:
        del columns
        pause_status = active_pause_status()
        if not pause_status.get("isPaused"):
            raise JsonResponseError(
                "Hard stop requires an active board pause. Pause the board before stopping spawned agents.",
                status=409,
                payload={
                    "error": "Hard stop requires an active board pause. Pause the board before stopping spawned agents.",
                    "paused": False,
                    "isPaused": False,
                },
            )

        requested_role = self.normalize_agent_role(payload.get("role")) if payload.get("role") else ""
        if requested_role and requested_role not in SPAWNABLE_AGENT_ROLES:
            raise ValueError(f"Unsupported hard-stop role: {requested_role!r}. Allowed: {sorted(SPAWNABLE_AGENT_ROLES)}")

        settings = load_dispatch_settings()
        pending = settings.get("pendingSpawns") if isinstance(settings.get("pendingSpawns"), list) else []
        paused_runs = settings.get("pausedRuns") if isinstance(settings.get("pausedRuns"), list) else []
        active_state = self.load_active_agents_state()
        agents = active_state.get("agents") if isinstance(active_state.get("agents"), list) else []
        stopped_at = now_iso()
        stop_reason = str(
            payload.get("stopReason")
            or payload.get("reason")
            or pause_status.get("pauseReason")
            or "Board paused by owner"
        ).strip()
        actor = self.agent_name(payload, "Task board viewer")

        remaining_pending = []
        targeted_runs = []
        skipped_runs = []
        for spawn in pending:
            if not isinstance(spawn, dict):
                continue
            role = self.normalize_agent_role(spawn.get("role"))
            if role not in SPAWNABLE_AGENT_ROLES:
                continue
            if requested_role and role != requested_role:
                remaining_pending.append(spawn)
                continue

            process_status = spawned_process_status(spawn)
            if not is_live_pending_spawn(spawn, process_status=process_status):
                skipped_runs.append({
                    "role": role,
                    "model": self.normalize_agent_model(spawn.get("model")),
                    "personalName": str(spawn.get("personalName") or "").strip(),
                    "processId": parse_process_id(spawn.get("processId")),
                    "logPath": str(spawn.get("logPath") or "").strip(),
                    "status": process_status,
                    "reason": "not-running",
                })
                continue

            context = self.infer_spawn_task_context(board, spawn, agents)
            paused_entry = {
                "role": role,
                "model": self.normalize_agent_model(spawn.get("model")),
                "personalName": str(spawn.get("personalName") or "").strip(),
                "processId": parse_process_id(spawn.get("processId")),
                "logPath": str(spawn.get("logPath") or "").strip(),
                "spawnedAt": str(spawn.get("spawnedAt") or "").strip(),
                "stoppedAt": stopped_at,
                "stoppedBy": actor,
                "stopReason": stop_reason,
                "currentTaskId": context.get("currentTaskId", ""),
                "currentColumn": context.get("currentColumn", ""),
                "taskInference": context.get("taskInference", ""),
                "activeAgentId": context.get("activeAgentId", ""),
                "statusBeforeStop": process_status,
            }
            stop_status = terminate_spawned_process(spawn, process_status)
            paused_entry["stopStatus"] = stop_status
            paused_entry["resumeReady"] = bool(stop_status.get("terminated"))
            paused_entry["resumeState"] = "waiting" if stop_status.get("terminated") else "stop-failed"
            self.upsert_paused_run(paused_runs, paused_entry)
            targeted_runs.append(paused_entry)
            if not stop_status.get("terminated"):
                remaining_pending.append(spawn)

        settings["pendingSpawns"] = remaining_pending
        settings["pausedRuns"] = paused_runs[-100:]
        settings["updatedAt"] = now_iso()
        persist_dispatch_settings(settings)

        stopped_count = sum(1 for run in targeted_runs if run.get("stopStatus", {}).get("terminated"))
        if not targeted_runs:
            message = "No running backend-spawned Worker/Reviewer processes were found."
        else:
            message = f"Stopped {stopped_count} of {len(targeted_runs)} backend-spawned process(es)."
        return {
            "ok": True,
            "paused": True,
            "isPaused": True,
            "message": message,
            "stoppedCount": stopped_count,
            "targetedCount": len(targeted_runs),
            "skippedCount": len(skipped_runs),
            "pausedRuns": targeted_runs,
            "skippedRuns": skipped_runs,
            "remainingPendingSpawns": len(remaining_pending),
        }

    def resume_lock_context(self, board: dict, resume_run: dict) -> dict:
        role = self.normalize_agent_role(resume_run.get("role"))
        personal_name = str(resume_run.get("personalName") or "").strip().lower()
        task_id = str(resume_run.get("currentTaskId") or "").strip()
        context = {
            "currentTaskId": task_id,
            "currentColumn": "",
            "currentTaskStillLocked": False,
            "currentTaskOwner": "",
        }
        if not task_id:
            return context
        try:
            column_name, _, _, task = self.find_task_location(self.get_columns(board), task_id)
        except (LookupError, ValueError):
            return context
        context["currentColumn"] = column_name
        if role == "worker":
            owner = str(task.get("claimedBy") or "").strip()
            context["currentTaskOwner"] = owner
            context["currentTaskStillLocked"] = column_name == "claimed" and owner.lower() == personal_name
        elif role == "review":
            owner = str(task.get("reviewClaimedBy") or "").strip()
            context["currentTaskOwner"] = owner
            context["currentTaskStillLocked"] = column_name == "reviewing" and owner.lower() == personal_name
        return context

    def build_spawn_start_phrase(
        self,
        role: str,
        tool: str,
        personal_name: str,
        backend_base_url: str,
        board: dict,
        resume_run: dict | None = None,
    ) -> str:
        base_phrase = self.start_phrase_for_role(role)
        if not base_phrase:
            raise ValueError(f"No start phrase configured for role {role!r}")

        prompt = (
            f"{base_phrase} and start; your personalName is {personal_name}; your model is {tool}; "
            f"backendBaseUrl is {backend_base_url}; use this full base URL for every task-board API call; "
            f"call {backend_base_url}/api/register-agent with personalName, model, role to receive your agentId"
        )
        if not isinstance(resume_run, dict):
            return prompt

        lock_context = self.resume_lock_context(board, resume_run)
        prior_log_path = str(resume_run.get("logPath") or "").strip()
        stopped_at = str(resume_run.get("stoppedAt") or "").strip()
        previous_process_id = str(resume_run.get("processId") or "").strip()
        current_task_id = lock_context.get("currentTaskId") or ""
        current_column = lock_context.get("currentColumn") or str(resume_run.get("currentColumn") or "").strip()
        locked_text = "true" if lock_context.get("currentTaskStillLocked") else "false"
        prompt += (
            f"; resumeMode is paused-run; previousProcessId is {previous_process_id}; "
            f"priorLogPath is {prior_log_path}; stoppedAt is {stopped_at}; "
            f"currentTaskId is {current_task_id or 'unknown'}; currentBoardColumn is {current_column or 'unknown'}; "
            f"currentTaskStillLockedByYou is {locked_text}; "
            "before editing, inspect the task board through the API and inspect the worktree; "
            "the board is the source of truth and the prior log is context only. "
            "If currentTaskStillLockedByYou is true, continue that task before claiming anything new. "
            "If currentTaskId is unknown, missing, unlocked, or owned by someone else, reconcile from the board and prior log, "
            "then either continue the safest matching locked task or unregister with a clear note."
        )
        return prompt

    def interactive_spawn_command_args(self, tool: str, start_phrase: str, command_override: object = None) -> list[str]:
        args = self.spawn_command_args(tool, command_override=command_override)
        if tool == "codex":
            args.extend(["--no-alt-screen", start_phrase])
        elif tool == "qwen":
            args.extend(["--prompt-interactive", start_phrase])
        else:
            args.append(start_phrase)
        return args

    def terminal_env_overrides(self, tool: str) -> dict[str, str]:
        env = agent_subprocess_env(tool)
        keys = ("CODEX_SQLITE_HOME", "FORCE_COLOR", "NO_COLOR", "QWEN_CODE_DEBUG")
        return {
            key: str(env.get(key) or "")
            for key in keys
            if str(env.get(key) or "").strip()
        }

    def interactive_shell_command(self, args: list[str], working_dir: str, tool: str) -> str:
        env_overrides = self.terminal_env_overrides(tool)
        if os.name == "nt":
            command = f"cd /d {subprocess.list2cmdline([working_dir])}"
            for key, value in env_overrides.items():
                command += f" && set {subprocess.list2cmdline([f'{key}={value}'])}"
            return f"{command} && {subprocess.list2cmdline(args)}"

        command = f"cd {shlex.quote(working_dir)} && "
        env_parts = [
            f"{key}={shlex.quote(value)}"
            for key, value in env_overrides.items()
        ]
        if env_parts:
            command += f"exec env {' '.join(env_parts)} {shlex.join(args)}"
        else:
            command += f"exec {shlex.join(args)}"
        return command

    def recorded_interactive_shell_command(
        self,
        args: list[str],
        working_dir: str,
        tool: str,
        log_path: str,
        done_path: str,
        exit_path: str,
        pid_path: str,
        finished_label: str,
    ) -> str:
        env_overrides = self.terminal_env_overrides(tool)
        command_args = []
        if env_overrides:
            command_args.extend(["env", *[f"{key}={value}" for key, value in env_overrides.items()]])
        command_args.extend(args)

        if os.name == "nt":
            command = f"cd /d {subprocess.list2cmdline([working_dir])}"
            command += f" && echo %PROCESSID% > {subprocess.list2cmdline([pid_path])}"
            command += f" && {subprocess.list2cmdline(command_args)}"
            command += f" && echo 0 > {subprocess.list2cmdline([exit_path])}"
            command += f" && type nul > {subprocess.list2cmdline([done_path])}"
            return command

        script_args = ["script", "-a", "-q", "-F", log_path, *command_args]
        return " ".join([
            f"printf '%s\\n' \"$$\" > {shlex.quote(pid_path)};",
            f"cd {shlex.quote(working_dir)} || exit 1;",
            "if ! command -v script >/dev/null 2>&1; then",
            f"  printf '%s\\n' {shlex.quote('The script command is required for interactive recorded agent sessions.')} | tee -a {shlex.quote(log_path)};",
            f"  printf '%s\\n' 127 > {shlex.quote(exit_path)};",
            f"  touch {shlex.quote(done_path)};",
            "  exit 127;",
            "fi;",
            shlex.join(script_args) + ";",
            "agent_rc=$?;",
            f"printf '%s\\n' \"$agent_rc\" > {shlex.quote(exit_path)};",
            f"touch {shlex.quote(done_path)};",
            f"printf '\\n%s exited (code %s). You can close this terminal.\\n' {shlex.quote(finished_label)} \"$agent_rc\";",
            "exec ${SHELL:-/bin/zsh} -l",
        ])

    def launch_recorded_interactive_terminal(
        self,
        args: list[str],
        working_dir: str,
        tool: str,
        log_path: str,
        done_path: str,
        title: str,
    ) -> tuple[TerminalSessionMonitor, dict, str, str]:
        exit_path = str(Path(done_path).with_suffix(".exit"))
        pid_path = str(Path(done_path).with_suffix(".pid"))
        try:
            Path(exit_path).unlink()
        except (FileNotFoundError, OSError):
            pass
        try:
            Path(pid_path).unlink()
        except (FileNotFoundError, OSError):
            pass
        shell_command = self.recorded_interactive_shell_command(
            args,
            working_dir,
            tool,
            log_path,
            done_path,
            exit_path,
            pid_path,
            title,
        )
        terminal = self.launch_interactive_terminal(shell_command, title)
        pid = 0
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                pid = parse_process_id(Path(pid_path).read_text(encoding="utf-8").strip())
            except (FileNotFoundError, OSError):
                pid = 0
            if pid:
                break
            time.sleep(0.05)
        monitor = TerminalSessionMonitor(pid, done_path, exit_path, now_iso())
        terminal_info = {
            "mode": "interactive-terminal",
            "terminalCommand": shell_command,
            "terminalDonePath": done_path,
            "terminalExitPath": exit_path,
            "terminalPidPath": pid_path,
            **terminal,
        }
        return monitor, terminal_info, exit_path, pid_path

    def launch_interactive_terminal(self, shell_command: str, title: str) -> dict:
        if sys.platform == "darwin":
            script = [
                'tell application "Terminal"',
                f"do script {json.dumps(shell_command)}",
                "activate",
                "end tell",
            ]
            result = subprocess.run(
                ["osascript", *sum((["-e", line] for line in script), [])],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise RuntimeError(f"Could not open Terminal: {detail or 'osascript failed'}")
            return {"terminal": "Terminal", "launcher": "osascript"}

        if os.name == "nt":
            process = subprocess.Popen(
                ["cmd.exe", "/c", "start", title, "cmd.exe", "/k", shell_command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return {"terminal": "cmd.exe", "launcherProcessId": process.pid}

        terminal_commands = [
            ("x-terminal-emulator", ["x-terminal-emulator", "-e", "bash", "-lc", shell_command]),
            ("gnome-terminal", ["gnome-terminal", "--", "bash", "-lc", shell_command]),
            ("konsole", ["konsole", "-e", "bash", "-lc", shell_command]),
            ("xfce4-terminal", ["xfce4-terminal", "--command", f"bash -lc {shlex.quote(shell_command)}"]),
            ("xterm", ["xterm", "-e", "bash", "-lc", shell_command]),
        ]
        for name, command in terminal_commands:
            if shutil.which(name):
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                return {"terminal": name, "launcherProcessId": process.pid}
        raise RuntimeError("No supported terminal app was found for interactive mode.")

    def spawn_interactive_agent(
        self,
        role: str,
        tool: str,
        personal_name: str,
        backend_base_url: str,
        start_phrase: str,
        working_dir: str,
        log_path: Path | None = None,
        resume_run: dict | None = None,
    ) -> dict:
        args = self.interactive_spawn_command_args(tool, start_phrase)
        shell_command = self.interactive_shell_command(args, working_dir, tool)
        title = f"Task Board {role} {tool}"
        terminal = self.launch_interactive_terminal(shell_command, title)
        return {
            "spawned": True,
            "mode": "interactive",
            "role": role,
            "tool": tool,
            "personalName": personal_name,
            "cliCommand": self.spawn_command_for_tool(tool),
            "startPhrase": start_phrase,
            "backendBaseUrl": backend_base_url,
            "workingDirectory": working_dir,
            "logPath": str(log_path) if log_path else "",
            "resumeOfProcessId": resume_run.get("processId", "") if isinstance(resume_run, dict) else "",
            "terminalCommand": shell_command,
            **terminal,
        }

    def agent_health_check(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns
        tool = self.normalize_agent_model(payload.get("tool") or payload.get("model"))
        if tool not in SPAWNABLE_TOOLS:
            raise ValueError(f"Unsupported health check tool: {tool!r}. Allowed: {sorted(SPAWNABLE_TOOLS)}")

        command_override = payload.get("command") if "command" in payload else None
        command_text = (
            normalize_spawn_command(command_override, "")
            if command_override is not None
            else self.spawn_command_for_tool(tool)
        )
        args = self.spawn_command_args(tool, command_override=command_override)
        if tool == "codex":
            args.extend(["exec", "--skip-git-repo-check", HEALTH_CHECK_PROMPT])
        else:
            args.extend(["-p", HEALTH_CHECK_PROMPT])
            if tool == "qwen":
                args.append("-y")

        started = time.monotonic()
        env = agent_subprocess_env(tool)
        try:
            result = subprocess.run(
                args,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
                check=False,
            )
            result.stdout = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, (bytes, bytearray)) else (result.stdout or "")
        except FileNotFoundError as error:
            return {
                "ok": False,
                "status": "not-found",
                "tool": tool,
                "command": command_text,
                "error": str(error),
                "suggestion": health_check_suggestion(tool, "not-found", error, ""),
                "durationMs": round((time.monotonic() - started) * 1000),
            }
        except subprocess.TimeoutExpired as error:
            raw_output = error.output
            if isinstance(raw_output, (bytes, bytearray)):
                output = raw_output.decode("utf-8", errors="replace")
            elif isinstance(raw_output, str):
                output = raw_output
            else:
                output = ""
            return {
                "ok": False,
                "status": "timeout",
                "tool": tool,
                "command": command_text,
                "timeoutSeconds": HEALTH_CHECK_TIMEOUT_SECONDS,
                "error": f"{tool} health check timed out after {HEALTH_CHECK_TIMEOUT_SECONDS} seconds",
                "outputPreview": self.preview_text(output),
                "suggestion": health_check_suggestion(tool, "timeout", error, output),
                "durationMs": round((time.monotonic() - started) * 1000),
            }
        except (OSError, subprocess.SubprocessError) as error:
            return {
                "ok": False,
                "status": "launch-error",
                "tool": tool,
                "command": command_text,
                "error": str(error),
                "suggestion": health_check_suggestion(tool, "launch-error", error, ""),
                "durationMs": round((time.monotonic() - started) * 1000),
            }

        output = self.preview_text(result.stdout)
        ok = result.returncode == 0
        suggestion = "" if ok else health_check_suggestion(tool, "failed", "", output)
        return {
            "ok": ok,
            "status": "ok" if ok else "failed",
            "tool": tool,
            "command": command_text,
            "executable": args[0],
            "returnCode": result.returncode,
            "outputPreview": output,
            "suggestion": suggestion,
            "codexSqliteHome": str(env.get("CODEX_SQLITE_HOME", "")) if tool == "codex" else "",
            "durationMs": round((time.monotonic() - started) * 1000),
        }

    def update_dispatch_settings(self, board: dict, columns: dict, payload: dict) -> dict:
        settings = load_dispatch_settings()
        role = normalize_dispatch_role(payload.get("role"))
        roles_payload = payload.get("roles")
        commands_payload = payload.get("commands")
        if isinstance(roles_payload, dict):
            role_updates = {
                normalize_dispatch_role(role_name): role_value
                for role_name, role_value in roles_payload.items()
                if isinstance(role_value, dict)
            }
        elif role in {"planner", "workflow", "worker", "review"}:
            role_updates = {role: payload}
        else:
            role_updates = {}

        for role_name, updates in role_updates.items():
            if role_name in {"planner", "workflow"}:
                current = settings.get(role_name, {})
                fallback_model = DEFAULT_PLANNER_MODEL if role_name == "planner" else DEFAULT_DISPATCH_MODEL
                settings[role_name] = {
                    "model": normalize_dispatch_model(updates.get("model"), current.get("model", fallback_model)),
                }
                continue
            if role_name not in {"worker", "review"}:
                continue
            current = settings.get(role_name, {})
            settings[role_name] = {
                "enabled": bool(updates.get("enabled", current.get("enabled", False))),
                "model": normalize_dispatch_model(updates.get("model"), current.get("model", DEFAULT_DISPATCH_MODEL)),
                "maxAgents": normalize_max_agents(updates.get("maxAgents"), current.get("maxAgents", 1)),
            }

        if isinstance(commands_payload, dict):
            current_commands = settings.get("commands")
            if not isinstance(current_commands, dict):
                current_commands = {}
            settings["commands"] = {
                "claude": normalize_spawn_command(
                    commands_payload.get("claude"),
                    current_commands.get("claude", CLAUDE_COMMAND),
                ),
                "codex": normalize_spawn_command(
                    commands_payload.get("codex"),
                    current_commands.get("codex", CODEX_COMMAND),
                ),
                "qwen": normalize_spawn_command(
                    commands_payload.get("qwen"),
                    current_commands.get("qwen", QWEN_COMMAND),
                ),
            }

        if payload.get("clearPending"):
            settings["pendingSpawns"] = []
        if payload.get("clearPausedRuns"):
            settings["pausedRuns"] = []

        settings["updatedAt"] = now_iso()
        persist_dispatch_settings(settings)
        return load_dispatch_settings()

    def generate_agent_id(self, existing_ids: set[str]) -> str:
        for _ in range(20):
            candidate = f"agt_{secrets.token_hex(4)}"
            if candidate not in existing_ids:
                return candidate
        return f"agt_{secrets.token_hex(6)}"

    def pick_personal_name(self, agents: list) -> str:
        schema = self.load_agent_schema()
        pool = schema.get("personalNamePool")
        if not isinstance(pool, list) or not pool:
            return ""
        active_names = {
            str(agent.get("personalName") or "").strip().lower()
            for agent in agents
            if isinstance(agent, dict) and str(agent.get("status", "")).lower() == "active"
        }
        for name in pool:
            candidate = str(name or "").strip()
            if candidate and candidate.lower() not in active_names:
                return candidate
        return str(pool[0] or "").strip()

    def normalize_board_columns(self, board: dict) -> None:
        columns = board.get("columns")
        task_lookup = board.get("tasks")
        if not isinstance(columns, dict):
            return
        if not isinstance(task_lookup, dict):
            task_lookup = {}

        for column_name, column in list(columns.items()):
            if isinstance(column, list):
                column_items = column
            elif column is None:
                column_items = []
            else:
                column_items = [column]
            normalized = []
            for item in column_items:
                if isinstance(item, dict):
                    if self.is_valid_task(item):
                        normalized.append(item)
                    continue
                if isinstance(item, str):
                    task = task_lookup.get(item)
                    if isinstance(task, dict) and self.is_valid_task(task):
                        normalized.append(task)
            columns[column_name] = normalized

    def clean_title(self, value: object) -> str:
        return str(value or "").strip()

    def clean_text(self, value: object) -> str:
        return str(value or "").strip()

    def is_valid_task(self, task: dict) -> bool:
        if not isinstance(task, dict):
            return False
        task_id = str(task.get("id", "") or "").strip()
        title = self.clean_title(task.get("title"))
        return bool(task_id and title and not title.lower().startswith("untitled"))

    def get_columns(self, board: dict) -> dict:
        columns = board.get("columns")
        if not isinstance(columns, dict):
            raise ValueError("Board is missing `columns` object")
        return columns

    def require_task_id(self, payload: dict) -> str:
        task_id = str(payload.get("taskId") or payload.get("id") or "").strip()
        if not task_id:
            raise ValueError("Missing taskId")
        return task_id

    def ensure_column(self, columns: dict, column_name: str) -> list:
        column = columns.get(column_name)
        if column is None:
            column = []
            columns[column_name] = column
        if not isinstance(column, list):
            raise ValueError(f"columns.{column_name} is not a task list")
        return column

    def find_task_location(self, columns: dict, task_id: str) -> tuple[str, list, int, dict]:
        for column_name, column in columns.items():
            if not isinstance(column, list):
                continue
            for task_index, task in enumerate(column):
                if isinstance(task, dict) and task.get("id") == task_id:
                    return column_name, column, task_index, task
        raise LookupError(f"Task {task_id} was not found on the board")

    def task_exists(self, columns: dict, task_id: str) -> bool:
        try:
            self.find_task_location(columns, task_id)
            return True
        except LookupError:
            return False

    def pop_task(self, columns: dict, column_name: str, task_id: str) -> dict:
        column = self.ensure_column(columns, column_name)
        task_index = next(
            (
                index
                for index, task in enumerate(column)
                if isinstance(task, dict) and task.get("id") == task_id
            ),
            None,
        )
        if task_index is None:
            raise LookupError(f"Task {task_id} was not found in columns.{column_name}")
        return column.pop(task_index)

    def append_note(self, task: dict, note: str) -> None:
        note = note.strip()
        if not note:
            return
        task["notes"] = f"{task.get('notes', '').rstrip()}\n\n{note}".strip()

    def agent_id(self, payload: dict) -> str:
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("agentId", "") or "").strip()

    def find_agent_by_id(self, agent_id: str) -> dict | None:
        if not agent_id:
            return None
        state = self.load_active_agents_state()
        for agent in state.get("agents", []) or []:
            if isinstance(agent, dict) and str(agent.get("agentId", "")).strip() == agent_id:
                return agent
        return None

    def agent_name(self, payload: dict, default: str) -> str:
        if not isinstance(payload, dict):
            return default
        agent_id = self.agent_id(payload)
        if agent_id:
            record = self.find_agent_by_id(agent_id)
            if record:
                name = str(record.get("personalName") or record.get("agentName") or "").strip()
                if name:
                    return name
        for field in (
            "personalName",
            "agentName",
            "agent",
            "claimedBy",
            "completedBy",
            "reviewClaimedBy",
            "reviewedBy",
            "createdBy",
            "updatedBy",
            "returnedBy",
            "archivedBy",
            "deletedBy",
        ):
            value = str(payload.get(field, "") or "").strip()
            if value:
                return value
        return default

    def add_task_id(self, task_ids: list[str], value: object) -> None:
        task_id = str(value or "").strip()
        if task_id and task_id not in task_ids:
            task_ids.append(task_id)

    def payload_task_ids(self, payload: dict) -> list[str]:
        task_ids: list[str] = []
        if not isinstance(payload, dict):
            return task_ids
        for field in ("taskId", "id", "sourceReviewTaskId", "currentTaskId"):
            self.add_task_id(task_ids, payload.get(field))
        follow_up = payload.get("followUpTask")
        if isinstance(follow_up, dict):
            self.add_task_id(task_ids, follow_up.get("id"))
        return task_ids

    def result_task_ids(self, result: object) -> list[str]:
        task_ids: list[str] = []
        if not isinstance(result, dict):
            return task_ids
        task_id_list = result.get("taskIds")
        if isinstance(task_id_list, list):
            for task_id in task_id_list:
                self.add_task_id(task_ids, task_id)
        for field in ("taskId", "relatedTaskId", "followUpTaskId"):
            self.add_task_id(task_ids, result.get(field))
        return task_ids

    def append_api_log(self, entry: dict, viewer: bool = False) -> None:
        try:
            task_ids = entry.get("taskIds")
            if not isinstance(task_ids, list):
                task_ids = []
                entry["taskIds"] = task_ids
            entry["taskId"] = task_ids[0] if len(task_ids) == 1 else ""
            entry["clientAddress"] = self.client_address[0] if self.client_address else ""
            log_lock = VIEWER_LOG_LOCK if viewer else API_LOG_LOCK
            log_path = VIEWER_LOG_PATH if viewer else API_LOG_PATH
            with log_lock:
                with log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            self.log_terminal_api_entry(entry, viewer=viewer)
        except Exception as error:
            self.log_error("Unable to append API log: %s", error)

    def log_terminal_api_entry(self, entry: dict, viewer: bool = False) -> None:
        if not self.should_log_terminal_api_entry(entry, viewer=viewer):
            return
        status = str(entry.get("status") or "").strip().lower()
        pieces = [
            f"[task-board {'viewer' if viewer else 'api'}]",
            str(entry.get("at") or now_iso()),
            str(entry.get("method") or "").upper() or "-",
            str(entry.get("path") or "-"),
            status or "-",
            str(entry.get("httpStatus") or "-"),
        ]
        action = str(entry.get("action") or "").strip()
        if action:
            pieces.append(f"action={action}")
        agent_name = str(entry.get("agentName") or "").strip()
        if agent_name:
            pieces.append(f"agent={agent_name}")
        task_ids = entry.get("taskIds")
        if isinstance(task_ids, list):
            tasks = ",".join(str(task_id) for task_id in task_ids if str(task_id or "").strip())
            if tasks:
                pieces.append(f"tasks={self.terminal_preview(tasks, 160)}")
        error = str(entry.get("error") or "").strip()
        if error:
            pieces.append(f"error={self.terminal_preview(error)}")
        stream = sys.stderr if status == "error" else sys.stdout
        print(" ".join(pieces), file=stream, flush=True)

    def should_log_terminal_api_entry(self, entry: dict, viewer: bool = False) -> bool:
        status = str(entry.get("status") or "").strip().lower()
        if status == "error":
            return True
        method = str(entry.get("method") or "").strip().upper()
        if method != "GET":
            return True
        return False

    def terminal_preview(self, text: str, limit: int = 180) -> str:
        collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(collapsed) <= limit:
            return collapsed
        return collapsed[: max(0, limit - 3)] + "..."

    def log_api_success(self, at: str, path: str, action: str, payload: dict, result: object, method: str = "POST", viewer: bool = False) -> None:
        task_ids = self.result_task_ids(result) or self.payload_task_ids(payload)
        self.append_api_log({
            "at": at,
            "method": method,
            "path": path,
            "action": action,
            "status": "success",
            "httpStatus": 200,
            "agentName": self.agent_name(payload, "Task board viewer" if viewer else "Unknown API caller"),
            "taskIds": task_ids,
            "error": "",
        }, viewer=viewer)

    def log_api_error(self, at: str, path: str, action: str, payload: dict, message: str, http_status: int, method: str = "POST", viewer: bool = False) -> None:
        self.append_api_log({
            "at": at,
            "method": method,
            "path": path,
            "action": action,
            "status": "error",
            "httpStatus": http_status,
            "agentName": self.agent_name(payload, "Task board viewer" if viewer else "Unknown API caller"),
            "taskIds": self.payload_task_ids(payload),
            "error": message,
        }, viewer=viewer)

    def record_task_api_action(self, task: dict, action: str, agent_name: str, timestamp: str) -> None:
        task["lastApiAction"] = action
        task["lastApiActor"] = agent_name
        task["lastApiAt"] = timestamp
        history = task.get("apiHistory")
        if not isinstance(history, list):
            history = []
        history.append({
            "action": action,
            "agentName": agent_name,
            "at": timestamp,
        })
        task["apiHistory"] = history[-30:]

    def record_board_api_action(self, board: dict, action: str, agent_name: str, timestamp: str, task_id: str) -> None:
        audit_log = board.get("apiAuditLog")
        if not isinstance(audit_log, list):
            audit_log = []
        audit_log.append({
            "action": action,
            "agentName": agent_name,
            "taskId": task_id,
            "at": timestamp,
        })
        board["apiAuditLog"] = audit_log[-200:]

    def update_board_timestamp(self, board: dict, timestamp: str) -> None:
        board["updatedAt"] = timestamp

    def append_unique_files(self, task: dict, files: object) -> None:
        if not isinstance(files, list):
            return
        existing = task.get("files")
        if not isinstance(existing, list):
            existing = []
            task["files"] = existing
        for file in files:
            file_text = str(file).strip()
            if file_text and file_text not in existing:
                existing.append(file_text)

    def normalize_list(self, value: object, field_name: str) -> list:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        raise ValueError(f"{field_name} must be a list")

    def normalize_int(self, value: object, default: int, field_name: str) -> int:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must be an integer") from error

    def next_task_id(self, board: dict) -> str:
        today = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")
        pattern = re.compile(rf"^TASK-{today}-(\d+)$")
        max_number = 0
        for column in self.get_columns(board).values():
            if not isinstance(column, list):
                continue
            for task in column:
                if not isinstance(task, dict):
                    continue
                match = pattern.match(str(task.get("id", "")))
                if match:
                    max_number = max(max_number, int(match.group(1)))
        return f"TASK-{today}-{max_number + 1:03d}"

    def build_new_task(self, board: dict, columns: dict, payload: dict, timestamp: str) -> dict:
        agent_name = self.agent_name(payload, "Planning Agent")
        task_id = str(payload.get("taskId") or payload.get("id") or "").strip() or self.next_task_id(board)
        title = self.clean_title(payload.get("title"))
        if not title:
            raise ValueError("Missing title")
        if title.lower().startswith("untitled"):
            raise ValueError("Task title cannot be Untitled")
        if self.task_exists(columns, task_id):
            raise ValueError(f"Task {task_id} already exists")
        raw_depends_on = payload.get("dependsOn")
        if isinstance(raw_depends_on, list) and raw_depends_on:
            for dep_id in raw_depends_on:
                dep_id_str = str(dep_id or "").strip()
                if not dep_id_str:
                    raise ValueError("dependsOn entries must be non-blank task IDs")
                if dep_id_str == task_id:
                    raise ValueError(f"Task cannot depend on itself: {task_id}")

        return {
            "id": task_id,
            "title": title,
            "project": payload.get("project", ""),
            "priority": payload.get("priority", "normal"),
            "type": payload.get("type", "implementation"),
            "status": "todo",
            "requestedBy": payload.get("requestedBy", DEFAULT_REQUESTED_BY),
            "createdBy": payload.get("createdBy") or agent_name,
            "createdAt": payload.get("createdAt") or timestamp,
            "agentName": agent_name,
            "claimedBy": "",
            "claimedAt": "",
            "reviewClaimedBy": "",
            "reviewClaimedAt": "",
            "reviewRequestedAt": "",
            "doneAt": "",
            "reviewedBy": "",
            "reviewedAt": "",
            "redoCount": self.normalize_int(payload.get("redoCount"), 0, "redoCount"),
            "summary": payload.get("summary", ""),
            "requirements": self.normalize_list(payload.get("requirements"), "requirements"),
            "acceptanceCriteria": self.normalize_list(payload.get("acceptanceCriteria"), "acceptanceCriteria"),
            "dependsOn": self.normalize_list(payload.get("dependsOn"), "dependsOn"),
            "relatedTaskIds": self.normalize_list(payload.get("relatedTaskIds"), "relatedTaskIds"),
            "files": self.normalize_list(payload.get("files"), "files"),
            "referenceImages": self.normalize_list(payload.get("referenceImages"), "referenceImages"),
            "inspectionTargets": self.normalize_list(payload.get("inspectionTargets"), "inspectionTargets"),
            "blockers": self.normalize_list(payload.get("blockers"), "blockers"),
            "sourceReviewTaskId": payload.get("sourceReviewTaskId", ""),
            "notes": payload.get("notes", ""),
        }

    def build_follow_up_task(self, board: dict, reviewed_task: dict, payload: dict, timestamp: str) -> dict:
        follow_up = payload.get("followUpTask")
        if not isinstance(follow_up, dict):
            follow_up = {}

        agent_name = self.agent_name(payload, "Review Agent")
        review_notes = str(payload.get("reviewNotes", "")).strip()
        failure_expected = self.clean_text(
            payload.get("failureExpected")
            or payload.get("expectedBehavior")
            or payload.get("expected")
        )
        failure_actual = self.clean_text(
            payload.get("failureActual")
            or payload.get("actualBehavior")
            or payload.get("actual")
        )
        failure_decision = self.clean_text(
            payload.get("failureDecision")
            or payload.get("failureReason")
            or payload.get("decision")
            or review_notes
        )
        default_notes = "\n".join([
            line
            for line in [
                f"Should be: {failure_expected}" if failure_expected else "",
                f"Actually happening: {failure_actual}" if failure_actual else "",
                f"Why it failed: {failure_decision}" if failure_decision else "",
                f"Review notes: {review_notes}" if review_notes else "",
            ]
            if line
        ])
        follow_up_title = self.clean_title(follow_up.get("title"))
        if not follow_up_title or follow_up_title.lower().startswith("untitled"):
            follow_up_title = f"Fix review feedback for {reviewed_task.get('id', 'task')}"
        return {
            "id": str(follow_up.get("id") or "").strip() or self.next_task_id(board),
            "title": follow_up_title,
            "project": follow_up.get("project") or reviewed_task.get("project", ""),
            "priority": follow_up.get("priority") or reviewed_task.get("priority", "normal"),
            "type": follow_up.get("type") or "implementation",
            "status": "todo",
            "requestedBy": follow_up.get("requestedBy") or "Review Agent",
            "createdBy": follow_up.get("createdBy") or agent_name,
            "createdAt": follow_up.get("createdAt") or timestamp,
            "agentName": agent_name,
            "claimedBy": "",
            "claimedAt": "",
            "reviewRequestedAt": "",
            "doneAt": "",
            "reviewedBy": "",
            "reviewedAt": "",
            "reviewClaimedBy": "",
            "reviewClaimedAt": "",
            "redoCount": int(follow_up.get("redoCount") or 1),
            "sourceReviewTaskId": reviewed_task.get("id", ""),
            "summary": follow_up.get("summary") or review_notes or "Address review feedback.",
            "requirements": follow_up.get("requirements") if isinstance(follow_up.get("requirements"), list) else [],
            "acceptanceCriteria": follow_up.get("acceptanceCriteria")
            if isinstance(follow_up.get("acceptanceCriteria"), list)
            else [],
            "files": follow_up.get("files") if isinstance(follow_up.get("files"), list) else reviewed_task.get("files", []),
            "referenceImages": follow_up.get("referenceImages")
            if isinstance(follow_up.get("referenceImages"), list)
            else reviewed_task.get("referenceImages", []),
            "inspectionTargets": follow_up.get("inspectionTargets")
            if isinstance(follow_up.get("inspectionTargets"), list)
            else reviewed_task.get("inspectionTargets", []),
            "blockers": follow_up.get("blockers") if isinstance(follow_up.get("blockers"), list) else [],
            "notes": follow_up.get("notes") or default_notes or review_notes,
        }

    def upsert_follow_up_task(self, board: dict, columns: dict, reviewed_task: dict, payload: dict, timestamp: str) -> dict:
        todo = self.ensure_column(columns, "todo")
        source_id = reviewed_task.get("id", "")
        existing = next(
            (
                task
                for task in todo
                if isinstance(task, dict) and task.get("sourceReviewTaskId") == source_id
            ),
            None,
        )
        follow_up = self.build_follow_up_task(board, reviewed_task, payload, timestamp)

        if existing:
            agent_name = self.agent_name(payload, "Review Agent")
            existing["redoCount"] = int(existing.get("redoCount") or 0) + 1
            existing["status"] = "todo"
            existing["priority"] = follow_up["priority"]
            existing["summary"] = follow_up["summary"]
            existing["requirements"] = follow_up["requirements"]
            existing["acceptanceCriteria"] = follow_up["acceptanceCriteria"]
            existing["files"] = follow_up["files"]
            existing["referenceImages"] = follow_up["referenceImages"]
            existing["inspectionTargets"] = follow_up["inspectionTargets"]
            existing["blockers"] = follow_up["blockers"]
            self.append_note(existing, f"Review feedback update ({timestamp}): {follow_up['notes']}")
            self.record_task_api_action(existing, "request-changes-follow-up-update", agent_name, timestamp)
            return existing

        self.record_task_api_action(follow_up, "request-changes-follow-up-create", self.agent_name(payload, "Review Agent"), timestamp)
        todo.insert(0, follow_up)
        return follow_up

    def build_agent_record(self, payload: dict, timestamp: str, existing: dict | None = None, agent_id: str = "") -> dict:
        existing = existing if isinstance(existing, dict) else {}
        personal_name = str(
            payload.get("personalName")
            or existing.get("personalName")
            or payload.get("agentName")
            or existing.get("agentName")
            or ""
        ).strip()
        if not personal_name:
            raise ValueError("Missing personalName")
        resolved_id = (agent_id or str(existing.get("agentId") or "").strip()).strip()
        if not resolved_id:
            raise ValueError("Missing agentId")
        role = self.normalize_agent_role(payload.get("role") or existing.get("role"))
        model = self.normalize_agent_model(payload.get("model") or existing.get("model"))
        start_phrase = str(payload.get("startPhrase") or existing.get("startPhrase") or self.start_phrase_for_role(role) or "").strip()
        current_task_id = str(payload.get("currentTaskId") if "currentTaskId" in payload else existing.get("currentTaskId", "")).strip()
        notes = str(payload.get("notes") if "notes" in payload else existing.get("notes", "")).strip()
        return {
            "agentId": resolved_id,
            "personalName": personal_name,
            "model": model,
            "agentName": personal_name,
            "role": role,
            "startPhrase": start_phrase,
            "registeredAt": str(existing.get("registeredAt") or payload.get("registeredAt") or timestamp).strip(),
            "lastHeartbeatAt": timestamp,
            "currentTaskId": current_task_id,
            "status": str(payload.get("status") or "active").strip().lower() or "active",
            "notes": notes,
        }

    def upsert_agent_record(self, payload: dict, timestamp: str, generate_id_if_missing: bool = False) -> tuple[dict, str]:
        state = self.load_active_agents_state()
        agents = state.get("agents")
        if not isinstance(agents, list):
            agents = []
            state["agents"] = agents
        incoming_id = self.agent_id(payload)
        existing_index = None
        if incoming_id:
            existing_index = next(
                (
                    index
                    for index, agent in enumerate(agents)
                    if isinstance(agent, dict) and str(agent.get("agentId", "")).strip() == incoming_id
                ),
                None,
            )
        if existing_index is None and not incoming_id and generate_id_if_missing:
            existing_ids = {
                str(agent.get("agentId") or "").strip()
                for agent in agents
                if isinstance(agent, dict)
            }
            incoming_id = self.generate_agent_id(existing_ids)
        if existing_index is None and not incoming_id:
            raise ValueError("Missing agentId")
        existing = agents[existing_index] if existing_index is not None else None
        record = self.build_agent_record(payload, timestamp, existing, agent_id=incoming_id)
        if existing_index is None:
            agents.append(record)
        else:
            agents[existing_index] = record
        state["updatedAt"] = timestamp
        self.persist_active_agents_state(state)
        return self.load_active_agents_state(), record["agentId"]

    def register_agent(self, board: dict, columns: dict, payload: dict) -> None:
        timestamp = now_iso()
        state, agent_id = self.upsert_agent_record(payload, timestamp, generate_id_if_missing=True)
        agent_record = next(
            (
                agent
                for agent in state.get("agents", [])
                if isinstance(agent, dict) and str(agent.get("agentId", "")) == agent_id
            ),
            {},
        )
        response = dict(state)
        response["agentId"] = agent_id
        response["agent"] = agent_record
        response["agentName"] = agent_record.get("personalName") or agent_record.get("agentName") or ""
        response["taskIds"] = [str(payload.get("currentTaskId", "") or "").strip()] if payload.get("currentTaskId") else []
        return response

    def heartbeat_agent(self, board: dict, columns: dict, payload: dict) -> None:
        if not self.agent_id(payload):
            raise ValueError("Missing agentId")
        timestamp = now_iso()
        state, agent_id = self.upsert_agent_record(payload, timestamp)
        response = dict(state)
        response["agentId"] = agent_id
        response["agentName"] = self.agent_name(payload, "")
        response["taskIds"] = [str(payload.get("currentTaskId", "") or "").strip()] if payload.get("currentTaskId") else []
        return response

    def unregister_agent(self, board: dict, columns: dict, payload: dict) -> None:
        agent_id = self.agent_id(payload)
        if not agent_id:
            raise ValueError("Missing agentId")
        timestamp = now_iso()
        state = self.load_active_agents_state()
        agents = state.get("agents")
        if not isinstance(agents, list):
            agents = []
        state["agents"] = [
            agent
            for agent in agents
            if not (isinstance(agent, dict) and str(agent.get("agentId", "")).strip() == agent_id)
        ]
        state["updatedAt"] = timestamp
        self.persist_active_agents_state(state)
        return {"agentId": agent_id, "taskIds": []}

    def add_task(self, board: dict, columns: dict, payload: dict) -> None:
        todo = self.ensure_column(columns, "todo")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Planning Agent")
        task = self.build_new_task(board, columns, payload, timestamp)
        self.record_task_api_action(task, "add-task", agent_name, timestamp)
        self.record_board_api_action(board, "add-task", agent_name, timestamp, task.get("id", ""))
        self.update_board_timestamp(board, timestamp)
        todo.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task.get("id", "")]}

    def update_task(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        _, _, _, task = self.find_task_location(columns, task_id)
        updates = payload.get("updates")
        if updates is None:
            updates = {
                key: value
                for key, value in payload.items()
                if key not in {"taskId", "agent", "agentName", "updatedBy", "notesAppend"}
            }
        if not isinstance(updates, dict):
            raise ValueError("updates must be an object")

        allowed_fields = {
            "title",
            "project",
            "priority",
            "type",
            "requestedBy",
            "createdBy",
            "createdAt",
            "summary",
            "requirements",
            "acceptanceCriteria",
            "dependsOn",
            "relatedTaskIds",
            "files",
            "referenceImages",
            "inspectionTargets",
            "blockers",
            "sourceReviewTaskId",
            "failureExpected",
            "failureActual",
            "failureDecision",
            "failureBrief",
            "notes",
            "redoCount",
        }
        list_fields = {
            "requirements",
            "acceptanceCriteria",
            "dependsOn",
            "relatedTaskIds",
            "files",
            "referenceImages",
            "inspectionTargets",
            "blockers",
        }

        for field, value in updates.items():
            if field in {"id", "status"}:
                raise ValueError(f"{field} cannot be changed through /api/update-task")
            if field not in allowed_fields:
                raise ValueError(f"{field} is not an allowed task update field")
            if field in list_fields:
                task[field] = self.normalize_list(value, field)
            elif field == "redoCount":
                task[field] = self.normalize_int(value, int(task.get("redoCount") or 0), "redoCount")
            elif field == "title":
                title = self.clean_title(value)
                if not title:
                    raise ValueError("Task title cannot be blank")
                if title.lower().startswith("untitled"):
                    raise ValueError("Task title cannot be Untitled")
                task[field] = title
            elif field == "failureBrief":
                if not isinstance(value, dict):
                    raise ValueError("failureBrief must be an object")
                task[field] = {
                    "expected": self.clean_text(value.get("expected")),
                    "actual": self.clean_text(value.get("actual")),
                    "decision": self.clean_text(value.get("decision")),
                }
            else:
                task[field] = value

        self.validate_depends_on(task_id, task.get("dependsOn"), columns)

        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Task board API")
        self.append_note(task, str(payload.get("notesAppend", "") or ""))
        task["lastEditedBy"] = payload.get("updatedBy") or agent_name
        task["lastEditedAt"] = timestamp
        self.record_task_api_action(task, "update-task", agent_name, timestamp)
        self.record_board_api_action(board, "update-task", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def delete_task(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        agent_name = self.agent_name(payload, "Task board API")
        requested_column = str(payload.get("column", "")).strip()
        if requested_column:
            self.pop_task(columns, requested_column, task_id)
        else:
            _, column, task_index, _ = self.find_task_location(columns, task_id)
            column.pop(task_index)

        timestamp = now_iso()
        self.record_board_api_action(board, "delete-task", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def archive_task(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        task = self.pop_task(columns, "done", task_id)
        archived = self.ensure_column(columns, "archived")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Task board viewer")
        task["status"] = "archived"
        task["archivedAt"] = timestamp
        task["archivedBy"] = payload.get("archivedBy") or agent_name
        self.record_task_api_action(task, "archive", agent_name, timestamp)
        self.record_board_api_action(board, "archive", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        archived.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def return_task_to_review(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        feedback = str(payload.get("feedback", "")).strip()
        if not feedback:
            raise ValueError("Missing feedback")

        task = self.pop_task(columns, "done", task_id)
        review = self.ensure_column(columns, "review")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Task board viewer")
        feedback_entry = {
            "feedback": feedback,
            "returnedBy": payload.get("returnedBy") or agent_name,
            "returnedAt": timestamp,
        }
        existing_feedback = task.get("ownerFeedback")
        if isinstance(existing_feedback, list):
            existing_feedback.append(feedback_entry)
        else:
            task["ownerFeedback"] = [feedback_entry]

        task["status"] = "review"
        task["reviewRequestedAt"] = timestamp
        task["reviewDecision"] = "feedback_requested"
        task["returnedToReviewAt"] = timestamp
        task["returnedToReviewBy"] = feedback_entry["returnedBy"]
        task["doneAt"] = ""
        task["reviewedAt"] = ""
        task["reviewedBy"] = ""
        task["reviewClaimedAt"] = ""
        task["reviewClaimedBy"] = ""
        self.append_note(task, f"Owner feedback for re-review ({timestamp}): {feedback}")
        self.record_task_api_action(task, "return-to-review", agent_name, timestamp)
        self.record_board_api_action(board, "return-to-review", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        review.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def claim_task(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        self.require_not_paused("claim-task")
        task = self.pop_task(columns, "todo", task_id)
        claimed = self.ensure_column(columns, "claimed")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Worker Agent")
        task["status"] = "claimed"
        task["claimedBy"] = payload.get("claimedBy") or agent_name
        task["claimedAt"] = timestamp
        self.append_note(task, str(payload.get("notes", "") or ""))
        self.record_task_api_action(task, "claim-task", agent_name, timestamp)
        self.record_board_api_action(board, "claim-task", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        claimed.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def unclaim_task(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Task board viewer")
        reason = str(payload.get("reason", "") or "").strip() or "Claim released because the worker agent stopped before finishing."

        reviewing_column = self.ensure_column(columns, "reviewing")
        in_reviewing = any(
            isinstance(t, dict) and t.get("id") == task_id for t in reviewing_column
        )

        if in_reviewing:
            task = self.pop_task(columns, "reviewing", task_id)
            review = self.ensure_column(columns, "review")
            task["status"] = "review"
            task["reviewClaimedBy"] = ""
            task["reviewClaimedAt"] = ""
            task["unclaimedBy"] = payload.get("unclaimedBy") or agent_name
            task["unclaimedAt"] = timestamp
            self.append_note(task, f"Unclaimed from reviewing ({timestamp}) by {task['unclaimedBy']}: {reason}")
            self.record_task_api_action(task, "unclaim-task", agent_name, timestamp)
            self.record_board_api_action(board, "unclaim-task", agent_name, timestamp, task_id)
            self.clear_active_agents_for_task(task_id, "review", timestamp, reason)
            self.update_board_timestamp(board, timestamp)
            review.insert(0, task)
            self.persist_board(board)
            return {"taskIds": [task_id], "destinationColumn": "review"}

        task = self.pop_task(columns, "claimed", task_id)
        todo = self.ensure_column(columns, "todo")
        task["status"] = "todo"
        task["claimedBy"] = ""
        task["claimedAt"] = ""
        task["unclaimedBy"] = payload.get("unclaimedBy") or agent_name
        task["unclaimedAt"] = timestamp
        self.append_note(task, f"Unclaimed ({timestamp}) by {task['unclaimedBy']}: {reason}")
        self.record_task_api_action(task, "unclaim-task", agent_name, timestamp)
        self.record_board_api_action(board, "unclaim-task", agent_name, timestamp, task_id)
        self.clear_active_agents_for_task(task_id, "worker", timestamp, reason)
        self.update_board_timestamp(board, timestamp)
        todo.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id], "destinationColumn": "todo"}

    def terminate_agent(self, board: dict, columns: dict, payload: dict) -> dict:
        agent_id = str(payload.get("agentId") or "").strip()
        process_id = parse_process_id(payload.get("processId"))
        task_id = str(payload.get("taskId") or "").strip()
        actor = self.agent_name(payload, "Task board viewer")
        reason = str(payload.get("reason") or "").strip() or "Agent terminated by owner via viewer."
        timestamp = now_iso()

        active_state = self.load_active_agents_state()
        agents = active_state.get("agents") if isinstance(active_state.get("agents"), list) else []

        matched_agent = None
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            if agent_id and str(agent.get("agentId") or "").strip() == agent_id:
                matched_agent = agent
                break
            if process_id and str(agent.get("processId") or "").strip() == str(process_id):
                matched_agent = agent
                break

        if matched_agent:
            agent_task_id = str(matched_agent.get("currentTaskId") or "").strip()
            if not task_id and agent_task_id:
                task_id = agent_task_id
            matched_agent["currentTaskId"] = ""
            matched_agent["status"] = "stale"
            existing_notes = str(matched_agent.get("notes", "") or "").strip()
            termination_note = f"Terminated ({timestamp}) by {actor}: {reason}"
            matched_agent["notes"] = f"{existing_notes}\n{termination_note}".strip() if existing_notes else termination_note
            matched_agent["lastHeartbeatAt"] = timestamp
            active_state["updatedAt"] = timestamp
            self.persist_active_agents_state(active_state)

        unclaimed_task_id = ""
        unclaimed_destination = ""
        if task_id:
            try:
                column_name, column, task_index, task = self.find_task_location(columns, task_id)
            except (LookupError, ValueError):
                column_name, column, task_index, task = "", [], -1, {}

            if column_name in {"claimed", "reviewing"} and isinstance(task, dict) and task_index >= 0:
                removed = column.pop(task_index)
                removed["unclaimedBy"] = actor
                removed["unclaimedAt"] = timestamp

                if column_name == "reviewing":
                    destination = self.ensure_column(columns, "review")
                    removed["status"] = "review"
                    removed["reviewClaimedBy"] = ""
                    removed["reviewClaimedAt"] = ""
                    self.append_note(removed, f"Unclaimed from reviewing ({timestamp}) by {actor}: {reason}")
                    self.clear_active_agents_for_task(task_id, "review", timestamp, reason)
                    unclaimed_destination = "review"
                else:
                    destination = self.ensure_column(columns, "todo")
                    removed["status"] = "todo"
                    removed["claimedBy"] = ""
                    removed["claimedAt"] = ""
                    self.append_note(removed, f"Unclaimed ({timestamp}) by {actor}: {reason}")
                    self.clear_active_agents_for_task(task_id, "worker", timestamp, reason)
                    unclaimed_destination = "todo"

                self.record_task_api_action(removed, "unclaim-task", actor, timestamp)
                self.record_board_api_action(board, "unclaim-task", actor, timestamp, task_id)
                self.update_board_timestamp(board, timestamp)
                destination.insert(0, removed)
                self.persist_board(board)
                unclaimed_task_id = task_id

        spawn_terminated = False
        spawn_process_id = 0
        settings = load_dispatch_settings()
        pending = settings.get("pendingSpawns") if isinstance(settings.get("pendingSpawns"), list) else []
        remaining_pending = []
        for spawn in pending:
            if not isinstance(spawn, dict):
                remaining_pending.append(spawn)
                continue
            spawn_pid = parse_process_id(spawn.get("processId"))
            matched_by_process = process_id and spawn_pid == process_id
            matched_by_agent = False
            if agent_id and not matched_by_process:
                spawn_agent_id = str(spawn.get("agentId") or "").strip()
                spawn_name = str(spawn.get("personalName") or "").strip()
                matched_by_agent = spawn_agent_id == agent_id or (
                    matched_agent and str(matched_agent.get("personalName") or "").strip() == spawn_name
                    and self.normalize_agent_role(spawn.get("role")) == self.normalize_agent_role(matched_agent.get("role"))
                )
            if matched_by_process or matched_by_agent:
                process_status = spawned_process_status(spawn)
                if is_live_pending_spawn(spawn, process_status=process_status):
                    result = terminate_spawned_process(spawn, process_status)
                    spawn_terminated = bool(result.get("terminated"))
                    spawn_process_id = parse_process_id(spawn.get("processId"))
                else:
                    spawn_terminated = True
                    spawn_process_id = spawn_pid
                continue
            remaining_pending.append(spawn)
        settings["pendingSpawns"] = remaining_pending
        settings["updatedAt"] = timestamp
        persist_dispatch_settings(settings)

        if not spawn_terminated and not matched_agent and not unclaimed_task_id:
            raise JsonResponseError(
                "No matching agent or process found to terminate.",
                status=404,
            )

        message_parts = []
        if unclaimed_task_id:
            message_parts.append(f"Unclaimed {unclaimed_task_id}")
        if spawn_terminated:
            message_parts.append(f"terminated PID {spawn_process_id}")
        elif matched_agent:
            message_parts.append("marked agent stale")
        return {
            "ok": True,
            "message": "; ".join(message_parts) if message_parts else "Done.",
            "agentId": agent_id or str(matched_agent.get("agentId") or "") if matched_agent else agent_id,
            "processId": spawn_process_id or process_id,
            "unclaimedTaskId": unclaimed_task_id,
            "destinationColumn": unclaimed_destination,
            "terminated": spawn_terminated,
        }

    def move_to_review(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        task = self.pop_task(columns, "claimed", task_id)
        review = self.ensure_column(columns, "review")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Worker Agent")
        task["status"] = "review"
        task["reviewRequestedAt"] = timestamp
        task["completedBy"] = payload.get("completedBy") or agent_name or task.get("claimedBy", "")
        worker_elapsed = compute_elapsed_seconds(task.get("claimedAt", ""), timestamp)
        if worker_elapsed is not None:
            task["workerTimeSeconds"] = worker_elapsed
            task["workerTime"] = format_duration(worker_elapsed)
        worker_tokens = parse_optional_int(payload.get("workerTokens"))
        if worker_tokens is not None:
            task["workerTokens"] = worker_tokens
        self.append_unique_files(task, payload.get("files"))
        if "inspectionTargets" in payload:
            task["inspectionTargets"] = self.normalize_list(payload.get("inspectionTargets"), "inspectionTargets")
        self.append_note(task, str(payload.get("notes", "") or ""))
        self.record_task_api_action(task, "move-to-review", agent_name, timestamp)
        self.record_board_api_action(board, "move-to-review", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        review.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def claim_review(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        self.require_not_paused("claim-review")
        task = self.pop_task(columns, "review", task_id)
        reviewing = self.ensure_column(columns, "reviewing")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Review Agent")
        task["status"] = "reviewing"
        task["reviewClaimedBy"] = payload.get("reviewClaimedBy") or agent_name
        task["reviewClaimedAt"] = timestamp
        self.record_task_api_action(task, "claim-review", agent_name, timestamp)
        self.record_board_api_action(board, "claim-review", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        reviewing.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def task_in_terminal_state(self, columns: dict, task_id: str) -> bool:
        if not task_id:
            return False
        try:
            column_name, _, _, _ = self.find_task_location(columns, task_id)
            return column_name in TASK_TERMINAL_COLUMNS
        except LookupError:
            return False

    def get_unresolved_depends_on(self, columns: dict, task: dict) -> list[str]:
        depends_on = task.get("dependsOn")
        if not isinstance(depends_on, list) or not depends_on:
            return []
        unresolved = []
        for dep_id in depends_on:
            dep_id_str = str(dep_id or "").strip()
            if dep_id_str and not self.task_in_terminal_state(columns, dep_id_str):
                unresolved.append(dep_id_str)
        return unresolved

    def get_derived_blocking_ids(self, columns: dict, task_id: str) -> list[str]:
        blocking = []
        for column_tasks in columns.values():
            if not isinstance(column_tasks, list):
                continue
            for task in column_tasks:
                if not isinstance(task, dict):
                    continue
                other_id = str(task.get("id") or "").strip()
                if not other_id or other_id == task_id:
                    continue
                depends_on = task.get("dependsOn")
                if isinstance(depends_on, list) and task_id in [str(d or "").strip() for d in depends_on]:
                    blocking.append(other_id)
        return blocking

    def select_next_work_candidate(self, columns: dict, source_column: str, age_field: str) -> dict:
        pause_status = active_pause_status()
        if pause_status.get("isPaused"):
            return {"paused": True, "pauseStatus": pause_status}

        column = self.ensure_column(columns, source_column)
        candidates = [t for t in column if isinstance(t, dict) and self.is_valid_task(t)]
        if not candidates:
            return {"candidate": None, "reason": "no-work", "blockedSummary": []}

        def sort_key(task):
            priority = PRIORITY_ORDER.get(str(task.get("priority", "normal")).strip().lower(), 1)
            age_dt = parse_iso_datetime(task.get(age_field) or task.get("createdAt"))
            age_value = age_dt.timestamp() if age_dt else 0
            return (priority, age_value)

        candidates.sort(key=sort_key)

        blocked_summary = []
        for task in candidates:
            blocked_by = self.get_unresolved_depends_on(columns, task)
            if not blocked_by:
                age_dt = parse_iso_datetime(task.get(age_field) or task.get("createdAt"))
                return {
                    "candidate": task,
                    "sourceColumn": source_column,
                    "ageField": age_field,
                    "orderingTimestamp": age_dt.isoformat() if age_dt else None,
                    "blockedByTaskIds": [],
                    "blockingTaskIds": self.get_derived_blocking_ids(columns, str(task.get("id") or "").strip()),
                }
            age_dt = parse_iso_datetime(task.get(age_field) or task.get("createdAt"))
            blocked_summary.append({
                "taskId": str(task.get("id") or "").strip(),
                "title": str(task.get("title") or "").strip(),
                "priority": str(task.get("priority") or "normal").strip(),
                "createdAt": str(task.get("createdAt") or "").strip(),
                "orderingTimestamp": age_dt.isoformat() if age_dt else None,
                "blockedByTaskIds": blocked_by,
            })

        return {"candidate": None, "reason": "all-blocked", "blockedSummary": blocked_summary}

    def build_next_work_response(self, selection: dict) -> dict:
        if selection.get("paused"):
            status = selection["pauseStatus"]
            return paused_error_payload(status) | {
                "action": "next-work",
                "paused": True,
            }

        candidate = selection.get("candidate")
        if not candidate:
            return {
                "eligible": False,
                "reason": selection.get("reason", "no-work"),
                "blockedSummary": selection.get("blockedSummary", []),
            }

        task_id = str(candidate.get("id") or "").strip()
        response = {
            "eligible": True,
            "taskId": task_id,
            "title": str(candidate.get("title") or "").strip(),
            "project": str(candidate.get("project") or "").strip(),
            "priority": str(candidate.get("priority") or "normal").strip(),
            "type": str(candidate.get("type") or "").strip(),
            "status": str(candidate.get("status") or "").strip(),
            "sourceColumn": selection.get("sourceColumn", ""),
            "createdAt": str(candidate.get("createdAt") or "").strip(),
            "detailUrl": f"/api/task-detail?taskId={task_id}",
            "blockedByTaskIds": selection.get("blockedByTaskIds", []),
            "blockingTaskIds": selection.get("blockingTaskIds", []),
        }
        review_requested = str(candidate.get("reviewRequestedAt") or "").strip()
        if review_requested:
            response["reviewRequestedAt"] = review_requested
        ordering_ts = selection.get("orderingTimestamp")
        if ordering_ts:
            response["orderingTimestamp"] = ordering_ts
        return response

    def next_worker_task(self, board: dict, payload: dict) -> dict:
        columns = self.get_columns(board)
        selection = self.select_next_work_candidate(columns, "todo", "createdAt")
        return self.build_next_work_response(selection)

    def next_review_task(self, board: dict, payload: dict) -> dict:
        columns = self.get_columns(board)
        selection = self.select_next_work_candidate(columns, "review", "reviewRequestedAt")
        return self.build_next_work_response(selection)

    def claim_next_worker(self, board: dict, columns: dict, payload: dict) -> dict:
        self.require_not_paused("claim-next-worker")
        selection = self.select_next_work_candidate(columns, "todo", "createdAt")
        candidate = selection.get("candidate")
        if not candidate:
            return self.build_next_work_response(selection) | {"claimed": False}

        task_id = str(candidate.get("id") or "").strip()
        blocked_by = self.get_unresolved_depends_on(columns, candidate)
        if blocked_by:
            return {
                "claimed": False,
                "eligible": False,
                "reason": "dependency-resolved-after-selection",
                "taskId": task_id,
                "blockedByTaskIds": blocked_by,
            }

        task = self.pop_task(columns, "todo", task_id)
        claimed = self.ensure_column(columns, "claimed")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Worker Agent")
        task["status"] = "claimed"
        task["claimedBy"] = payload.get("claimedBy") or agent_name
        task["claimedAt"] = timestamp
        self.record_task_api_action(task, "claim-next-worker", agent_name, timestamp)
        self.record_board_api_action(board, "claim-next-worker", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        claimed.insert(0, task)
        self.persist_board(board)
        response = self.build_next_work_response(selection)
        response["claimed"] = True
        response["claimedAt"] = timestamp
        response["taskIds"] = [task_id]
        return response

    def claim_next_review(self, board: dict, columns: dict, payload: dict) -> dict:
        self.require_not_paused("claim-next-review")
        selection = self.select_next_work_candidate(columns, "review", "reviewRequestedAt")
        candidate = selection.get("candidate")
        if not candidate:
            return self.build_next_work_response(selection) | {"claimed": False}

        task_id = str(candidate.get("id") or "").strip()
        blocked_by = self.get_unresolved_depends_on(columns, candidate)
        if blocked_by:
            return {
                "claimed": False,
                "eligible": False,
                "reason": "dependency-resolved-after-selection",
                "taskId": task_id,
                "blockedByTaskIds": blocked_by,
            }

        task = self.pop_task(columns, "review", task_id)
        reviewing = self.ensure_column(columns, "reviewing")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Review Agent")
        task["status"] = "reviewing"
        task["reviewClaimedBy"] = payload.get("reviewClaimedBy") or agent_name
        task["reviewClaimedAt"] = timestamp
        self.record_task_api_action(task, "claim-next-review", agent_name, timestamp)
        self.record_board_api_action(board, "claim-next-review", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        reviewing.insert(0, task)
        self.persist_board(board)
        response = self.build_next_work_response(selection)
        response["claimed"] = True
        response["reviewClaimedAt"] = timestamp
        response["taskIds"] = [task_id]
        return response

    def validate_depends_on(self, task_id: str, depends_on: object, columns: dict) -> None:
        if not isinstance(depends_on, list) or not depends_on:
            return
        for dep_id in depends_on:
            dep_id_str = str(dep_id or "").strip()
            if not dep_id_str:
                raise ValueError("dependsOn entries must be non-blank task IDs")
            if dep_id_str == task_id:
                raise ValueError(f"Task cannot depend on itself: {task_id}")
            if not self.task_exists(columns, dep_id_str):
                raise ValueError(f"dependsOn references unknown task ID: {dep_id_str}")

    def approve_review(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        task = self.pop_task(columns, "reviewing", task_id)
        done = self.ensure_column(columns, "done")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Review Agent")
        task["status"] = "done"
        task["doneAt"] = timestamp
        task["reviewedBy"] = payload.get("reviewedBy") or agent_name or task.get("reviewClaimedBy", "")
        task["reviewedAt"] = timestamp
        task["reviewDecision"] = "approved"
        reviewer_elapsed = compute_elapsed_seconds(task.get("reviewClaimedAt", ""), timestamp)
        if reviewer_elapsed is not None:
            task["reviewerTimeSeconds"] = reviewer_elapsed
            task["reviewerTime"] = format_duration(reviewer_elapsed)
        reviewer_tokens = parse_optional_int(payload.get("reviewerTokens"))
        if reviewer_tokens is not None:
            task["reviewerTokens"] = reviewer_tokens
        review_notes = str(payload.get("reviewNotes", "") or payload.get("notes", "") or "").strip()
        if review_notes:
            task["reviewNotes"] = review_notes
            self.append_note(task, f"Review approved ({timestamp}): {review_notes}")
        self.record_task_api_action(task, "approve-review", agent_name, timestamp)
        self.record_board_api_action(board, "approve-review", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        done.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id]}

    def request_changes(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        review_notes = str(payload.get("reviewNotes", "") or payload.get("notes", "") or "").strip()
        if not review_notes:
            raise ValueError("Missing reviewNotes")
        failure_expected = self.clean_text(
            payload.get("failureExpected")
            or payload.get("expectedBehavior")
            or payload.get("expected")
        )
        failure_actual = self.clean_text(
            payload.get("failureActual")
            or payload.get("actualBehavior")
            or payload.get("actual")
        )
        failure_decision = self.clean_text(
            payload.get("failureDecision")
            or payload.get("failureReason")
            or payload.get("decision")
            or review_notes
        )

        task = self.pop_task(columns, "reviewing", task_id)
        done = self.ensure_column(columns, "done")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Review Agent")
        reviewer_elapsed = compute_elapsed_seconds(task.get("reviewClaimedAt", ""), timestamp)
        if reviewer_elapsed is not None:
            task["reviewerTimeSeconds"] = reviewer_elapsed
            task["reviewerTime"] = format_duration(reviewer_elapsed)
        reviewer_tokens = parse_optional_int(payload.get("reviewerTokens"))
        if reviewer_tokens is not None:
            task["reviewerTokens"] = reviewer_tokens
        task["status"] = "done"
        task["reviewedBy"] = payload.get("reviewedBy") or agent_name or task.get("reviewClaimedBy", "")
        task["reviewedAt"] = timestamp
        task["reviewDecision"] = "changes_requested"
        task["doneAt"] = timestamp
        task["closedAs"] = "replaced_by_follow_up"
        task["reviewClaimedBy"] = ""
        task["reviewClaimedAt"] = ""
        task["reviewNotes"] = review_notes
        task["failureExpected"] = failure_expected
        task["failureActual"] = failure_actual
        task["failureDecision"] = failure_decision
        task["failureBrief"] = {
            "expected": failure_expected,
            "actual": failure_actual,
            "decision": failure_decision,
        }
        task["redoCount"] = int(task.get("redoCount") or 0) + 1
        self.append_note(task, f"Changes requested ({timestamp}): {review_notes}")

        follow_up = self.upsert_follow_up_task(board, columns, task, payload, timestamp)
        follow_up_id = follow_up.get("id", "")
        task["latestFollowUpTaskId"] = follow_up_id
        task["replacedByTaskId"] = follow_up_id
        self.append_note(task, f"Closed as replaced ({timestamp}): follow-up task {follow_up_id} replaces this failed review task.")
        self.record_task_api_action(task, "request-changes", agent_name, timestamp)
        self.record_board_api_action(board, "request-changes", agent_name, timestamp, task_id)
        self.update_board_timestamp(board, timestamp)
        done.insert(0, task)
        self.persist_board(board)
        return {"taskIds": [task_id, follow_up_id], "followUpTaskId": follow_up_id}

    def spawn_agent(self, board: dict, columns: dict, payload: dict) -> dict:
        del columns
        role = self.normalize_agent_role(payload.get("role"))
        tool = self.normalize_agent_model(payload.get("tool") or payload.get("model"))
        if role not in SPAWNABLE_AGENT_ROLES:
            raise ValueError(f"Unsupported spawn role: {role!r}. Allowed: {sorted(SPAWNABLE_AGENT_ROLES)}")
        if tool not in SPAWNABLE_TOOLS:
            raise ValueError(f"Unsupported spawn tool: {tool!r}. Allowed: {sorted(SPAWNABLE_TOOLS)}")
        self.require_not_paused("spawn-agent")

        explicit_name = str(payload.get("personalName") or "").strip()
        if explicit_name:
            personal_name = explicit_name
        else:
            agents_state = self.load_active_agents_state()
            personal_name = self.pick_personal_name(agents_state.get("agents") or [])
        if not personal_name:
            personal_name = "agent"

        backend_base_url = f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"
        resume_run = payload.get("resumeRun") if isinstance(payload.get("resumeRun"), dict) else None
        start_phrase = self.build_spawn_start_phrase(
            role,
            tool,
            personal_name,
            backend_base_url,
            board,
            resume_run=resume_run,
        )

        working_dir = str(PROJECT_ROOT)
        cli_command_text = self.spawn_command_for_tool(tool)

        SPAWN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", personal_name).strip("-") or "agent"
        run_stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
        log_path = SPAWN_LOG_DIR / f"{run_stamp}-{role}-{tool}-{safe_name}.log"
        env = agent_subprocess_env(tool)

        log_file = log_path.open("a", encoding="utf-8")
        log_file.write(f"Spawned {role} agent ({tool}) at {now_iso()}\n")
        log_file.write(f"Working directory: {working_dir}\n")
        log_file.write(f"Backend: {backend_base_url}\n")
        if resume_run:
            log_file.write(f"Resume of process: {resume_run.get('processId', '')}\n")
            log_file.write(f"Prior log: {resume_run.get('logPath', '')}\n")
        if tool == "codex":
            log_file.write(f"Codex SQLite state: {env.get('CODEX_SQLITE_HOME', '')}\n")
        log_file.write(f"Prompt: {start_phrase}\n\n")
        log_file.flush()

        # Prefer an interactive terminal so the owner can watch and take over.
        try:
            interactive_result = self.spawn_interactive_agent(
                role,
                tool,
                personal_name,
                backend_base_url,
                start_phrase,
                working_dir,
                log_path=log_path,
                resume_run=resume_run,
            )
            log_file.write("Interactive spawn via terminal\n")
            log_file.write(f"Command: {interactive_result.get('terminalCommand', '')}\n")
            log_file.close()
            return interactive_result
        except Exception as exc:
            log_file.write(f"Interactive spawn failed: {exc}\n")
            log_file.close()
            raise RuntimeError(f"Could not open interactive {tool} terminal: {exc}") from exc

    # --- Planner chat (interactive human input to the Planner agent) ---

    PLANNER_CHAT_OUTPUT_MARKER = "===PLANNER-OUTPUT==="

    def _new_chat_id(self) -> str:
        return f"pc_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"

    def load_planner_chat(self) -> dict:
        try:
            data = json.loads(PLANNER_CHAT_SESSION_PATH.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        if not isinstance(data.get("messages"), list):
            data["messages"] = []
        data.setdefault("cliSessionId", "")
        data.setdefault("cliTool", "")
        return data

    def save_planner_chat(self, data: dict) -> None:
        PLANNER_CHAT_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = PLANNER_CHAT_SESSION_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, PLANNER_CHAT_SESSION_PATH)

    def read_planner_chat_output(self, log_path: str, truncate: bool = True) -> str:
        if not log_path:
            return ""
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, OSError):
            return ""
        marker = self.PLANNER_CHAT_OUTPUT_MARKER
        if marker in text:
            text = text.split(marker, 1)[1]
        text = strip_terminal_control_sequences(text)
        text = text.strip()
        if truncate and len(text) > PLANNER_CHAT_OUTPUT_LIMIT:
            text = "...(truncated)...\n" + text[-PLANNER_CHAT_OUTPUT_LIMIT:]
        return text

    def read_text_tail(self, path: str, limit: int = 2000) -> str:
        if not path:
            return ""
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
        except (FileNotFoundError, OSError):
            return ""
        if len(text) > limit:
            text = "...(truncated)...\n" + text[-limit:]
        return text

    def _is_noise_line(self, line: str) -> bool:
        """Check if a line is likely CLI/tool noise, not conversational text."""
        stripped = line.strip()
        if not stripped:
            return False
        noise_prefixes = (
            ">>", "[OK]", "[ERROR]", "[error", "...(truncated)...",
            "   Command:", "   Directory:", "   Path:", "   Pattern:",
            "   Description:", "   Query:", "   URL:", "   Prompt:",
            "   Content (", "   Subagent", "   Todos:", "   Cell:",
            "   Old:", "   New:",
            "--------", "thinking", "model:", "qwen_code_version:",
            "permission_mode:", "session_id:",
            "cost:", "duration:", "input_tokens:", "output_tokens:",
            "--- Process exit status ---", "qwen:", "formatter:",
            "warning:", "warnings:", "OpenAI Codex", "Reading additional input",
            "workdir:", "provider:", "approval:", "sandbox:", "reasoning",
            "session id", "tokens used",
        )
        if any(stripped.startswith(p) for p in noise_prefixes):
            return True
        if stripped in {"user", "assistant", "codex"}:
            return True
        lower = stripped.lower()
        if any(kw in lower for kw in (
            "command:", "directory:", "exit code:", "signal:",
            "process group", "return code", "error:",
            "load as planner", "load as worker", "load as reviewer",
            "your model is", "your personalname", "backendbaseurl",
            "call http", "use this full base url",
            "api/register-agent", "api/add-task", "api/update-task",
            "api/claim-task", "api/heartbeat", "api/move-to-review",
            "api/worker-board", "api/board", "api/task-detail",
            "api/review-board", "api/claim-review", "api/approve-review",
            "api/request-changes", "api/next-worker", "api/next-review",
            "api/duplicate-scan", "api/agents",
        )):
            return True
        if stripped.startswith("{") or stripped.endswith("}"):
            return True
        if stripped.startswith("[") and stripped.endswith("]"):
            return True
        if re.match(r'^\s{3,}\S', line) and not stripped.startswith(('-', '*', '#')):
            return True
        return False

    def _is_doc_heavy_section(self, section: str) -> bool:
        """Check if a section is mostly documentation/role content, not conversational."""
        lines = section.split("\n")
        if not lines:
            return True
        doc_indicators = 0
        total_non_empty = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            total_non_empty += 1
            # Markdown headers
            if re.match(r'^#{1,6}\s', stripped):
                doc_indicators += 1
            # Code fence markers
            elif stripped.startswith("```"):
                doc_indicators += 1
            # JSON-like structures
            elif stripped.startswith("{") or stripped.startswith("["):
                doc_indicators += 1
            # API endpoint patterns
            elif re.search(r'(GET|POST|PUT|DELETE|PATCH)\s+/\w+', stripped):
                doc_indicators += 1
            # curl/Invoke-RestMethod examples
            elif stripped.startswith("curl ") or stripped.startswith("Invoke-"):
                doc_indicators += 1
            # Rule/list numbering patterns (1. 2. 3. etc.)
            elif re.match(r'^\d+\.\s', stripped):
                doc_indicators += 1
            # Field definition patterns (key: value or "key":)
            elif re.match(r'^"?[\w_]+"?\s*:', stripped):
                doc_indicators += 1
        if total_non_empty == 0:
            return True
        # If more than 40% of lines look like documentation, treat as doc-heavy
        return doc_indicators / total_non_empty > 0.4

    def _extract_clean_reply(self, text: str) -> str:
        """Extract the final conversational reply from formatted CLI output.

        Strips tool invocations, tool results, thinking blocks, init
        metadata, cost/stats lines, role documentation, and other CLI noise.
        Returns only the last substantial assistant text block.
        """
        if not text:
            return ""
        if text.startswith("...(truncated)..."):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        # Split into sections at tool invocation boundaries.
        # When the formatter's result event is found, stop — everything after
        # is cost/stats metadata, not conversational text.
        sections = []
        current: list[str] = []
        result_fallback = ""
        result_fallback_lines: list[str] = []
        found_result = False
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(">> ") and len(stripped) > 3:
                if current:
                    sections.append("\n".join(current))
                    current = []
                continue
            if not found_result and re.match(r'^result \(\w+\)\s*$', stripped):
                if current:
                    sections.append("\n".join(current))
                    current = []
                found_result = True
                continue
            if found_result:
                # Capture lines after result marker as the primary reply candidate.
                # Stop before Qwen formatter/process status, then skip trailing
                # metadata lines like [duration: ...], cost:, return codes, etc.
                if re.match(r'^-{3,}\s*process exit status\s*-{3,}$', stripped, re.IGNORECASE):
                    break
                if stripped and not self._is_noise_line(line):
                    result_fallback_lines.append(line)
                continue
            current.append(line)
        if current:
            sections.append("\n".join(current))
        # Build result_fallback from captured lines after result marker.
        if result_fallback_lines:
            result_fallback = "\n".join(result_fallback_lines).strip()
        # Filter each section: remove noise lines, keep clean lines.
        clean_sections: list[str] = []
        for section in sections:
            clean_lines: list[str] = []
            in_code_fence = False
            for line in section.split("\n"):
                stripped = line.strip()
                if stripped.startswith("```"):
                    in_code_fence = not in_code_fence
                    continue
                if in_code_fence:
                    continue
                if self._is_noise_line(line):
                    continue
                clean_lines.append(line)
            clean = "\n".join(clean_lines).strip()
            if len(clean) > 20:
                clean_sections.append(clean)
        # Priority 1: Use text after result (success) marker if substantial.
        # This is the Planner's actual conversational reply.
        if result_fallback and len(result_fallback) > 10:
            rf_lines = [l for l in result_fallback.split("\n") if l.strip()]
            if rf_lines and not all(re.match(r'^[\[\s]*$', l.strip()) or l.strip().startswith("cost:") or l.strip().startswith("duration:") for l in rf_lines):
                return result_fallback[:3000]
        # Priority 2: Last clean section that isn't doc-heavy.
        for section in reversed(clean_sections):
            if self._is_doc_heavy_section(section):
                continue
            words = section.split()
            if len(words) >= 5:
                return section[:3000]
        # Priority 3: Any clean section with enough words.
        for section in reversed(clean_sections):
            words = section.split()
            if len(words) >= 5:
                return section[:3000]
        # Priority 4: result_fallback if it exists.
        if result_fallback and len(result_fallback) > 10:
            return result_fallback[:3000]
        # Last resort: truncated raw text.
        return text.strip()[:3000]

    def extract_planner_reply(self, message: dict, data: dict) -> None:
        """Called once a planner turn finishes. Parses the CLI output into a clean
        reply and, for Claude JSON turns, captures the resumable session id.

        Sets message['output'] to the full raw output (for diagnostics)
        and message['result'] to the clean conversational reply (for the
        default chat bubble).
        """
        log_path = str(message.get("logPath") or "")
        if message.get("format") == "json":
            raw = self.read_planner_chat_output(log_path, truncate=False)
            parsed = None
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
            if isinstance(parsed, dict):
                reply = parsed.get("result")
                if not isinstance(reply, str) or not reply.strip():
                    reply = json.dumps(parsed, indent=2)
                message["output"] = reply.strip()
                message["result"] = reply.strip()
                if parsed.get("is_error"):
                    message["isError"] = True
                session_id = parsed.get("session_id")
                if isinstance(session_id, str) and session_id and message.get("tool") == "claude":
                    data["cliSessionId"] = session_id
                    data["cliTool"] = "claude"
            else:
                # CLI did not return parseable JSON (e.g. not logged in, crash).
                err_tail = self.read_text_tail(str(message.get("errPath") or ""))
                pieces = [p for p in [raw, ("[error output]\n" + err_tail) if err_tail else ""] if p]
                message["output"] = ("\n\n".join(pieces)).strip() or "(no output captured)"
                message["result"] = self._extract_clean_reply(raw) if raw else ""
                if not message["result"]:
                    message["result"] = "Planner run did not produce a reply. Check diagnostics for details."
                message["isError"] = True
        else:
            raw_output = self.read_planner_chat_output(log_path, truncate=False)
            message["output"] = raw_output[:PLANNER_CHAT_OUTPUT_LIMIT] if len(raw_output) > PLANNER_CHAT_OUTPUT_LIMIT else raw_output
            message["result"] = self._extract_clean_reply(raw_output)
            if not message["result"]:
                message["result"] = "Planner run did not produce a reply. Check diagnostics for details."

    def refresh_planner_chat(self, data: dict) -> bool:
        changed = False
        for message in data.get("messages", []):
            if not isinstance(message, dict) or message.get("role") != "planner":
                continue
            if message.get("status") != "running":
                continue
            # Text-mode turns can stream partial output while still running.
            if message.get("format") != "json":
                output = self.read_planner_chat_output(str(message.get("logPath") or ""))
                if output != message.get("output"):
                    message["output"] = output
                    changed = True
            terminal_done_path = str(message.get("terminalDonePath") or "")
            terminal_done = bool(terminal_done_path and Path(terminal_done_path).exists())
            terminal_info = message.get("terminalInfo") if isinstance(message.get("terminalInfo"), dict) else {}
            status = spawned_process_status({
                "processId": message.get("processId"),
                "spawnedAt": message.get("spawnedAt"),
                "mode": "interactive" if str(terminal_info.get("mode") or "") == "interactive-terminal" else "",
            })
            if terminal_done or not status.get("isRunning"):
                self.extract_planner_reply(message, data)
                message["status"] = "done"
                message["finishedAt"] = now_iso()
                message["processState"] = status.get("state", "")
                changed = True
        return changed

    def planner_chat_poll(self, board: dict, payload: dict) -> dict:
        del board, payload
        with PLANNER_CHAT_LOCK:
            data = self.load_planner_chat()
            if self.refresh_planner_chat(data):
                self.save_planner_chat(data)
            return {"messages": data.get("messages", [])}

    def planner_chat_clear(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns, payload
        with PLANNER_CHAT_LOCK:
            self.save_planner_chat({"messages": []})
            return {"messages": []}

    def build_planner_chat_history(self, messages: list, max_chars: int = 3000) -> str:
        """Build a concise history string from prior planner chat messages.

        Returns a compact multi-line summary of completed owner/planner turns,
        truncated to *max_chars* so the prompt stays within a reasonable budget.
        Returns an empty string when there is no usable history.
        """
        lines: list[str] = []
        total = 0
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role == "owner":
                text = str(msg.get("text") or "").strip()
                if text:
                    line = f"Owner: {text}"
                    if total + len(line) > max_chars:
                        break
                    lines.append(line)
                    total += len(line)
            elif role == "planner" and msg.get("status") not in ("running",):
                reply = str(msg.get("result") or "").strip()
                if reply:
                    line = f"Planner: {reply}"
                    if total + len(line) > max_chars:
                        break
                    lines.append(line)
                    total += len(line)
        return "\n".join(lines)

    def build_planner_chat_phrase(self, message: str, backend_base_url: str) -> str:
        """First turn of a conversation: load the planner role and answer the owner."""
        return (
            "load as planner and start; your model is planner-chat; "
            f"backendBaseUrl is {backend_base_url}; use this full base URL for every task-board API call; "
            f"call {backend_base_url}/api/register-agent with personalName, model, role to receive your agentId. "
            "You are in an ongoing back-and-forth chat with the owner through the planner chat window. "
            "Reply conversationally and concisely; ask clarifying questions when useful. "
            "Record and decompose agreed work into deduplicated todo tasks per your planner rules; do not implement or review. "
            "The owner will keep replying in this same conversation, so keep your earlier context in mind. "
            "Owner says:\n" + message
        )

    def planner_chat_send(self, board: dict, columns: dict, payload: dict) -> dict:
        del board, columns
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ValueError("Planner chat message must not be blank")

        settings = load_dispatch_settings()
        planner_settings = settings.get("planner") if isinstance(settings.get("planner"), dict) else {}
        saved_tool = normalize_dispatch_model(planner_settings.get("model"), DEFAULT_PLANNER_MODEL)
        requested_tool = str(payload.get("tool") or payload.get("model") or saved_tool).strip().lower()
        tool = requested_tool if requested_tool in SPAWNABLE_TOOLS else saved_tool
        if tool != saved_tool:
            settings["planner"] = {"model": tool}
            settings["updatedAt"] = now_iso()
            persist_dispatch_settings(settings)

        # Read conversation state and block overlapping turns up front.
        with PLANNER_CHAT_LOCK:
            data = self.load_planner_chat()
            # Refresh first so a turn whose process already exited is not seen as running.
            if self.refresh_planner_chat(data):
                self.save_planner_chat(data)
            for existing in data.get("messages", []):
                if isinstance(existing, dict) and existing.get("role") == "planner" and existing.get("status") == "running":
                    raise ValueError("The Planner is still responding to the previous message. Wait for it to finish.")
            cli_session_id = str(data.get("cliSessionId") or "")

        # Conversation memory currently works through Claude's resumable sessions.
        continuing = bool(cli_session_id) and tool == "claude"

        backend_base_url = f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"
        if continuing:
            phrase = message  # resumed session already holds the planner context
        else:
            phrase = self.build_planner_chat_phrase(message, backend_base_url)
            history = self.build_planner_chat_history(data.get("messages", []))
            if history:
                phrase = phrase.replace(
                    "Owner says:\n" + message,
                    "Prior conversation history:\n" + history + "\n\nOwner now says:\n" + message,
                )

        command_override = payload.get("command") if "command" in payload else None
        args = self.interactive_spawn_command_args(tool, phrase, command_override=command_override)
        chat_format = "text"

        message_id = self._new_chat_id()
        spawned_at = now_iso()
        working_dir = str(PROJECT_ROOT)
        err_path = ""
        terminal_info: dict = {}
        try:
            PLANNER_CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = PLANNER_CHAT_LOG_DIR / f"{message_id}-{tool}.log"
            log_file = log_path.open("a", encoding="utf-8")
            log_file.write(f"Planner chat ({tool}) at {spawned_at}\n")
            log_file.write(f"Working directory: {working_dir}\n")
            log_file.write(f"Backend: {backend_base_url}\n")
            log_file.write(f"Resuming session: {cli_session_id or '(new conversation)'}\n")
            log_file.write(f"{self.PLANNER_CHAT_OUTPUT_MARKER}\n")
            log_file.flush()
            log_file.close()
            done_path = str(PLANNER_CHAT_LOG_DIR / f"{message_id}-{tool}.done")
            try:
                Path(done_path).unlink()
            except (FileNotFoundError, OSError):
                pass
            process, terminal_info, _, _ = self.launch_recorded_interactive_terminal(
                args,
                working_dir,
                tool,
                str(log_path),
                done_path,
                f"Planner Chat {tool}",
            )
        except FileNotFoundError as error:
            raise RuntimeError(f"Could not launch planner chat ({tool}): {error}") from error
        except Exception as error:
            raise RuntimeError(f"Planner chat send failed: {error}") from error

        with PLANNER_CHAT_LOCK:
            data = self.load_planner_chat()
            data["messages"].append({
                "id": self._new_chat_id(),
                "role": "owner",
                "text": message,
                "createdAt": spawned_at,
            })
            data["messages"].append({
                "id": message_id,
                "role": "planner",
                "tool": tool,
                "format": chat_format,
                "status": "running",
                "processId": process.pid,
                "spawnedAt": spawned_at,
                "logPath": str(log_path),
                "errPath": err_path,
                "terminalInfo": terminal_info,
                "terminalDonePath": done_path,
                "resumedSession": cli_session_id if continuing else "",
                "output": "",
                "createdAt": spawned_at,
                "finishedAt": "",
            })
            self.save_planner_chat(data)
            messages = data.get("messages", [])

        return {
            "sent": True,
            "messageId": message_id,
            "tool": tool,
            "continuing": continuing,
            "processId": process.pid,
            "logPath": str(log_path),
            "terminalInfo": terminal_info,
            "backendBaseUrl": backend_base_url,
            "messages": messages,
        }

    def persist_board(self, board: dict) -> None:
        try:
            with BOARD_LOCK:
                self.normalize_board_columns(board)
                temp_path = BOARD_PATH.with_suffix(".json.tmp")
                temp_path.write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
                os.replace(temp_path, BOARD_PATH)
        except Exception as error:
            raise RuntimeError(f"Unable to persist board: {error}") from error

    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return


def load_dispatch_board() -> dict:
    with BOARD_LOCK:
        board = json.loads(BOARD_PATH.read_text(encoding="utf-8-sig"))
        columns = board.get("columns")
        if not isinstance(columns, dict):
            board["columns"] = {}
        return board


def load_dispatch_active_agents() -> list[dict]:
    with ACTIVE_AGENTS_LOCK:
        if not ACTIVE_AGENTS_PATH.exists():
            return []
        try:
            state = json.loads(ACTIVE_AGENTS_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return []
    agents = state.get("agents") if isinstance(state, dict) else []
    return agents if isinstance(agents, list) else []


def load_personal_name_pool() -> list[str]:
    try:
        schema = json.loads(AGENT_SCHEMA_PATH.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        schema = {}
    pool = schema.get("personalNamePool") if isinstance(schema, dict) else []
    return [str(name).strip().lower() for name in pool if str(name).strip()]


def append_dispatch_log(entry: dict) -> None:
    try:
        entry.setdefault("at", now_iso())
        entry.setdefault("method", "AUTO")
        entry.setdefault("path", "/viewer/auto-dispatch")
        entry.setdefault("agentName", "Auto dispatcher")
        entry.setdefault("taskIds", [])
        entry["taskId"] = entry["taskIds"][0] if len(entry["taskIds"]) == 1 else ""
        with VIEWER_LOG_LOCK:
            with VIEWER_LOG_PATH.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        return


def active_agent_count(agents: list[dict], role: str, now: datetime) -> int:
    return sum(1 for agent in agents if is_active_agent_record(agent, role, now))


def work_count_for_role(board: dict, role: str) -> int:
    columns = board.get("columns") if isinstance(board, dict) else {}
    if not isinstance(columns, dict):
        return 0
    column_name = "todo" if role == "worker" else "review"
    tasks = columns.get(column_name)
    return len(tasks) if isinstance(tasks, list) else 0


def clean_pending_spawns(settings: dict, now: datetime) -> list[dict]:
    pending = settings.get("pendingSpawns")
    if not isinstance(pending, list):
        pending = []
    cleaned = [
        spawn
        for spawn in pending
        if is_live_pending_spawn(spawn)
    ]
    settings["pendingSpawns"] = cleaned
    return cleaned


def choose_auto_personal_name(role: str, agents: list[dict], pending: list[dict]) -> str:
    used = {
        str(agent.get("personalName") or agent.get("agentName") or "").strip().lower()
        for agent in agents
        if isinstance(agent, dict)
    }
    used.update(
        str(spawn.get("personalName") or "").strip().lower()
        for spawn in pending
        if isinstance(spawn, dict)
    )
    for name in load_personal_name_pool():
        if name and name not in used:
            return name
    return f"{role}{secrets.token_hex(2)}"


def spawn_via_viewer_endpoint(
    server: ThreadingHTTPServer,
    role: str,
    model: str,
    personal_name: str,
    resume_run: dict | None = None,
) -> dict:
    host, port = server.server_address
    url = f"http://{host}:{port}/viewer/spawn-agent"
    payload = {
        "role": role,
        "tool": model,
        "personalName": personal_name,
        "agentName": "Auto dispatcher",
        "spawnReason": "resume-paused-run" if isinstance(resume_run, dict) else "auto-dispatch",
    }
    if isinstance(resume_run, dict):
        payload["resumeRun"] = resume_run
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def paused_run_is_waiting(run: object) -> bool:
    if not isinstance(run, dict):
        return False
    role = str(run.get("role") or "").strip().lower()
    model = str(run.get("model") or "").strip().lower()
    personal_name = str(run.get("personalName") or "").strip()
    if role not in SPAWNABLE_AGENT_ROLES or model not in SPAWNABLE_TOOLS or not personal_name:
        return False
    resume_state = str(run.get("resumeState") or "waiting").strip().lower()
    if resume_state not in PAUSED_RUN_RETRYABLE_STATES:
        return False
    if run.get("resumeReady") is False:
        return False
    return True


def resume_paused_runs(
    server: ThreadingHTTPServer,
    settings: dict,
    pending: list[dict],
    now: datetime,
) -> bool:
    paused_runs = settings.get("pausedRuns")
    if not isinstance(paused_runs, list):
        paused_runs = []
        settings["pausedRuns"] = paused_runs
    changed = False
    for run in paused_runs:
        if not paused_run_is_waiting(run):
            continue
        role = str(run.get("role") or "").strip().lower()
        model = normalize_dispatch_model(run.get("model"), "codex")
        personal_name = str(run.get("personalName") or "").strip()
        attempt_at = now_iso()
        run["lastResumeAttemptAt"] = attempt_at
        try:
            result = spawn_via_viewer_endpoint(server, role, model, personal_name, resume_run=run)
            pending_entry = {
                "role": role,
                "model": model,
                "personalName": personal_name,
                "spawnedAt": now_iso(),
                "mode": result.get("mode", ""),
                "processId": result.get("processId", ""),
                "logPath": result.get("logPath", ""),
                "resumeOfProcessId": run.get("processId", ""),
                "resumeOfLogPath": run.get("logPath", ""),
            }
            pending.append(pending_entry)
            run["resumeState"] = "resumed"
            run["resumedAt"] = pending_entry["spawnedAt"]
            run["resumedProcessId"] = result.get("processId", "")
            run["resumedLogPath"] = result.get("logPath", "")
            run["lastResumeError"] = ""
            run["lastResumeFailedAt"] = ""
            settings["pendingSpawns"] = pending
            changed = True
            append_dispatch_log({
                "action": "resume-paused-run",
                "status": "success",
                "httpStatus": 200,
                "role": role,
                "model": model,
                "personalName": personal_name,
                "processId": result.get("processId", ""),
                "taskIds": [str(run.get("currentTaskId") or "").strip()] if run.get("currentTaskId") else [],
                "error": "",
            })
        except Exception as error:
            run["resumeState"] = "resume-failed"
            run["lastResumeError"] = str(error)
            run["lastResumeFailedAt"] = now_iso()
            changed = True
            append_dispatch_log({
                "action": "resume-paused-run",
                "status": "error",
                "httpStatus": 500,
                "role": role,
                "model": model,
                "personalName": personal_name,
                "taskIds": [str(run.get("currentTaskId") or "").strip()] if run.get("currentTaskId") else [],
                "error": str(error),
            })
    if changed:
        settings["pausedRuns"] = paused_runs
    return changed


def run_auto_dispatch_once(server: ThreadingHTTPServer) -> None:
    now = datetime.now(timezone.utc).astimezone()
    settings = load_dispatch_settings()
    board = load_dispatch_board()
    agents = load_dispatch_active_agents()
    original_pending = settings.get("pendingSpawns")
    original_pending_text = json.dumps(original_pending if isinstance(original_pending, list) else [], sort_keys=True, separators=(",", ":"))
    pending = clean_pending_spawns(settings, now)
    cleaned_pending_text = json.dumps(pending, sort_keys=True, separators=(",", ":"))
    changed_settings = cleaned_pending_text != original_pending_text

    if pause_status_from_settings(settings, now=now).get("isPaused"):
        if changed_settings:
            settings["updatedAt"] = now_iso()
            persist_dispatch_settings(settings)
        return

    if resume_paused_runs(server, settings, pending, now):
        changed_settings = True

    for role in ("worker", "review"):
        role_settings = settings.get(role, {})
        if not role_settings.get("enabled"):
            continue
        max_agents = normalize_max_agents(role_settings.get("maxAgents"), 1)
        if max_agents <= 0:
            continue
        available_work = work_count_for_role(board, role)
        if available_work <= 0:
            continue
        model = normalize_dispatch_model(role_settings.get("model"), "codex")
        active_count = active_agent_count(agents, role, now)
        pending_count = sum(1 for spawn in pending if is_recent_spawn(spawn, role, now))
        spawn_count = min(available_work, max_agents - active_count - pending_count)
        for _ in range(max(0, spawn_count)):
            personal_name = choose_auto_personal_name(role, agents, pending)
            try:
                result = spawn_via_viewer_endpoint(server, role, model, personal_name)
                pending_entry = {
                    "role": role,
                    "model": model,
                    "personalName": personal_name,
                    "spawnedAt": now_iso(),
                    "mode": result.get("mode", ""),
                    "processId": result.get("processId", ""),
                    "logPath": result.get("logPath", ""),
                }
                pending.append(pending_entry)
                settings["pendingSpawns"] = pending
                changed_settings = True
                append_dispatch_log({
                    "action": "auto-spawn",
                    "status": "success",
                    "httpStatus": 200,
                    "role": role,
                    "model": model,
                    "personalName": personal_name,
                    "processId": result.get("processId", ""),
                    "taskIds": [],
                    "error": "",
                })
            except Exception as error:
                append_dispatch_log({
                    "action": "auto-spawn",
                    "status": "error",
                    "httpStatus": 500,
                    "role": role,
                    "model": model,
                    "personalName": personal_name,
                    "taskIds": [],
                    "error": str(error),
                })

    if changed_settings:
        settings["updatedAt"] = now_iso()
        persist_dispatch_settings(settings)


def auto_dispatch_loop(server: ThreadingHTTPServer) -> None:
    consecutive_errors = 0
    while True:
        sleep_seconds = AUTO_DISPATCH_INTERVAL_SECONDS
        if consecutive_errors:
            sleep_seconds = min(60, AUTO_DISPATCH_INTERVAL_SECONDS * (2 ** min(consecutive_errors, 4)))
        time.sleep(sleep_seconds)
        try:
            run_auto_dispatch_once(server)
            consecutive_errors = 0
        except Exception as error:
            consecutive_errors += 1
            append_dispatch_log({
                "action": "auto-dispatch-loop",
                "status": "error",
                "httpStatus": 500,
                "error": str(error),
                "consecutiveErrors": consecutive_errors,
                "nextRetrySeconds": min(60, AUTO_DISPATCH_INTERVAL_SECONDS * (2 ** min(consecutive_errors, 4))),
            })


def main() -> None:
    os.chdir(ROOT)
    server = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), TaskBoardHandler)
    dispatch_thread = threading.Thread(target=auto_dispatch_loop, args=(server,), daemon=True)
    dispatch_thread.start()
    print(f"{BOARD_TITLE}: serving at http://{SERVER_HOST}:{SERVER_PORT}/viewer.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
