#!/usr/bin/env python3
"""Provision a uv-managed virtual environment for staging-sync usage."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
import shlex


sys.dont_write_bytecode = True

DEFAULT_VENV_NAME = ".venv"


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def locate_uv(explicit: str | None) -> str:
    if explicit:
        uv_path = shutil.which(explicit) if not Path(explicit).exists() else explicit
    else:
        uv_path = shutil.which("uv")
    if not uv_path:
        fail("uv executable not found. Install uv or provide --uv-path.")
    return uv_path


def venv_python_path(venv_path: Path) -> Path:
    bin_dir = venv_path / "bin"
    if (bin_dir / "python").exists():
        return bin_dir / "python"
    scripts_dir = venv_path / "Scripts"
    if (scripts_dir / "python.exe").exists():
        return scripts_dir / "python.exe"
    fail(f"Unable to locate Python interpreter in virtual environment at {venv_path}.")


def run_uv(uv_path: str, *args: str) -> None:
    cmd = [uv_path, *args]
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        fail(f"uv command failed: {' '.join(cmd)}")


def get_site_packages(python_exe: Path) -> Path:
    code = "import sysconfig; print(sysconfig.get_path('purelib'))"
    result = subprocess.run(
        [str(python_exe), "-c", code],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        fail(
            "Unable to determine site-packages directory inside the virtual environment."
        )
    path = Path(result.stdout.strip())
    if not path:
        fail("site-packages path is empty for the virtual environment.")
    return path


def install_stage_sync(python_in_venv: Path, venv_path: Path, project_root: Path) -> None:
    module_source = project_root / "stage_sync.py"
    if not module_source.exists():
        fail(f"stage_sync.py not found in {project_root}.")

    site_packages = get_site_packages(python_in_venv)
    site_packages.mkdir(parents=True, exist_ok=True)
    shutil.copy2(module_source, site_packages / "stage_sync.py")

    bin_dir = venv_path / "bin"
    if not bin_dir.exists():
        bin_dir = venv_path / "Scripts"

    bin_dir.mkdir(parents=True, exist_ok=True)
    script_path = bin_dir / "stage-sync"
    script_contents = (
        "#!/usr/bin/env python3\n"
        "from stage_sync import main\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    script_path.write_text(script_contents)
    script_path.chmod(0o755)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or refresh a uv virtual environment in the current directory. "
            "Optionally recreate it with stage-sync installed and launch a staging shell."
        )
    )
    parser.add_argument(
        "staging_target",
        nargs="?",
        help=(
            "Directory to open in a new terminal when using --spawn-terminal. "
            "Required whenever --spawn-terminal is set."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing virtual environment if one already exists at the target path.",
    )
    parser.add_argument(
        "--uv-path",
        help="Path to the uv executable if it is not on PATH.",
    )
    parser.add_argument(
        "--spawn-terminal",
        action="store_true",
        help=(
            "Recreate the virtual environment, install stage-sync into it, and "
            "spawn a new Terminal window rooted at the staging target with the "
            "environment activated."
        ),
    )
    return parser


def activation_script(venv_path: Path) -> Path:
    candidate = venv_path / "bin" / "activate"
    if candidate.exists():
        return candidate
    candidate = venv_path / "Scripts" / "activate"
    if candidate.exists():
        return candidate
    fail(f"Unable to locate activation script inside {venv_path}.")


def spawn_staging_shell(staging_dir: Path, venv_path: Path) -> None:
    if sys.platform != "darwin":
        fail("--spawn-terminal is currently supported only on macOS (darwin).")

    activation = activation_script(venv_path)
    commands = [
        f"cd {shlex.quote(str(staging_dir))}",
        "source ~/.zshrc",
        f"source {shlex.quote(str(activation))}",
    ]
    joined = "; ".join(commands)
    applescript_command = joined.replace("\\", "\\\\").replace("\"", "\\\"")
    script = dedent(
        f"""
        tell application "Terminal"
            activate
            do script "{applescript_command}"
        end tell
        """
    ).strip()

    result = subprocess.run(["osascript", "-e", script], text=True)
    if result.returncode != 0:
        fail("Failed to spawn Terminal window via osascript.")


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    current_dir = Path.cwd()
    venv_path = current_dir / DEFAULT_VENV_NAME
    project_root = Path(__file__).resolve().parent

    uv_path = locate_uv(args.uv_path)

    if args.spawn_terminal:
        staging_target = args.staging_target
        if not staging_target:
            fail("--spawn-terminal requires a staging_target path argument.")
        staging_target_path = Path(staging_target).expanduser().resolve()
        staging_target_path.mkdir(parents=True, exist_ok=True)

        if venv_path.exists():
            shutil.rmtree(venv_path)

        run_uv(uv_path, "venv", str(venv_path))
        python_in_venv = venv_python_path(venv_path)
        install_stage_sync(python_in_venv, venv_path, project_root)

        spawn_staging_shell(staging_target_path, venv_path)
        print("Virtual environment refreshed and stage-sync installed.")
        print(f"Location: {venv_path}")
        return

    if venv_path.exists():
        if args.force:
            shutil.rmtree(venv_path)
        else:
            message = dedent(
                f"""
                Virtual environment already exists at {venv_path}.
                Use --force to recreate it or --spawn-terminal to refresh with stage-sync.
                """
            ).strip()
            print(message)
            return

    run_uv(uv_path, "venv", str(venv_path))
    print("Virtual environment ready.")
    print(f"Location: {venv_path}")


if __name__ == "__main__":
    main()
