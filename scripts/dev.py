"""
scripts/dev.py — Concurrent dev-server launcher for fission-sim.

Starts the FastAPI backend (uvicorn) and the Vite frontend (npm run dev)
side-by-side, prefixes each line of their output with a colored tag, and
shuts both down cleanly when the user presses Ctrl-C.

Platform note
-------------
This script relies on Unix process-group semantics (``os.killpg``,
``start_new_session=True``).  Windows would need a different approach
(``CREATE_NEW_PROCESS_GROUP`` + ``CTRL_BREAK_EVENT``).  A cross-platform
implementation is out of scope; feat-013 / README will document this.

Usage
-----
    uv run python scripts/dev.py
    # or via Make:
    make dev
"""

import os
import signal
import subprocess
import sys
import threading

# ---------------------------------------------------------------------------
# ANSI colour codes — raw escapes so we need no third-party library.
# ---------------------------------------------------------------------------
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"

# ---------------------------------------------------------------------------
# Child-process commands
# ---------------------------------------------------------------------------
BACKEND_CMD = [
    "uv", "run", "uvicorn",
    "fission_sim.api.app:app",
    "--host", "0.0.0.0",  # bind all interfaces — accessible on the LAN
    "--port", "8000",
    "--reload",
]

# `npm run dev` calls `vite`; `web/vite.config.ts` sets `server.host: true` so
# Vite also binds 0.0.0.0 and prints the LAN URL on the "Network:" line.
FRONTEND_CMD = ["npm", "run", "dev", "--prefix", "web"]

# ---------------------------------------------------------------------------
# Shared state between threads / signal handler
# ---------------------------------------------------------------------------
_children: list[subprocess.Popen] = []   # populated after Popen succeeds
_shutdown_lock = threading.Lock()
_shutting_down = False


def _prefix_reader(proc: subprocess.Popen, prefix: str, colour: str) -> None:
    """Read *proc* stdout line-by-line and print with a coloured *prefix*.

    Parameters
    ----------
    proc:
        Running child process whose ``stdout`` pipe will be drained.
    prefix:
        Short label, e.g. ``"[api]"`` or ``"[web]"``.
    colour:
        ANSI escape sequence selecting the colour, e.g. ``CYAN``.
    """
    label = f"{colour}{BOLD}{prefix}{RESET}"
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")
        print(f"{label} {line}", flush=True)


def _terminate_children(timeout: float = 5.0) -> None:
    """Send SIGTERM to every child's process group, then wait *timeout* s.

    Any child that has not exited after the wait receives SIGKILL.

    Parameters
    ----------
    timeout:
        Seconds to wait for a graceful exit before escalating to SIGKILL.
    """
    for proc in _children:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass  # already gone

    for proc in _children:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait()


def _start_children(common_popen_kwargs: dict) -> tuple[subprocess.Popen, subprocess.Popen]:
    """Start backend and frontend children, cleaning up on partial failure."""
    try:
        backend = subprocess.Popen(BACKEND_CMD, **common_popen_kwargs)
        _children.append(backend)

        frontend = subprocess.Popen(FRONTEND_CMD, **common_popen_kwargs)
        _children.append(frontend)
    except Exception:
        if _children:
            _terminate_children()
            _children.clear()
        raise

    return backend, frontend


def _sigint_handler(signum, frame):  # noqa: ANN001
    """Handle Ctrl-C (SIGINT): terminate children, restore default handler, re-raise.

    When the user presses Ctrl-C in an interactive terminal, the OS delivers
    SIGINT to the entire foreground process group, so this handler runs in the
    Python process.  When ``make dev`` runs in the background and the make
    process receives SIGINT, GNU Make forwards SIGTERM to its child jobs — that
    case is covered by ``_sigterm_handler`` below.
    """
    global _shutting_down
    with _shutdown_lock:
        if _shutting_down:
            return
        _shutting_down = True

    print(f"\n{BOLD}[dev] Ctrl-C received — shutting down …{RESET}", flush=True)
    _terminate_children()

    # Restore default SIGINT so the re-raise propagates to the shell as a
    # normal keyboard interrupt (exit status 130 by convention).
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGINT)


def _sigterm_handler(signum, frame):  # noqa: ANN001
    """Handle SIGTERM: terminate children and exit.

    GNU Make sends SIGTERM to its child jobs when Make itself receives SIGINT
    (e.g. ``kill -INT $MAKE_PID`` from a test harness).  This handler ensures
    the launcher shuts down both servers cleanly in that scenario too.
    """
    global _shutting_down
    with _shutdown_lock:
        if _shutting_down:
            return
        _shutting_down = True

    print(f"\n{BOLD}[dev] SIGTERM received — shutting down …{RESET}", flush=True)
    _terminate_children()
    sys.exit(0)


def _watch_parent(initial_ppid: int) -> None:
    """Daemon thread: send SIGTERM to self if the parent process dies.

    When ``make dev`` is run in the background and the make process is killed
    (e.g. ``kill -INT $MAKE_PID`` in a test harness), ``uv run`` — which is our
    direct parent — also dies.  This thread detects that event by polling
    ``os.getppid()`` and self-signals so ``_sigterm_handler`` can run and clean
    up the child servers.

    Parameters
    ----------
    initial_ppid:
        The PID of our parent at startup (recorded before ``uv`` might be
        replaced by another process).
    """
    while True:
        threading.Event().wait(0.5)
        try:
            current_ppid = os.getppid()
        except OSError:
            break
        # If ppid changed to 1 (reparented to init/systemd), the original
        # parent died without sending us a signal.
        if current_ppid != initial_ppid and current_ppid == 1:
            with _shutdown_lock:
                if not _shutting_down:
                    print(
                        f"\n{BOLD}[dev] Parent process died — shutting down …{RESET}",
                        flush=True,
                    )
                    os.kill(os.getpid(), signal.SIGTERM)
            break


def _print_banner() -> None:
    """Print a startup banner with URLs and Ctrl-C hint."""
    print(
        f"\n{BOLD}╔══════════════════════════════════════════════╗{RESET}\n"
        f"{BOLD}║  fission-sim dev servers                     ║{RESET}\n"
        f"{BOLD}║                                              ║{RESET}\n"
        f"{BOLD}║  Backend  → http://localhost:8000            ║{RESET}\n"
        f"{BOLD}║  Frontend → http://localhost:5173            ║{RESET}\n"
        f"{BOLD}║  Bound to 0.0.0.0 — LAN-reachable.           ║{RESET}\n"
        f"{BOLD}║                                              ║{RESET}\n"
        f"{BOLD}║  Press Ctrl-C to stop both servers.          ║{RESET}\n"
        f"{BOLD}╚══════════════════════════════════════════════╝{RESET}\n",
        flush=True,
    )


def main() -> int:
    """Launch backend + frontend, forward output, and wait.

    Returns
    -------
    int
        Exit code: 0 on clean shutdown, or the failing child's exit code.
    """
    _print_banner()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    initial_ppid = os.getppid()

    # Install signal handlers *before* spawning children so we never orphan them.
    # SIGINT  — user presses Ctrl-C in an interactive terminal.
    # SIGTERM — GNU Make forwards this to child jobs when Make itself gets INT,
    #           e.g. when a test harness does ``kill -INT $MAKE_PID``.
    signal.signal(signal.SIGINT, _sigint_handler)
    signal.signal(signal.SIGTERM, _sigterm_handler)

    common_popen_kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge stderr → stdout so one reader suffices
        text=True,
        bufsize=1,               # line-buffered
        cwd=repo_root,
        start_new_session=True,  # child becomes its own process-group leader
    )

    backend, frontend = _start_children(common_popen_kwargs)

    # One reader thread per child — daemons so they don't block interpreter exit.
    threads = [
        threading.Thread(
            target=_prefix_reader,
            args=(backend, "[api]", CYAN),
            daemon=True,
        ),
        threading.Thread(
            target=_prefix_reader,
            args=(frontend, "[web]", MAGENTA),
            daemon=True,
        ),
    ]
    # Also start a daemon thread that watches for parent-process death.
    # This handles the case where the make process is killed (e.g. during test
    # harness teardown) without first sending a signal to this Python process.
    threads.append(
        threading.Thread(
            target=_watch_parent,
            args=(initial_ppid,),
            daemon=True,
        )
    )

    for t in threads:
        t.start()

    # Poll until one child exits or we receive a signal.
    exit_code = 0
    while True:
        for proc in list(_children):
            rc = proc.poll()
            if rc is not None:
                global _shutting_down
                with _shutdown_lock:
                    already = _shutting_down
                    _shutting_down = True

                if not already and rc != 0:
                    label = "[api]" if proc is backend else "[web]"
                    print(
                        f"{BOLD}[dev]{RESET} {label} exited unexpectedly "
                        f"with code {rc} — stopping the other server.",
                        flush=True,
                    )
                    exit_code = rc
                    _terminate_children()
                    return exit_code

                # Clean exit of one child (e.g. after SIGTERM) — just return.
                _terminate_children()
                return exit_code

        # Short sleep so we don't busy-wait at 100 % CPU.
        threading.Event().wait(0.2)


if __name__ == "__main__":
    sys.exit(main())
