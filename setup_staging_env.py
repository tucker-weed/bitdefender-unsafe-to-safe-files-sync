#!/usr/bin/env python3
"""Provision a uv-managed virtual environment for staging-sync usage."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

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


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a uv virtual environment inside a staging directory and install "
            "the staging sync utility into it."
        )
    )
    parser.add_argument(
        "staging_dir",
        help="Directory that should contain the virtual environment (will be created if needed).",
    )
    parser.add_argument(
        "--venv-name",
        default=DEFAULT_VENV_NAME,
        help=f"Name of the virtual environment directory (default: {DEFAULT_VENV_NAME}).",
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
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    staging_dir = Path(args.staging_dir).expanduser().resolve()
    venv_path = staging_dir / args.venv_name
    project_root = Path(__file__).resolve().parent

    uv_path = locate_uv(args.uv_path)

    staging_dir.mkdir(parents=True, exist_ok=True)

    # Ensure setuptools metadata directory exists away from project root for AV compatibility
    build_dir = project_root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    if venv_path.exists():
        if not args.force:
            fail(
                f"Virtual environment already exists at {venv_path}. "
                "Use --force to replace it."
            )
        shutil.rmtree(venv_path)

    run_uv(uv_path, "venv", str(venv_path))

    python_in_venv = venv_python_path(venv_path)
    run_uv(uv_path, "pip", "install", "--python", str(python_in_venv), str(project_root))

    print("Virtual environment ready.")
    print(f"Location: {venv_path}")
    print("Activate it and run 'stage-sync --help' to get started.")


if __name__ == "__main__":
    main()
