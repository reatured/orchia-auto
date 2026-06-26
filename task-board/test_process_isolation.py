#!/usr/bin/env python3
"""Regression test: Qwen spawn pipeline process-group isolation.

Verifies that:
  1. REPRODUCTION — Children spawned WITHOUT start_new_session inherit the
     parent process group and die when the parent group receives SIGINT.
  2. FIX — Children spawned WITH start_new_session=True survive when the
     parent (backend) process group receives SIGINT.
  3. EXIT STATUS — The formatter pipeline logs explicit process-exit status
     lines (return code or signal name) instead of a dangling traceback.
  4. HARD-STOP — Sending SIGTERM directly to an isolated child PID still
     terminates it (simulates hard-stop behavior).

Uses a fake Qwen script that emits slow JSONL so the test never calls the
real qwen CLI or spends model/API time.

Run:
    python3 task-board/test_process_isolation.py
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FORMATTER_SCRIPT = SCRIPT_DIR / "format_qwen_log.py"


def _qwen_process_isolation_kwargs():
    """Copied from server.py so the test is self-contained."""
    if os.name == "nt":
        return {}
    return {"start_new_session": True}


def _signal_name(returncode):
    """Copied from server.py so the test is self-contained."""
    sig_num = -returncode
    try:
        return signal.Signals(sig_num).name
    except (ValueError, AttributeError):
        return f"signal {sig_num}"


def _run_qwen_formatter_pipe(qwen_proc, log_fh, fmt_script):
    """Copied from server.py so the test is self-contained."""
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


FAKE_QWEN_SCRIPT = textwrap.dedent("""\
    import json, sys, time
    for i in range(60):
        event = {"type": "assistant", "message": {"content": [{"type": "text", "text": f"step {i}"}]}}
        sys.stdout.write(json.dumps(event) + "\\n")
        sys.stdout.flush()
        time.sleep(0.2)
    result = {"type": "result", "subtype": "success", "result": "done"}
    sys.stdout.write(json.dumps(result) + "\\n")
    sys.stdout.flush()
""")

# Wrapper: acts as a "backend" that spawns children WITHOUT isolation,
# then sends SIGINT to its own process group. Catches SIGINT to write
# exit status before exiting.
REPRO_WRAPPER_SCRIPT = textwrap.dedent("""\
    import json, os, signal, subprocess, sys, time

    fake_qwen = sys.argv[1]
    log_path = sys.argv[2]
    fmt_script = sys.argv[3]

    interrupted = False
    def handle_sigint(signum, frame):
        global interrupted
        interrupted = True
    signal.signal(signal.SIGINT, handle_sigint)

    log_fh = open(log_path, "a", encoding="utf-8")
    qwen_proc = subprocess.Popen(
        [sys.executable, "-u", fake_qwen],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=log_fh,
        close_fds=True,
    )
    fmt_proc = subprocess.Popen(
        [sys.executable, "-u", fmt_script],
        stdin=qwen_proc.stdout,
        stdout=log_fh,
        stderr=log_fh,
    )

    time.sleep(0.8)

    # Send SIGINT to our own process group — children inherit it
    os.killpg(os.getpgrp(), signal.SIGINT)

    time.sleep(1)

    qwen_proc.wait()
    fmt_proc.wait()
    qwen_rc = qwen_proc.returncode
    fmt_rc = fmt_proc.returncode
    qwen_status = f"return code {qwen_rc}" if qwen_rc >= 0 else f"signal {-qwen_rc} (code {qwen_rc})"
    fmt_status = f"return code {fmt_rc}" if fmt_rc >= 0 else f"signal {-fmt_rc} (code {fmt_rc})"
    log_fh.write(f"\\n--- Process exit status ---\\n")
    log_fh.write(f"qwen:      {qwen_status}\\n")
    log_fh.write(f"formatter: {fmt_status}\\n")
    log_fh.write(f"backend interrupted: {interrupted}\\n")
    log_fh.flush()
    log_fh.close()
    sys.exit(0)
""")

# Wrapper: acts as a "backend" that spawns children WITH isolation,
# then sends SIGINT to its own process group. Isolated children should survive.
FIX_WRAPPER_SCRIPT = textwrap.dedent("""\
    import json, os, signal, subprocess, sys, time

    fake_qwen = sys.argv[1]
    log_path = sys.argv[2]
    fmt_script = sys.argv[3]

    interrupted = False
    def handle_sigint(signum, frame):
        global interrupted
        interrupted = True
    signal.signal(signal.SIGINT, handle_sigint)

    log_fh = open(log_path, "a", encoding="utf-8")
    qwen_proc = subprocess.Popen(
        [sys.executable, "-u", fake_qwen],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=log_fh,
        close_fds=True,
        start_new_session=True,
    )
    fmt_proc = subprocess.Popen(
        [sys.executable, "-u", fmt_script],
        stdin=qwen_proc.stdout,
        stdout=log_fh,
        stderr=log_fh,
        start_new_session=True,
    )

    time.sleep(0.8)

    # Send SIGINT to our own process group — isolated children should survive
    os.killpg(os.getpgrp(), signal.SIGINT)

    # Wait for isolated children to finish normally (up to 20s)
    try:
        qwen_proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        qwen_proc.kill()
        qwen_proc.wait()
    try:
        fmt_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        fmt_proc.kill()
        fmt_proc.wait()

    qwen_rc = qwen_proc.returncode
    fmt_rc = fmt_proc.returncode
    qwen_status = f"return code {qwen_rc}" if qwen_rc >= 0 else f"signal {-qwen_rc} (code {qwen_rc})"
    fmt_status = f"return code {fmt_rc}" if fmt_rc >= 0 else f"signal {-fmt_rc} (code {fmt_rc})"
    log_fh.write(f"\\n--- Process exit status ---\\n")
    log_fh.write(f"qwen:      {qwen_status}\\n")
    log_fh.write(f"formatter: {fmt_status}\\n")
    log_fh.write(f"backend interrupted: {interrupted}\\n")
    log_fh.flush()
    log_fh.close()
    sys.exit(0)
""")


def write_fake_qwen(tmp_dir: Path) -> Path:
    script = tmp_dir / "fake_qwen.py"
    script.write_text(FAKE_QWEN_SCRIPT, encoding="utf-8")
    return script


def test_reproduction_inherited_group():
    """Old behavior: children in the same process group die on SIGINT."""
    print("TEST 1: Reproduction — inherited process group receives SIGINT")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        fake_qwen = write_fake_qwen(tmp_dir)
        log_path = tmp_dir / "inherited.log"
        wrapper = tmp_dir / "repro_wrapper.py"
        wrapper.write_text(REPRO_WRAPPER_SCRIPT, encoding="utf-8")

        wrapper_proc = subprocess.Popen(
            [sys.executable, str(wrapper), str(fake_qwen), str(log_path), str(FORMATTER_SCRIPT)],
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        wrapper_proc.wait(timeout=15)

        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        has_exit_block = "--- Process exit status ---" in log_text
        has_keyboard_interrupt = "KeyboardInterrupt" in log_text

        # Check for signal-based termination in the exit status block
        has_signal_death = False
        for line in log_text.splitlines():
            if "signal" in line and "code -" in line:
                has_signal_death = True
                break

        print(f"  wrapper exit code: {wrapper_proc.returncode}")
        print(f"  exit status block present: {has_exit_block}")
        print(f"  children killed by signal: {has_signal_death}")
        print(f"  KeyboardInterrupt in log: {has_keyboard_interrupt}")

        if (has_signal_death or has_keyboard_interrupt) and has_exit_block:
            print("  PASS: inherited group children were killed by SIGINT (reproduces old behavior)")
            return True
        else:
            print("  FAIL: expected signal death or KeyboardInterrupt with exit status block")
            print(f"  Log:\n{log_text[-600:]}")
            return False


def test_fix_isolated_group():
    """New behavior: isolated children survive backend-group SIGINT."""
    print("\nTEST 2: Fix — isolated process group survives backend SIGINT")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        fake_qwen = write_fake_qwen(tmp_dir)
        log_path = tmp_dir / "isolated.log"
        wrapper = tmp_dir / "fix_wrapper.py"
        wrapper.write_text(FIX_WRAPPER_SCRIPT, encoding="utf-8")

        wrapper_proc = subprocess.Popen(
            [sys.executable, str(wrapper), str(fake_qwen), str(log_path), str(FORMATTER_SCRIPT)],
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        wrapper_proc.wait(timeout=30)

        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        has_exit_block = "--- Process exit status ---" in log_text
        qwen_ok = "qwen:      return code 0" in log_text
        fmt_ok = "formatter: return code 0" in log_text

        print(f"  wrapper exit code: {wrapper_proc.returncode}")
        print(f"  exit status block present: {has_exit_block}")
        print(f"  qwen return code 0: {qwen_ok}")
        print(f"  formatter return code 0: {fmt_ok}")

        if has_exit_block and qwen_ok and fmt_ok:
            print("  PASS: isolated children survived SIGINT and completed normally")
            return True
        else:
            print("  FAIL: expected normal completion with exit status block")
            print(f"  Log tail:\n{log_text[-600:]}")
            return False


def test_hard_stop_terminates_isolated():
    """Hard-stop: SIGTERM to the isolated PID still kills it."""
    print("\nTEST 3: Hard-stop — SIGTERM to isolated PID terminates it")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        fake_qwen = write_fake_qwen(tmp_dir)
        log_path = tmp_dir / "hardstop.log"

        log_fh = log_path.open("a", encoding="utf-8")
        log_fh.write("Spawned fake qwen (isolated) for hard-stop + formatter test\n\n")
        log_fh.flush()

        process = subprocess.Popen(
            [sys.executable, "-u", str(fake_qwen)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=log_fh,
            close_fds=True,
            **_qwen_process_isolation_kwargs(),
        )

        t = threading.Thread(
            target=_run_qwen_formatter_pipe,
            args=(process, log_fh, str(FORMATTER_SCRIPT)),
            daemon=True,
        )
        t.start()

        time.sleep(0.5)

        try:
            os.kill(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        t.join(timeout=10)
        process.wait(timeout=10)
        rc = process.returncode

        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        has_exit_block = "--- Process exit status ---" in log_text
        has_sigterm = "SIGTERM" in log_text

        terminated = rc is not None and rc < 0

        print(f"  qwen return code: {rc} (terminated: {terminated})")
        print(f"  exit status block present: {has_exit_block}")
        print(f"  SIGTERM in log: {has_sigterm}")

        if terminated and has_exit_block:
            print("  PASS: hard-stop terminated isolated process with exit status logged")
            return True
        else:
            print("  FAIL: expected signal termination with exit status block")
            print(f"  Log:\n{log_text[-400:]}")
            return False


def test_signal_name_helper():
    """Verify _signal_name returns correct names."""
    print("\nTEST 4: _signal_name helper")
    sigint_name = _signal_name(-signal.SIGINT)
    sigterm_name = _signal_name(-signal.SIGTERM)
    unknown_name = _signal_name(-999)

    print(f"  SIGINT:  {sigint_name}")
    print(f"  SIGTERM: {sigterm_name}")
    print(f"  signal 999: {unknown_name}")

    ok = "SIGINT" in sigint_name and "SIGTERM" in sigterm_name and "signal 999" in unknown_name
    print(f"  {'PASS' if ok else 'FAIL'}")
    return ok


def test_isolation_kwargs():
    """Verify _qwen_process_isolation_kwargs returns expected values."""
    print("\nTEST 5: _qwen_process_isolation_kwargs")
    kwargs = _qwen_process_isolation_kwargs()
    if os.name == "nt":
        ok = kwargs == {}
        print(f"  Windows: kwargs={kwargs} (expected empty)")
    else:
        ok = kwargs == {"start_new_session": True}
        print(f"  POSIX: kwargs={kwargs} (expected start_new_session=True)")
    print(f"  {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    if os.name == "nt":
        print("SKIP: process-group isolation tests are POSIX-only\n")
        results = [test_signal_name_helper(), test_isolation_kwargs()]
        passed = sum(1 for r in results if r)
        print(f"\n{'='*60}")
        print(f"Results: {passed}/{len(results)} passed")
        sys.exit(0 if passed == len(results) else 1)

    results = [
        test_reproduction_inherited_group(),
        test_fix_isolated_group(),
        test_hard_stop_terminates_isolated(),
        test_signal_name_helper(),
        test_isolation_kwargs(),
    ]
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
