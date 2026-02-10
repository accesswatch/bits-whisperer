"""Entry point for BITS Whisperer."""

import atexit
import sys


def _atexit_cleanup() -> None:
    """Last-resort cleanup to remove temp files if normal shutdown was bypassed."""
    import tempfile
    from pathlib import Path

    tmp_dir = Path(tempfile.gettempdir())
    for prefix in ("bw_transcode_", "bw_preprocess_"):
        for p in tmp_dir.glob(f"{prefix}*"):
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass


atexit.register(_atexit_cleanup)


def main() -> None:
    """Launch the BITS Whisperer application."""
    # Prepend isolated site-packages to sys.path BEFORE any provider imports.
    # This ensures on-demand-installed SDKs are discoverable in frozen builds.
    from bits_whisperer.core.sdk_installer import init_sdk_path

    init_sdk_path()

    from bits_whisperer.app import BitsWhispererApp

    app = BitsWhispererApp()
    app.MainLoop()

    # Force-terminate the process to kill any leftover daemon threads
    # (background workers, SDK installers, etc.) that might keep the
    # process alive after the UI has closed.
    sys.exit(0)


if __name__ == "__main__":
    main()
