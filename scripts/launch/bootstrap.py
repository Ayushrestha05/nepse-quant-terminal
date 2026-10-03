#!/usr/bin/env python3
"""Create/update the local environment and launch the desktop dashboard."""
from __future__ import annotations

import hashlib
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

MIN_PYTHON = (3, 10)
MAX_PYTHON_EXCLUSIVE = (3, 14)
VENV_DIRNAME = ".venv"
REQUIREMENTS_STAMP = ".nepse_quant_requirements.sha256"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_supported_python(version: Sequence[int] | None = None) -> bool:
    parts = tuple(version or sys.version_info[:3])
    return MIN_PYTHON <= parts[:2] < MAX_PYTHON_EXCLUSIVE


def requirements_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / VENV_DIRNAME / "Scripts" / "python.exe"
    return root / VENV_DIRNAME / "bin" / "python"


def _python_is_supported(python: Path | str) -> bool:
    try:
        result = subprocess.run(
            [str(python), "-c", "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def select_linux_runtime(root: Path, python_candidates: Sequence[str] | None = None) -> tuple[Path, str]:
    """Prefer a supported project environment, then the newest supported Python."""
    project_python = venv_python(root)
    if project_python.exists() and _python_is_supported(project_python):
        return project_python, VENV_DIRNAME

    names = python_candidates or ("python3.13", "python3.12", "python3.11", "python3.10", "python3")
    for name in names:
        candidate = shutil.which(name) if python_candidates is None else name
        if candidate and _python_is_supported(candidate):
            venv_dir = ".venv-linux" if project_python.exists() else VENV_DIRNAME
            return Path(candidate), venv_dir
    raise SystemExit("Python 3.10–3.13 is required. Install Python 3.12 and launch again.")


def linux_applications_dir(env: dict[str, str] | None = None, home: Path | None = None) -> Path:
    values = os.environ if env is None else env
    data_home = values.get("XDG_DATA_HOME", "")
    if data_home and Path(data_home).is_absolute():
        return Path(data_home) / "applications"
    return (home or Path.home()) / ".local" / "share" / "applications"


def desktop_exec_quote(value: str) -> str:
    """Quote one freedesktop Exec argument, including literal percent signs."""
    escaped = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def install_linux_shortcut(root: Path, applications_dir: Path | None = None) -> Path:
    """Install or replace the per-user application-menu shortcut."""
    root = root.resolve()
    launcher = root / "Launch Quant Terminal.sh"
    if not launcher.is_file():
        raise SystemExit(f"Linux launcher not found: {launcher}")
    target_dir = applications_dir or linux_applications_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = target_dir / "nepse-quant-terminal.desktop"
    contents = "\n".join((
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        "Name=NEPSE Quant Terminal",
        "Comment=NEPSE market research and paper trading",
        f"Exec={desktop_exec_quote(str(launcher))}",
        f"Path={root}",
        "Icon=utilities-terminal",
        "Terminal=true",
        "Categories=Finance;Office;",
        "",
    ))
    desktop_file.write_text(contents, encoding="utf-8")
    return desktop_file


def run(cmd: Sequence[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(str(part) for part in cmd)}", flush=True)
    return subprocess.run([str(part) for part in cmd], cwd=str(cwd), check=check)


def ensure_supported_python() -> None:
    if is_supported_python():
        return
    current = ".".join(map(str, sys.version_info[:3]))
    raise SystemExit(
        f"Python {current} is not supported. Install Python 3.10 through 3.13, "
        "then launch again. Python 3.12 is recommended."
    )


def ensure_virtualenv(root: Path, directory: str = VENV_DIRNAME) -> Path:
    python = venv_python(root) if directory == VENV_DIRNAME else root / directory / "bin" / "python"
    if python.exists():
        if not _python_is_supported(python):
            raise SystemExit(f"Unsupported Python in {python}. Remove or rename that environment, then launch again.")
        return python
    target = root / directory
    print(f"Creating local Python environment at {target}...")
    run([sys.executable, "-m", "venv", target], cwd=root)
    return python


def ensure_requirements(root: Path, python: Path) -> None:
    requirements = root / "requirements.txt"
    stamp = root / VENV_DIRNAME / REQUIREMENTS_STAMP
    current_hash = requirements_hash(requirements)
    if stamp.exists() and stamp.read_text(encoding="utf-8").strip() == current_hash:
        print("Python dependencies are already installed.")
        return

    print("Installing Python dependencies. First launch can take a few minutes...")
    run([python, "-m", "pip", "install", "-U", "pip"], cwd=root)
    try:
        run([python, "-m", "pip", "install", "-r", requirements], cwd=root)
    except subprocess.CalledProcessError as exc:
        print(
            "\nDependency install failed. Make sure Git is installed and available on PATH, "
            "then launch again."
        )
        raise SystemExit(exc.returncode) from exc
    stamp.write_text(current_hash + "\n", encoding="utf-8")


def ensure_database(root: Path, python: Path) -> None:
    probe = (
        "from pathlib import Path\n"
        "from backend.quant_pro.database import get_db_path\n"
        "path = Path(get_db_path())\n"
        "print(path)\n"
        "raise SystemExit(0 if path.exists() else 2)\n"
    )
    result = run([python, "-c", probe], cwd=root, check=False)
    if result.returncode == 0:
        print("Market database found.")
        return

    print("Market database is missing. Downloading the bundled database...")
    run([python, "setup_data.py"], cwd=root)


def run_preflight(root: Path, python: Path) -> None:
    print("Running launch preflight...")
    try:
        run([python, "-m", "scripts.ops.windows_preflight"], cwd=root)
    except subprocess.CalledProcessError as exc:
        print("\nPreflight failed. Fix the issue above, then launch again.")
        raise SystemExit(exc.returncode) from exc


def launch_dashboard(root: Path, python: Path, *, terminal: bool = False) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("NEPSE_LAUNCHED_FROM_HELPER", platform.system())
    module = "apps.tui.dashboard_tui" if terminal else "apps.desktop.dashboard"
    if not terminal:
        probe = subprocess.run(
            [str(python), "-c", "import tkinter; print(tkinter.TkVersion)"],
            cwd=str(root),
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode:
            hint = "Install the matching Tk package (for example, python3-tk on Debian/Ubuntu) and launch again."
            raise SystemExit(f"Tkinter is unavailable in {python}. {hint}\n{probe.stderr.strip()}")
    label = "Textual terminal" if terminal else "desktop dashboard"
    print(f"\nLaunching NEPSE Quant {label}...\n")
    command = [str(python), "-m", module]
    if os.name == "nt" and not terminal:
        log = root / "data" / "runtime" / "logs" / "desktop-launch.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as output:
            subprocess.Popen(
                command,
                cwd=str(root),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
        return 0
    return subprocess.run(command, cwd=str(root), env=env, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch NEPSE Quant")
    parser.add_argument("--tui", action="store_true", help="launch the optional terminal interface")
    parser.add_argument("--install-desktop", action="store_true", help="install a Linux application-menu shortcut for this checkout")
    parser.add_argument("--linux-launch-info", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--venv-directory", default=VENV_DIRNAME, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = repo_root()
    if args.install_desktop:
        if not sys.platform.startswith("linux"):
            raise SystemExit("The application-menu shortcut is available on Linux only.")
        print(install_linux_shortcut(root))
        return 0
    if args.linux_launch_info:
        python, venv_dir = select_linux_runtime(root)
        print(f"{python}\t{venv_dir}")
        return 0
    os.chdir(root)
    ensure_supported_python()
    python = ensure_virtualenv(root, args.venv_directory)
    ensure_requirements(root, python)
    ensure_database(root, python)
    run_preflight(root, python)
    return launch_dashboard(root, python, terminal=args.tui)


if __name__ == "__main__":
    raise SystemExit(main())
