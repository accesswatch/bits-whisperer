"""Build script for BITS Whisperer installer.

Usage
-----
    python build_installer.py              # Standard build from current venv
    python build_installer.py --lean       # Build in a clean venv (smallest output)
    python build_installer.py --onefile    # Single-file .exe (slower startup)

This script:
1. Optionally creates a clean venv with only core dependencies (--lean).
2. Verifies PyInstaller is installed.
3. Runs the ``bits_whisperer.spec`` through PyInstaller.
4. Produces a distributable folder in ``dist/BITS Whisperer/``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path


def _create_lean_venv(root: Path) -> Path:
    """Create a temporary venv with only core dependencies.

    This ensures PyInstaller never sees provider SDKs, ML stacks, or
    dev tools — resulting in a dramatically smaller bundle.

    Args:
        root: Project root directory.

    Returns:
        Path to the venv's Python executable.
    """
    venv_dir = root / ".build_venv"
    if venv_dir.exists():
        print(f"  Removing old build venv: {venv_dir}")
        shutil.rmtree(venv_dir, ignore_errors=True)

    print(f"  Creating clean build venv: {venv_dir}")
    venv.create(str(venv_dir), with_pip=True, clear=True)

    # Locate the Python executable inside the venv
    if sys.platform == "win32":
        python = venv_dir / "Scripts" / "python.exe"
    else:
        python = venv_dir / "bin" / "python"

    if not python.exists():
        print(f"ERROR: Could not find Python in venv at {python}")
        sys.exit(1)

    # Install only core deps + pyinstaller
    print("  Installing core dependencies into build venv...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet",
         "-r", str(root / "requirements.txt"),
         "pyinstaller"],
        check=True,
    )
    # Install the project itself (editable) so PyInstaller can find it
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet",
         "--no-deps", "-e", str(root)],
        check=True,
    )
    print("  Build venv ready.")
    return python


def main() -> None:
    """Run the PyInstaller build."""
    parser = argparse.ArgumentParser(description="Build BITS Whisperer installer")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Create a single-file executable instead of a folder",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous build artefacts before building",
    )
    parser.add_argument(
        "--lean",
        action="store_true",
        help=(
            "Build in a temporary clean venv with only core dependencies. "
            "This produces the smallest possible output (~40 MB instead of 1+ GB) "
            "by ensuring no provider SDKs or ML libraries are bundled."
        ),
    )
    args = parser.parse_args()

    root = Path(__file__).parent
    spec_file = root / "bits_whisperer.spec"

    if not spec_file.exists():
        print("ERROR: bits_whisperer.spec not found in project root.")
        sys.exit(1)

    # Determine which Python to use
    python_exe = sys.executable

    if args.lean:
        print("=" * 60)
        print("  LEAN BUILD MODE")
        print("  Creating clean venv with core dependencies only...")
        print("=" * 60)
        python_exe = str(_create_lean_venv(root))
    else:
        # Verify PyInstaller is available in current env
        try:
            import PyInstaller  # noqa: F401
        except ImportError:
            print("ERROR: PyInstaller is not installed.")
            print("       pip install pyinstaller")
            sys.exit(1)

    cmd: list[str] = [
        str(python_exe),
        "-m",
        "PyInstaller",
    ]

    if args.onefile:
        # Override spec with direct command for one-file build
        cmd.extend([
            "--onefile",
            "--windowed",
            "--name",
            "BITS Whisperer",
            str(root / "src" / "bits_whisperer" / "__main__.py"),
        ])
    else:
        cmd.append(str(spec_file))

    if args.clean:
        cmd.append("--clean")

    cmd.extend(["--distpath", str(root / "dist"), "--workpath", str(root / "build")])

    print(f"Building BITS Whisperer...")
    print(f"  Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=str(root))

    if result.returncode == 0:
        print()
        print("=" * 60)
        print("  BUILD SUCCESSFUL!")
        if args.onefile:
            print(f"  Output: dist/BITS Whisperer.exe")
        else:
            print(f"  Output: dist/BITS Whisperer/")
        if args.lean:
            print()
            print("  Lean build — provider SDKs NOT bundled.")
            print("  They will be installed on-demand at runtime")
            print("  via the SDK installer when users first enable")
            print("  a provider.")
        print("=" * 60)
    else:
        print()
        print("BUILD FAILED — see output above for errors.")
        sys.exit(1)

    # Clean up lean build venv
    if args.lean:
        venv_dir = root / ".build_venv"
        if venv_dir.exists():
            print(f"Cleaning up build venv: {venv_dir}")
            shutil.rmtree(venv_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
