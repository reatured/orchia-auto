from __future__ import annotations

import json
import os
import re
import secrets
import signal
import shlex
import shutil
import subprocess
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
API_LOG_LOCK = threading.Lock()
VIEWER_LOG_LOCK = threading.Lock()
ACTIVE_AGENTS_LOCK = threading.Lock()
DISPATCH_SETTINGS_LOCK = threading.Lock()
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
    "/api/pause": "get_pause_status",
    "/api/pause-status": "get_pause_status",
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
    "/viewer/dispatch-settings": "get_dispatch_settings",
    "/viewer/pause": "get_pause_status",
    "/viewer/pause-status": "get_pause_status",
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
    "/api/agent-health-check": "agent_health_check",
    "/api/hard-stop": "hard_stop_spawned_agents",
    "/api/hard-stop-spawned-agents": "hard_stop_spawned_agents",
    "/api/pause": "pause_plus_one_hour",
    "/api/pause-plus-one-hour": "pause_plus_one_hour",
    "/api/resume-now": "resume_now",
}
VIEWER_POST_ACTIONS = {
    "/viewer/archive": "archive_task",
    "/viewer/return-to-review": "return_task_to_review",
    "/viewer/unclaim-task": "unclaim_task",
    "/viewer/spawn-agent": "spawn_agent",
    "/viewer/agent-health-check": "agent_health_check",
    "/viewer/dispatch-settings": "update_dispatch_settings",
    "/viewer/hard-stop": "hard_stop_spawned_agents",
    "/viewer/hard-stop-spawned-agents": "hard_stop_spawned_agents",
    "/viewer/pause": "pause_plus_one_hour",
    "/viewer/pause-plus-one-hour": "pause_plus_one_hour",
    "/viewer/resume-now": "resume_now",
}
SPAWNABLE_AGENT_ROLES = {"worker", "review"}
SPAWNABLE_TOOLS = {"claude", "codex"}
BOARD_COLUMN_ORDER = ["todo", "claimed", "review", "reviewing", "done", "archived"]
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


def default_dispatch_settings() -> dict:
    return {
        "version": 1,
        "updatedAt": "",
        "commands": {
            "claude": CLAUDE_COMMAND,
            "codex": CODEX_COMMAND,
        },
        "worker": {
            "enabled": False,
            "model": "codex",
            "maxAgents": 1,
        },
        "review": {
            "enabled": False,
            "model": "codex",
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


def normalize_dispatch_model(value: object, fallback: str = "codex") -> str:
    model = str(value or "").strip().lower()
    if model in SPAWNABLE_TOOLS:
        return model
    return fallback if fallback in SPAWNABLE_TOOLS else "codex"


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
    return env


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


def persist_dispatch_settings(settings: dict) -> None:
    normalized = normalize_dispatch_settings(settings)
    with DISPATCH_SETTINGS_LOCK:
        DISPATCH_SETTINGS_PATH.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")


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
    return bool(status.get("isRunning")) and process_state == "running"


def is_recent_spawn(spawn: object, role: str, now: datetime) -> bool:
    return is_live_pending_spawn(spawn, role=role, now=now)


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
            "sourceHandoffs",
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

    def spawn_log_path_is_safe(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            root = SPAWN_LOG_DIR.resolve()
            return resolved == root or root in resolved.parents
        except OSError:
            return False

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

    def latest_spawn_log_for_agent(self, agent: dict) -> dict:
        role = self.normalize_agent_role(agent.get("role"))
        model = self.normalize_agent_model(agent.get("model"))
        personal_name = self.safe_spawn_log_name_part(agent.get("personalName") or agent.get("agentName"))
        if not role or not personal_name or not SPAWN_LOG_DIR.exists():
            return {}
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
        enriched = dict(state)
        now = datetime.now(timezone.utc).astimezone()
        agents = []
        for agent in state.get("agents", []) or []:
            if not isinstance(agent, dict):
                continue
            enriched_agent = dict(agent)
            latest_log = self.latest_spawn_log_for_agent(enriched_agent)
            if latest_log:
                enriched_agent["latestLog"] = latest_log
            agents.append(enriched_agent)
        active_agents = [
            agent
            for agent in agents
            if agent.get("status") == "active"
            and is_active_agent_record(agent, str(agent.get("role") or "").strip().lower(), now)
        ]
        settings = load_dispatch_settings()
        pending_spawns = []
        for spawn in settings.get("pendingSpawns", []) or []:
            if not isinstance(spawn, dict):
                continue
            if self.pending_spawn_matches_active_agent(spawn, active_agents):
                continue
            process_status = spawned_process_status(spawn)
            if not is_live_pending_spawn(spawn, now=now, process_status=process_status):
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

    def load_board(self) -> dict:
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
        return model or "unknown"

    def start_phrase_for_role(self, role: str) -> str:
        return AGENT_ROLE_START_PHRASES.get(role, "")

    def spawn_command_for_tool(self, tool: str) -> str:
        settings = load_dispatch_settings()
        commands = settings.get("commands")
        if not isinstance(commands, dict):
            commands = {}
        fallback = CLAUDE_COMMAND if tool == "claude" else CODEX_COMMAND
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

    def get_pause_status(self, board: dict, payload: dict) -> dict:
        del board, payload
        return active_pause_status()

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
                text=True,
                timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
                check=False,
            )
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
            output = error.output if isinstance(error.output, str) else ""
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
        role = self.normalize_agent_role(payload.get("role"))
        roles_payload = payload.get("roles")
        commands_payload = payload.get("commands")
        if isinstance(roles_payload, dict):
            role_updates = {
                self.normalize_agent_role(role_name): role_value
                for role_name, role_value in roles_payload.items()
                if isinstance(role_value, dict)
            }
        elif role in {"worker", "review"}:
            role_updates = {role: payload}
        else:
            role_updates = {}

        for role_name, updates in role_updates.items():
            if role_name not in {"worker", "review"}:
                continue
            current = settings.get(role_name, {})
            settings[role_name] = {
                "enabled": bool(updates.get("enabled", current.get("enabled", False))),
                "model": normalize_dispatch_model(updates.get("model"), current.get("model", "codex")),
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
        except Exception as error:
            self.log_error("Unable to append API log: %s", error)

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
            "sourceHandoffs": self.normalize_list(payload.get("sourceHandoffs"), "sourceHandoffs"),
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
            "sourceHandoffs",
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
            "sourceHandoffs",
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
        task = self.pop_task(columns, "claimed", task_id)
        todo = self.ensure_column(columns, "todo")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Task board viewer")
        reason = str(payload.get("reason", "") or "").strip() or "Claim released because the worker agent stopped before finishing."
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
        return {"taskIds": [task_id]}

    def move_to_review(self, board: dict, columns: dict, payload: dict) -> None:
        task_id = self.require_task_id(payload)
        task = self.pop_task(columns, "claimed", task_id)
        review = self.ensure_column(columns, "review")
        timestamp = now_iso()
        agent_name = self.agent_name(payload, "Worker Agent")
        task["status"] = "review"
        task["reviewRequestedAt"] = timestamp
        task["completedBy"] = payload.get("completedBy") or agent_name or task.get("claimedBy", "")
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
        if tool == "codex":
            args = self.spawn_command_args(tool)
            args.extend(["exec", "--skip-git-repo-check", start_phrase])
        else:
            args = self.spawn_command_args(tool)
            args.extend(["-p", start_phrase])
        cli_command = args[0]
        cli_command_text = self.spawn_command_for_tool(tool)

        try:
            SPAWN_LOG_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", personal_name).strip("-") or "agent"
            run_stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
            log_path = SPAWN_LOG_DIR / f"{run_stamp}-{role}-{tool}-{safe_name}.log"
            popen_flags = 0
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                popen_flags |= subprocess.CREATE_NO_WINDOW
            env = agent_subprocess_env(tool)
            with log_path.open("a", encoding="utf-8") as log_file:
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
                process = subprocess.Popen(
                    args,
                    cwd=working_dir,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=popen_flags,
                    close_fds=True,
                )
        except FileNotFoundError as error:
            raise RuntimeError(f"Could not launch non-interactive {tool} agent: {error}") from error
        except Exception as error:
            raise RuntimeError(f"Spawn failed: {error}") from error

        return {
            "spawned": True,
            "mode": "non-interactive",
            "role": role,
            "tool": tool,
            "personalName": personal_name,
            "cliCommand": cli_command_text,
            "startPhrase": start_phrase,
            "backendBaseUrl": backend_base_url,
            "processId": process.pid,
            "logPath": str(log_path),
            "workingDirectory": working_dir,
            "resumeOfProcessId": resume_run.get("processId", "") if resume_run else "",
        }

    def persist_board(self, board: dict) -> None:
        try:
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
            self.log_error("Client disconnected before JSON response was sent")


def load_dispatch_board() -> dict:
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
    while True:
        time.sleep(AUTO_DISPATCH_INTERVAL_SECONDS)
        try:
            run_auto_dispatch_once(server)
        except Exception as error:
            append_dispatch_log({
                "action": "auto-dispatch-loop",
                "status": "error",
                "httpStatus": 500,
                "error": str(error),
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
