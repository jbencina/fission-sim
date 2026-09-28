"""Interactive PWR console — type commands, watch telemetry update in real time.

Real-time at 1 sim-second per 1 wall-clock second by default. Use --speed
to compress time (e.g. --speed 60 → 1 minute of plant time per wall-second,
useful for watching slow delayed-neutron transients without waiting). The
screen shows a rolling window of the last N rows; commands are typed at a
prompt below the table.

Run:
    uv run python examples/console.py
    uv run python examples/console.py --speed 60   # 60x faster than real

Commands:
    <number>        set rod_command to value in [0, 1]  (e.g. "0.6";
                    12 pcm per 0.01, ±600 pcm about the 0.5 design point)
    s               engage scram
    r               idealized scram signal release; leaves turbine admission
                    demand at 0, so re-admission is an explicit operator action
    h <0-1>         set heater override to fraction in [0, 1]  (e.g. "h 0.3")
    h auto          return heater to automatic control
    y <0-1>         set spray override to fraction in [0, 1]  (e.g. "y 0.1")
    y auto          return spray to automatic control
    p <MPa>         set pressure setpoint in MPa  (e.g. "p 15.6")
    p reset         restore default pressure setpoint (15.5 MPa)
    admission <0-1> / turbine_load <0-1>
                    set turbine admission demand (valve admission, not MW);
                    gross electrical MW is displayed separately
    trip            Unprotected turbine trip: automatic reactor trip on
                    turbine trip omitted; ideal feedwater and combined
                    dump/relief available
    untrip          idealized turbine-trip signal release; leaves turbine
                    admission demand at 0 and is not a plant restart
    auto / manual   enable/disable automatic Tavg rod control
    q               quit (also: Ctrl-C)

Implementation notes:
    Single-threaded. Terminal is put into cbreak mode so we get keystrokes
    without an Enter press for backspace/control chars; commands themselves
    are line-buffered (committed on Enter). Screen redraws use ANSI cursor-
    home + clear-to-EOL so the display does not flicker. Unix-only (uses
    termios + tty); fission-sim is a Unix-targeted project.

    --speed N scales DT (sim-seconds per step) — each row in the rolling
    window represents N sim-seconds, and the display advances at a fixed
    1 Hz wall-clock rate. The buffer length stays 10 rows, so you see the
    last 10·N sim-seconds of history. At --speed 60, the rolling window
    shows the last 10 minutes of plant time.
"""

from __future__ import annotations

import argparse
import select
import sys
import termios
import textwrap
import time
import tty
from collections import deque

from fission_sim.control.pressurizer_controller import PressurizerControllerParams
from fission_sim.disclaimer import print_disclaimer
from fission_sim.physics.domain import ModelDomainError, check_snapshot
from fission_sim.plant import build_standard_plant

# Rolling window of last N steps shown in the table.
BUFFER_LEN = 10
# pcm = per-cent-mille = 1e-5; standard reactivity display unit.
PCM = 1e5
# Wall-clock interval between display ticks. Constant regardless of speed.
WALL_TICK_S = 1.0
# Default pressure setpoint [Pa], the controller's design setpoint (15.5 MPa).
P_SETPOINT_DEFAULT = PressurizerControllerParams().P_setpoint_default
# The console layout is intentionally narrow enough for a default terminal.
DISPLAY_WIDTH = 92
UNPROTECTED_TURBINE_TRIP_LABEL = (
    "Unprotected turbine trip: automatic reactor trip on turbine trip omitted; "
    "ideal feedwater and combined dump/relief available"
)
SIGNAL_RELEASE_NOTE = (
    "idealized signal release; turbine admission demand held at 0.000. "
    "This is not a plant restart; command admission to re-admit steam."
)


def format_row(snap: dict) -> str:
    """One time-series row for the rolling table.

    Columns: t, n, T_fuel, T_avg, rod_pos, rho_rod, Q_core, Q_sg, P[MPa], level, Q_htr.
    T_hot and T_cold are omitted to keep width ≤ 92 chars; T_avg is the
    operationally relevant bulk coolant temperature.
    """
    t = snap["t"]
    n = snap["core"]["n"]
    T_fuel = snap["core"]["T_fuel"]
    T_hot = snap["loop"]["T_hot"]
    T_cold = snap["loop"]["T_cold"]
    T_avg = (T_hot + T_cold) / 2.0
    rod_pos = snap["rod"]["rod_position"]
    rho_rod_v = snap["signals"]["rho_rod"] * PCM
    Q_core = snap["core"]["power_thermal"] / 1e9
    Q_sg = snap["signals"]["Q_sg"] / 1e9

    pzr = snap["pzr"]
    P_MPa = pzr["P"] / 1e6
    level = pzr["level"] * 100.0  # fraction → percent
    Q_htr = pzr["Q_heater"] / 1e6  # W → MW

    return (
        f" {t:6.1f}  {n:9.3e}  {T_fuel:7.2f}  {T_avg:6.2f}"
        f"  {rod_pos:7.4f}  {rho_rod_v:+7.1f}  {Q_core:6.3f}  {Q_sg:6.3f}"
        f"  {P_MPa:6.3f}  {level:5.1f}  {Q_htr:6.2f}"
    )


def header_lines(speed: float) -> list[str]:
    """Static lines above the rolling buffer."""
    window_s = BUFFER_LEN * speed
    if speed == 1.0:
        speed_str = "1 sim-s = 1 wall-s"
    else:
        speed_str = f"{speed:g} sim-s/wall-s ({speed:g}x real-time)"
    title = f"  PWR Reactor Console — Interactive P/S Plant   ({speed_str}, last {window_s:g} s)"
    return [
        "=" * DISPLAY_WIDTH,
        title,
        "=" * DISPLAY_WIDTH,
        "",
        f" {'t[s]':>6}  {'n':>9}  {'T_fuel':>7}  {'T_avg':>6}"
        f"  {'rod_pos':>7}  {'rho_rod':>7}  {'Q_core':>6}  {'Q_sg':>6}"
        f"  {'P[MPa]':>6}  {'pzr%':>5}  {'Q_htr':>6}",
        f" {'':>6}  {'':>9}  {'[K]':>7}  {'[K]':>6}"
        f"  {'':>7}  {'[pcm]':>7}  {'[GW]':>6}  {'[GW]':>6}"
        f"  {'':>6}  {'[%]':>5}  {'[MW]':>6}",
        "   " + "-" * 89,
    ]


def _on_off(value: bool) -> str:
    """Return a fixed-width operator-style on/off label."""
    return "ON " if value else "OFF"


def _turbine_trip_status(snap: dict) -> str:
    """Return the effective turbine-trip state and cause for display."""
    turbine = snap["turbine"]
    if not turbine.get("trip_active"):
        return "OFF"

    causes: list[str] = []
    if turbine.get("turbine_trip"):
        causes.append("explicit trip")
    if turbine.get("scram"):
        causes.append("SCRAM via P-4")
    cause = " + ".join(causes) if causes else "trip active"
    return f"ON ({cause})"


def _rod_control_status(snap: dict, state: dict) -> str:
    """Return MANUAL / AUTO ACTIVE / AUTO SUSPENDED from controller telemetry."""
    ctrl = snap["tavg_ctrl"]
    if not bool(ctrl.get("rod_auto", state["rod_auto"])):
        return "MANUAL"
    return "AUTO ACTIVE" if ctrl.get("acting") else "AUTO SUSPENDED"


def _fmt_optional_fraction(value: float | None) -> str:
    """Format a manual fraction, or ``auto`` when automatic control owns it."""
    return f"{value:.2f}" if value is not None else "auto"


def _message_lines(message: str) -> list[str]:
    """Wrap the current acknowledgement without exceeding the console width."""
    if not message:
        return []
    return textwrap.wrap(f"   msg: {message}", width=DISPLAY_WIDTH, subsequent_indent="   msg: ")


def status_lines(state: dict) -> list[str]:
    """Return terminal-width-aware operator status rows.

    The rows distinguish physical positions from demands, command state from
    effective trip state, and the SG collapsed liquid fraction from real
    indicated level. Keeping this formatting as a pure function makes the
    operator-facing labels regression-testable without running a terminal.
    """
    htr = state.get("heater_manual")
    spr = state.get("spray_manual")
    P_set_MPa = state.get("P_setpoint", P_SETPOINT_DEFAULT) / 1e6
    snap = state["last_snap"]
    rod = snap["rod"]
    ctrl = snap["tavg_ctrl"]
    turbine = snap["turbine"]
    fw = snap["fw_ctrl"]
    loop = snap["loop"]
    sg_sec = snap["sg_sec"]

    rod_actual = float(rod["rod_position"])
    rod_demand = float(ctrl.get("rod_demand", snap["signals"]["rod_demand"]))
    manual_cmd = float(state["rod_command"])
    rod_status = _rod_control_status(snap, state)

    admission_demand = float(state.get("turbine_load", turbine["load_demand"]))
    admission_actual = float(turbine["load"])
    P_electric = float(turbine["P_electric"]) / 1e6
    T_err = float(ctrl["T_err"] if ctrl.get("T_err") is not None else loop["T_avg"] - turbine["T_ref"])
    P_steam = snap["sg_sec"]["P_steam"] / 1e6
    level_sg = float(sg_sec["level_sg"]) * 100.0
    m_fw = float(fw["m_fw"])
    m_steam = float(turbine["m_steam"])
    m_dump = float(turbine["m_dump"])
    flow_mismatch = m_fw - (m_steam + m_dump)

    lines = [
        f"   sim_t = {state['sim_t']:7.1f} s  scram = {_on_off(state['scram'])}  "
        f"turbine trip = {_turbine_trip_status(snap)}",
        f"   rod control = {rod_status}  rod actual = {rod_actual:.4f}  active demand = {rod_demand:.4f}",
        f"   retained manual cmd = {manual_cmd:.4f}  htr = {_fmt_optional_fraction(htr)}  "
        f"spr = {_fmt_optional_fraction(spr)}  P_set = {P_set_MPa:.2f} MPa",
        f"   turbine admission demand/actual = {100.0 * admission_demand:5.1f}% / "
        f"{100.0 * admission_actual:5.1f}%  gross electrical = {P_electric:.0f} MW",
        f"   T_avg - T_ref = {T_err:+.2f} K  P_steam = {P_steam:.3f} MPa  "
        f"SG collapsed frac = {level_sg:5.1f}%",
        f"   secondary flows: feed = {m_fw:7.1f} kg/s  steam = {m_steam:7.1f} kg/s  "
        f"dump = {m_dump:7.1f} kg/s",
        f"   flow mismatch feed - (steam + dump) = {flow_mismatch:+.3f} kg/s",
    ]
    lines.extend(_message_lines(state.get("msg", "")))
    return lines


def status_line(state: dict) -> str:
    """Return a one-line status string for older callers."""
    return "  ".join(status_lines(state))


def render(state: dict) -> None:
    """Redraw the entire screen using ANSI escape codes.

    Uses cursor-home + per-line clear-to-EOL + final clear-below to avoid
    flicker. The terminal is in cbreak mode with cursor hidden, so the
    user's typed text is rendered by us (on the prompt line) rather than
    by the terminal's input echo.
    """
    rows = list(state["buffer"])
    lines = list(header_lines(state["speed"]))
    for i in range(BUFFER_LEN):
        lines.append(format_row(rows[i]) if i < len(rows) else "")
    lines.append("   " + "-" * 89)
    lines.extend(status_lines(state))
    lines.append("")
    lines.append(
        "   SG collapsed frac = 4 SGs lumped; no shrink/swell. "
        "Use --speed 1 to watch trips."
    )
    lines.append("   Commands: <num>=rod  auto/manual rods  s=scram  r=idealized release")
    lines.append("             admission <0-1> (or turbine_load) = turbine admission demand")
    lines.append("             trip: Unprotected turbine trip — automatic reactor trip on turbine trip")
    lines.append("                   omitted; ideal feedwater and combined dump/relief available")
    lines.append("             untrip=idealized release  q=quit")
    lines.append("             h <0-1>/auto=heater  y <0-1>/auto=spray  p <MPa>/reset=setpoint")
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
        state["turbine_load"] = 0.0
        state["msg"] = f"Scram {SIGNAL_RELEASE_NOTE}"
        return True
    if cmd == "trip":
        state["turbine_trip"] = True
        state["msg"] = UNPROTECTED_TURBINE_TRIP_LABEL
        return True
    if cmd == "untrip":
        state["turbine_trip"] = False
        state["turbine_load"] = 0.0
        state["msg"] = f"Turbine trip {SIGNAL_RELEASE_NOTE}"
        return True
    if cmd == "auto":
        state["rod_auto"] = True
        state["msg"] = "Automatic Tavg rod control enabled."
        return True
    if cmd == "manual":
        state["rod_auto"] = False
        # Bumpless transfer: manual mode passes rod_command directly to the
        # actuator, so align the operator's command with the actual bank
        # before taking automatic control out of service.
        state["rod_command"] = state["last_snap"]["rod"]["rod_position"]
        state["msg"] = f"Manual rods; command synced to actual position {state['rod_command']:.4f}."
        return True
    if cmd == "":
        return True

    # --- heater manual override: "h <0-1>" or "h auto" ---
    if cmd.startswith("h ") or cmd == "h":
        arg = cmd[2:].strip() if cmd.startswith("h ") else ""
        if arg == "auto" or arg == "":
            state["heater_manual"] = None
            state["msg"] = "Heater returned to automatic control."
        else:
            try:
                val = float(arg)
            except ValueError:
                state["msg"] = f"ERROR: 'h' expects a number in [0,1] or 'auto', got {arg!r}"
                return True
            if not (0.0 <= val <= 1.0):
                state["msg"] = "ERROR: heater fraction must be in [0, 1]"
                return True
            state["heater_manual"] = val
            state["msg"] = f"Heater override set to {val:.2f}"
        return True

    # --- spray manual override: "y <0-1>" or "y auto" ---
    if cmd.startswith("y ") or cmd == "y":
        arg = cmd[2:].strip() if cmd.startswith("y ") else ""
        if arg == "auto" or arg == "":
            state["spray_manual"] = None
            state["msg"] = "Spray returned to automatic control."
        else:
            try:
                val = float(arg)
            except ValueError:
                state["msg"] = f"ERROR: 'y' expects a number in [0,1] or 'auto', got {arg!r}"
                return True
            if not (0.0 <= val <= 1.0):
                state["msg"] = "ERROR: spray fraction must be in [0, 1]"
                return True
            state["spray_manual"] = val
            state["msg"] = f"Spray override set to {val:.2f}"
        return True

    # --- pressure setpoint: "p <MPa>" or "p reset" ---
    if cmd.startswith("p ") or cmd == "p":
        arg = cmd[2:].strip() if cmd.startswith("p ") else ""
        if arg == "reset" or arg == "":
            state["P_setpoint"] = P_SETPOINT_DEFAULT
            state["msg"] = f"Pressure setpoint reset to {P_SETPOINT_DEFAULT / 1e6:.2f} MPa"
        else:
            try:
                val_mpa = float(arg)
            except ValueError:
                state["msg"] = f"ERROR: 'p' expects MPa value or 'reset', got {arg!r}"
                return True
            # Reasonable operating range: 10–17.5 MPa for a PWR primary circuit.
            if not (10.0 <= val_mpa <= 17.5):
                state["msg"] = "ERROR: pressure setpoint must be in [10, 17.5] MPa"
                return True
            state["P_setpoint"] = val_mpa * 1e6
            state["msg"] = f"Pressure setpoint set to {val_mpa:.3f} MPa"
        return True

    # --- turbine admission demand: "admission <0-1>" or "turbine_load <0-1>" ---
    if cmd.startswith("admission ") or cmd == "admission" or cmd.startswith("turbine_load ") or cmd == "turbine_load":
        keyword = "admission" if cmd.startswith("admission") else "turbine_load"
        arg = cmd[len(keyword) :].strip()
        try:
            val = float(arg)
        except ValueError:
            state["msg"] = f"ERROR: '{keyword}' expects a turbine admission demand in [0,1], got {arg!r}"
            return True
        if not (0.0 <= val <= 1.0):
            state["msg"] = "ERROR: turbine admission demand must be in [0, 1]"
            return True
        state["turbine_load"] = val
        state["msg"] = f"Turbine admission demand set to {val:.3f} (valve admission, not MW)."
        return True

    # --- numeric rod command ---
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Sim-seconds per wall-clock-second (default 1.0). E.g. --speed 60 "
        "compresses 1 minute of plant time into 1 wall-second; useful for "
        "watching slow delayed-neutron transients without waiting.",
    )
    return p.parse_args()


def main() -> None:
    print_disclaimer()
    args = parse_args()
    if args.speed <= 0:
        sys.stderr.write(f"--speed must be > 0, got {args.speed}\n")
        sys.exit(2)

    if not sys.stdin.isatty():
        sys.stderr.write("examples/console.py is interactive — run it from a terminal, not a pipe.\n")
        sys.exit(1)
    engine = build_standard_plant()
    state = {
        "sim_t": 0.0,
        "rod_command": 0.5,
        "scram": False,
        "msg": "Ready. Type a command and press Enter.",
        "input": "",
        "buffer": deque(maxlen=BUFFER_LEN),
        "speed": args.speed,
        "last_snap": engine.snapshot(),
        # Pressurizer operator controls — None means auto (controller decides).
        "heater_manual": None,   # fraction [0, 1] or None
        "spray_manual": None,    # fraction [0, 1] or None
        "P_setpoint": P_SETPOINT_DEFAULT,  # [Pa] default 15.5 MPa
        "turbine_load": 1.0,
        "turbine_trip": False,
        "rod_auto": False,
    }
    state["buffer"].append(state["last_snap"])

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    halt_reason: ModelDomainError | None = None
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l")  # hide cursor
        sys.stdout.write("\033[2J")  # clear screen once at startup
        sys.stdout.flush()

        next_step_time = time.monotonic() + WALL_TICK_S

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
                # Each wall-tick advances sim by `speed` seconds.
                snap = engine.step(
                    dt=args.speed,
                    rod_command=state["rod_command"],
                    scram=state["scram"],
                    P_setpoint=state["P_setpoint"],
                    heater_manual=state["heater_manual"],
                    spray_manual=state["spray_manual"],
                    turbine_load=state["turbine_load"],
                    turbine_trip=state["turbine_trip"],
                    rod_auto=state["rod_auto"],
                )
                # Stop, as the web runtime does, once the state leaves the
                # model's liquid-loop / saturated-pressurizer domain.
                check_snapshot(snap)
                state["buffer"].append(snap)
                state["last_snap"] = snap
                state["sim_t"] = engine.t
                next_step_time += WALL_TICK_S
                # Don't drift forward forever if integration runs slow.
                if next_step_time < time.monotonic():
                    next_step_time = time.monotonic() + WALL_TICK_S
    except ModelDomainError as err:
        halt_reason = err
    finally:
        sys.stdout.write("\033[?25h")  # show cursor
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSANOW, old_attrs)
        print("\nExiting interactive console.")
    if halt_reason is not None:
        print(f"Model limit reached: {halt_reason} The simulation stopped at t = {state['sim_t']:.1f} s.")


if __name__ == "__main__":
    main()
