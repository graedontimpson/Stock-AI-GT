"""Install or remove the automatic weekday run on this Mac.

    .venv/bin/python scripts/schedule.py install   # every weekday at 5:00 AM local time
    .venv/bin/python scripts/schedule.py remove
    .venv/bin/python scripts/schedule.py status

It only creates, loads, and removes one file:
~/Library/LaunchAgents/com.stock-ai.daily.plist
If the Mac is asleep at 5:00 AM, macOS runs it when the Mac wakes.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.stock-ai.daily"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
PROJECT = Path(__file__).resolve().parents[1]
HOUR, MINUTE = 5, 0
WEEKDAYS = [1, 2, 3, 4, 5]  # Monday to Friday


def domain() -> str:
    return f"gui/{os.getuid()}"


def agent() -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [str(PROJECT / ".venv" / "bin" / "python"), str(PROJECT / "scripts" / "scheduled_run.py")],
        "WorkingDirectory": str(PROJECT),
        "StartCalendarInterval": [{"Weekday": day, "Hour": HOUR, "Minute": MINUTE} for day in WEEKDAYS],
        # Anything the run prints outside its own log (such as a crash on start-up) goes here.
        "StandardOutPath": str(PROJECT / "data" / "logs" / "launchd.log"),
        "StandardErrorPath": str(PROJECT / "data" / "logs" / "launchd.log"),
    }


def is_loaded() -> bool:
    return subprocess.run(["launchctl", "print", f"{domain()}/{LABEL}"], capture_output=True).returncode == 0


def install():
    (PROJECT / "data" / "logs").mkdir(parents=True, exist_ok=True)
    if is_loaded():
        subprocess.run(["launchctl", "bootout", f"{domain()}/{LABEL}"], check=False)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST, "wb") as file:
        plistlib.dump(agent(), file)
    subprocess.run(["launchctl", "bootstrap", domain(), str(PLIST)], check=True)
    print(f"Installed: runs every weekday at {HOUR}:{MINUTE:02d} AM local time.")
    print(f"Logs go to {PROJECT / 'data' / 'logs'}.")


def remove():
    if is_loaded():
        subprocess.run(["launchctl", "bootout", f"{domain()}/{LABEL}"], check=False)
    if PLIST.exists():
        PLIST.unlink()
    print("Removed. The daily update will only run when you open the site.")


def status():
    print(f"Installed file: {'yes' if PLIST.exists() else 'no'} ({PLIST})")
    print(f"Loaded by macOS: {'yes' if is_loaded() else 'no'}")


if __name__ == "__main__":
    commands = {"install": install, "remove": remove, "status": status}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(1)
    commands[sys.argv[1]]()
