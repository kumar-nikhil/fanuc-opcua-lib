"""
Build the standalone dist/FANUC-OPCUA.exe (Python, the library, the GUI page and all
dependencies in one file; the target PC needs nothing installed).

    .venv\\Scripts\\python packaging\\build_exe.py

Needs the dev environment: pip install -e ".[web]" pyinstaller
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "FANUC-OPCUA"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print('PyInstaller is missing. Install it with: pip install "pyinstaller>=6.16"')
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--console",
        "--name", NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(ROOT),
        # The GUI page (fanuc_opcua/web/static) and asyncua's lazily imported modules.
        "--collect-data", "fanuc_opcua",
        "--collect-submodules", "fanuc_opcua",
        "--collect-submodules", "asyncua",
        "--collect-submodules", "aiohttp",
        str(ROOT / "packaging" / "launcher.py"),
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode == 0:
        exe = ROOT / "dist" / f"{NAME}.exe"
        print(f"\nBuilt {exe} ({exe.stat().st_size / 1e6:.1f} MB)")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
