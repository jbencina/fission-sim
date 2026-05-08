"""Interactive PWR console — type commands, watch telemetry update in real time.

Real-time at 1 sim-second per 1 wall-clock second. The screen shows a rolling
window of the last 10 simulated seconds; commands are typed at a prompt below
the table.

Run:
    uv run python examples/console.py

Commands:
    <number>   set rod_command to value in [0, 1]  (e.g. "0.515")
    s          engage scram
    r          release scram
    q          quit (also: Ctrl-C)

Implementation notes:
    Single-threaded. Terminal is put into cbreak mode so we get keystrokes
    without an Enter press for backspace/control chars; commands themselves
    are line-buffered (committed on Enter). Screen redraws use ANSI cursor-
    home + clear-to-EOL so the display does not flicker. Unix-only (uses
    termios + tty); fission-sim is a Unix-targeted project.
"""

from __future__ import annotations

import select
import sys
import termios
import time
import tty
from collections import deque

from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator

# 1 sim-second per 1 wall-clock second.
DT = 1.0
# Rolling window of last N steps shown in the table.
BUFFER_LEN = 10
# pcm = per-cent-mille = 1e-5; standard reactivity display unit.
PCM = 1e5


def build_plant() -> SimEngine:
    """Wire the M1 plant. Mirrors examples/report_primary.py."""
    engine = SimEngine()
    rod = engine.module(RodController(RodParams()), name="rod")
    core = engine.module(PointKineticsCore(CoreParams()), name="core")
    loop = engine.module(PrimaryLoop(LoopParams()), name="loop")
    sg = engine.module(SteamGenerator(SGParams()), name="sg")
    sink = engine.module(SecondarySink(SinkParams()), name="sink")

    rod_cmd_sig = engine.input("rod_command", default=0.5)
    scram_sig = engine.input("scram", default=False)

    rho_rod = rod(rod_command=rod_cmd_sig, scram=scram_sig)
    T_sec = sink()
    Q_sg_sig = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rho_rod, T_cool=loop.T_cool)
    loop(power_thermal=core.power_thermal, Q_sg=Q_sg_sig)
    engine.finalize()
    return engine


def format_row(snap: dict) -> str:
    """One time-series row matching the report_primary table layout, plus
    T_hot and T_cold columns since space is available."""
    t = snap["t"]
    n = snap["core"]["n"]
    T_fuel = snap["core"]["T_fuel"]
    T_hot = snap["loop"]["T_hot"]
    T_cold = snap["loop"]["T_cold"]
    T_avg = (T_hot + T_cold) / 2.0
    rod_pos = snap["rod"]["rod_position"]
    rho_rod_v = snap["signals"]["rho_rod"] * PCM
    Q_core = snap["signals"]["power_thermal"] / 1e9
    Q_sg = snap["signals"]["Q_sg"] / 1e9
    return (
        f"   {t:6.1f}  {n:9.3e}  {T_fuel:7.2f}  {T_avg:6.2f}  {T_hot:6.2f}"
        f"  {T_cold:6.2f}  {rod_pos:7.4f}  {rho_rod_v:+7.1f}  {Q_core:6.3f}  {Q_sg:6.3f}"
    )


def header_lines() -> list[str]:
    """Static lines above the rolling buffer."""
    return [
        "=" * 92,
        "  PWR Reactor Console — Interactive M1 Plant       (1 sim-s = 1 wall-s, last 10 s)",
        "=" * 92,
        "",
        f"   {'t[s]':>6}  {'n':>9}  {'T_fuel':>7}  {'T_avg':>6}  {'T_hot':>6}"
        f"  {'T_cold':>6}  {'rod_pos':>7}  {'rho_rod':>7}  {'Q_core':>6}  {'Q_sg':>6}",
        f"   {'':>6}  {'':>9}  {'[K]':>7}  {'[K]':>6}  {'[K]':>6}"
        f"  {'[K]':>6}  {'':>7}  {'[pcm]':>7}  {'[GW]':>6}  {'[GW]':>6}",
        "   " + "-" * 89,
    ]


def status_line(state: dict) -> str:
    scram_str = "ON " if state["scram"] else "OFF"
    return (
        f"   sim_t = {state['sim_t']:7.1f} s    "
        f"rod_command = {state['rod_command']:.4f}    "
        f"scram = {scram_str}    "
        f"{state.get('msg', '')}"
    )


def render(state: dict) -> None:
    """Redraw the entire screen using ANSI escape codes.

    Uses cursor-home + per-line clear-to-EOL + final clear-below to avoid
    flicker. The terminal is in cbreak mode with cursor hidden, so the
    user's typed text is rendered by us (on the prompt line) rather than
    by the terminal's input echo.
    """
    rows = list(state["buffer"])
    lines = list(header_lines())
    for i in range(BUFFER_LEN):
        lines.append(format_row(rows[i]) if i < len(rows) else "")
    lines.append("   " + "-" * 89)
    lines.append(status_line(state))
    lines.append("")
    lines.append("   Commands:  <number> = rod_command (0..1)   's' = scram   'r' = release   'q' = quit")
    lines.append(f"   > {state['input']}")

    # ANSI: \033[H = move cursor to (0, 0); \033[K = clear to end of line;
    # \033[J = clear from cursor to end of screen.
    out = ["\033[H"]
    for line in lines:
        out.append("\033[K" + line + "\n")
    out.append("\033[J")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def process_command(state: dict, cmd: str) -> bool:
    """Apply a parsed command. Returns False if the user wants to quit."""
    cmd = cmd.strip()
    if cmd == "q" or cmd == "quit":
        return False
    if cmd == "s" or cmd == "scram":
        state["scram"] = True
        state["msg"] = ">>> SCRAM ENGAGED <<<"
        return True
    if cmd == "r" or cmd == "release":
        state["scram"] = False
        state["msg"] = "Scram released."
        return True
    if cmd == "":
        return True
    try:
        val = float(cmd)
    except ValueError:
        state["msg"] = f"ERROR: unknown command {cmd!r}"
        return True
    if not (0.0 <= val <= 1.0):
        state["msg"] = "ERROR: rod_command must be in [0, 1]"
        return True
    state["rod_command"] = val
    state["msg"] = f"rod_command set to {val:.4f}"
    return True


def main() -> None:
    if not sys.stdin.isatty():
        sys.stderr.write("examples/console.py is interactive — run it from a terminal, not a pipe.\n")
        sys.exit(1)
    engine = build_plant()
    state = {
        "sim_t": 0.0,
        "rod_command": 0.5,
        "scram": False,
        "msg": "Ready. Type a command and press Enter.",
        "input": "",
        "buffer": deque(maxlen=BUFFER_LEN),
    }
    state["buffer"].append(engine.snapshot())

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l")  # hide cursor
        sys.stdout.write("\033[2J")  # clear screen once at startup
        sys.stdout.flush()

        next_step_time = time.monotonic() + DT

        while True:
            render(state)

            now = time.monotonic()
            timeout = max(0.0, next_step_time - now)
            rlist, _, _ = select.select([sys.stdin], [], [], timeout)

            # Drain all pending input chars before stepping.
            while rlist:
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    if not process_command(state, state["input"]):
                        return
                    state["input"] = ""
                elif ch in ("\x7f", "\b"):  # backspace / DEL
                    state["input"] = state["input"][:-1]
                elif ch == "\x03":  # Ctrl-C
                    return
                elif ch.isprintable():
                    state["input"] += ch
                rlist, _, _ = select.select([sys.stdin], [], [], 0.0)

            if time.monotonic() >= next_step_time:
                snap = engine.step(
                    dt=DT,
                    rod_command=state["rod_command"],
                    scram=state["scram"],
                )
                state["buffer"].append(snap)
                state["sim_t"] = engine.t
                next_step_time += DT
                # Don't drift forward forever if integration runs slow.
                if next_step_time < time.monotonic():
                    next_step_time = time.monotonic() + DT
    finally:
        sys.stdout.write("\033[?25h")  # show cursor
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSANOW, old_attrs)
        print("\nExiting interactive console.")


if __name__ == "__main__":
    main()
