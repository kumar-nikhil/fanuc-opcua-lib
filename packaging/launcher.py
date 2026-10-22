"""
Entry point of the standalone FANUC-OPCUA.exe built by packaging/build_exe.ps1.

Double-click (no arguments): starts the browser GUI.
With arguments it is the fanuc-opcua command line, for example:

    FANUC-OPCUA.exe web --host 192.168.1.10 --read-only
    FANUC-OPCUA.exe read DO[1] R[5]
    FANUC-OPCUA.exe status --host 192.168.1.10
"""
import sys
import traceback

from fanuc_opcua import __version__
from fanuc_opcua.cli import main


def _pause(message: str) -> None:
    # A double-clicked console window closes as soon as the program ends;
    # wait so the user can read what went wrong.
    print(message)
    try:
        input("Press Enter to close this window...")
    except (EOFError, KeyboardInterrupt):
        pass


def run() -> int:
    double_clicked = len(sys.argv) == 1
    if double_clicked:
        print(f"FANUC OPC UA Console {__version__}")
        print("Starting the browser GUI. Keep this window open; close it or press Ctrl+C to stop.\n", flush=True)
    try:
        code = main(sys.argv[1:] or ["web"])
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001 - show anything unexpected before the window closes
        traceback.print_exc()
        code = 1
    if double_clicked and code not in (0, 130):
        _pause("\nThe GUI stopped with an error (see above).")
    return code


if __name__ == "__main__":
    sys.exit(run())
