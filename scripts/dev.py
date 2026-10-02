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
implementation is out of scope.

Usage
-----
    uv run python scripts/dev.py
    # or via Make:
    make dev
    # with the backend on another port (Vite proxies to the same port):
    FISSION_SIM_API_PORT=8780 make dev
"""

import os
import signal
import subprocess
import sys
import threading
import time

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
DEFAULT_API_PORT = 8000
# Same variable web/vite.config.ts reads for its /api and /ws proxy target.
# The Vite child inherits this process's environment, so one setting moves both.
API_PORT_ENV = "FISSION_SIM_API_PORT"


def _api_port() -> int:
    """Backend port from ``FISSION_SIM_API_PORT``, else 8000.

    Raises
    ------
    SystemExit
        If the variable is set but is not an integer in 1-65535.
    """
    raw = os.environ.get(API_PORT_ENV)
    if raw is None or raw.strip() == "":
        return DEFAULT_API_PORT
    try:
        port = int(raw)
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        raise SystemExit(f"{API_PORT_ENV} must be a port number 1-65535, got {raw!r}")
    return port


def _backend_cmd(port: int) -> list[str]:
    """uvicorn command for the backend on *port*."""
    return [
        "uv", "run", "uvicorn",
        "fission_sim.api.app:app",
        "--host", "0.0.0.0",  # bind all interfaces — accessible on the LAN
        "--port", str(port),
        "--reload",
    ]

# `npm run dev` calls `vite`; `web/vite.config.ts` sets `server.host: true` so
# Vite also binds 0.0.0.0 and prints the LAN URL on the "Network:" line.
FRONTEND_CMD = ["npm", "run", "dev", "--prefix", "web"]

# ---------------------------------------------------------------------------
# Shared state between threads / signal handler
# ---------------------------------------------------------------------------
_children: list[subprocess.Popen] = []   # populated after Popen succeeds
# Process-group ID of each child, recorded at spawn. Each child is started
# with ``start_new_session=True``, so it leads a new group whose ID equals its
# PID. Recording it up front matters: once the leader has exited and been
# reaped, ``os.getpgid(proc.pid)`` fails, yet its descendants (a reloader's
# worker, npm's vite) can still be running in that group.
_process_groups: list[int] = []
_shutdown_lock = threading.Lock()
_shutting_down = False
# Set by the signal handlers, read by main()'s loop. Handlers only record
# which signal arrived; the blocking cleanup runs once, in the main loop.
_shutdown_signal: int | None = None


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


def _signal_group(pgid: int, sig: int) -> None:
    """Send *sig* to process group *pgid*, ignoring a group that is already gone."""
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass  # every process in the group has exited


def _group_alive(pgid: int) -> bool:
    """Return True while any process remains in group *pgid* (signal 0 probes)."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, but owned by someone else
    return True


def _terminate_children(timeout: float = 5.0) -> None:
    """Send SIGTERM to every child's process group, then wait up to *timeout* s.

    Any group that still has members after the wait receives SIGKILL. The
    group IDs recorded at spawn are signalled even if the leader has already
    exited, so descendants that outlived it are still stopped.

    Parameters
    ----------
    timeout:
        Seconds to wait for a graceful exit before escalating to SIGKILL.
    """
    for pgid in _process_groups:
        _signal_group(pgid, signal.SIGTERM)

    deadline = time.monotonic() + timeout
    # Reap the leaders first: an exited but unreaped leader is a zombie that
    # still counts as a group member.
    for proc in _children:
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    # Descendants may take a moment longer than their leader.
    while any(_group_alive(pgid) for pgid in _process_groups) and time.monotonic() < deadline:
        time.sleep(0.05)

    for pgid in _process_groups:
        if _group_alive(pgid):
            _signal_group(pgid, signal.SIGKILL)
    for proc in _children:
        proc.wait()


def _spawn(cmd: list[str], popen_kwargs: dict) -> subprocess.Popen:
    """Start *cmd* in its own session and record it for cleanup."""
    proc = subprocess.Popen(cmd, **popen_kwargs)
    _children.append(proc)
    # start_new_session=True makes the child a group leader: pgid == pid.
    # The kernel could reuse this ID once the whole group is gone, but the
    # recorded groups are only signalled during the short cleanup window.
    _process_groups.append(proc.pid)
    return proc


def _start_children(common_popen_kwargs: dict) -> tuple[subprocess.Popen, subprocess.Popen]:
    """Start backend and frontend children, cleaning up on partial failure."""
    try:
        backend = _spawn(_backend_cmd(_api_port()), common_popen_kwargs)
        frontend = _spawn(FRONTEND_CMD, common_popen_kwargs)
    except Exception:
        if _children:
            _terminate_children()
            _children.clear()
            _process_groups.clear()
        raise

    return backend, frontend


def _signal_handler(signum, frame):  # noqa: ANN001
    """Record a shutdown request from SIGINT (Ctrl-C) or SIGTERM.

    When the user presses Ctrl-C in an interactive terminal, the OS delivers
    SIGINT to the entire foreground process group. When ``make dev`` runs in
    the background and the make process receives SIGINT, GNU Make forwards
    SIGTERM to its child jobs instead.

    The handler only records the signal. Cleanup blocks (``proc.wait()``) and
    a signal can arrive while the main loop is inside ``proc.poll()``, which
    holds the same non-reentrant lock inside ``Popen``; waiting from here
    could deadlock. ``main()`` sees the flag within one poll interval and
    cleans up once.
    """
    global _shutdown_signal
    if _shutdown_signal is None:
        _shutdown_signal = signum


def _watch_parent(initial_ppid: int) -> None:
    """Daemon thread: send SIGTERM to self if the parent process dies.

    When ``make dev`` is run in the background and the make process is killed
    (e.g. ``kill -INT $MAKE_PID`` in a test harness), ``uv run`` — which is our
    direct parent — also dies.  This thread detects that event by polling
    ``os.getppid()`` and self-signals SIGTERM so ``main()`` cleans up the child
    servers.

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


def _print_banner(api_port: int) -> None:
    """Print a startup banner with URLs and Ctrl-C hint."""
    backend = f"Backend  → http://localhost:{api_port}"
    print(
        f"\n{BOLD}╔══════════════════════════════════════════════╗{RESET}\n"
        f"{BOLD}║  fission-sim dev servers                     ║{RESET}\n"
        f"{BOLD}║                                              ║{RESET}\n"
        f"{BOLD}║  {backend:<44}║{RESET}\n"
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
    # Validate before printing anything, so a bad value fails fast and clearly.
    _print_banner(_api_port())

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    initial_ppid = os.getppid()

    # Install signal handlers *before* spawning children so we never orphan them.
    # SIGINT  — user presses Ctrl-C in an interactive terminal.
    # SIGTERM — GNU Make forwards this to child jobs when Make itself gets INT,
    #           e.g. when a test harness does ``kill -INT $MAKE_PID``.
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

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
    global _shutting_down
    while True:
        if _shutdown_signal is not None:
            with _shutdown_lock:
                _shutting_down = True
            name = "Ctrl-C" if _shutdown_signal == signal.SIGINT else "SIGTERM"
            print(f"\n{BOLD}[dev] {name} received — shutting down …{RESET}", flush=True)
            _terminate_children()
            if _shutdown_signal == signal.SIGINT:
                # Restore default SIGINT and re-raise so the shell sees a
                # normal keyboard interrupt (exit status 130 by convention).
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                os.kill(os.getpid(), signal.SIGINT)
                return 130  # only reached if the re-raised signal is blocked
            return 0

        for proc in list(_children):
            rc = proc.poll()
            if rc is not None:
                with _shutdown_lock:
                    _shutting_down = True
                if rc != 0:
                    label = "[api]" if proc is backend else "[web]"
                    print(
                        f"{BOLD}[dev]{RESET} {label} exited unexpectedly "
                        f"with code {rc} — stopping the other server.",
                        flush=True,
                    )
                # Either way, one server is gone: stop the rest (including any
                # descendants of the one that exited) and return.
                _terminate_children()
                # Popen reports death by signal N as -N; shells report 128 + N.
                return rc if rc >= 0 else 128 - rc

        # Short sleep so we don't busy-wait at 100 % CPU.
        time.sleep(0.2)


if __name__ == "__main__":
    sys.exit(main())
