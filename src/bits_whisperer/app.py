"""BITS Whisperer — wx.App subclass and application bootstrap."""

from __future__ import annotations

import logging
import sys

import wx

from bits_whisperer.utils.constants import APP_NAME, DATA_DIR, LOG_PATH

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure file + console logging."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(str(LOG_PATH), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)


class BitsWhispererApp(wx.App):
    """Top-level wx application for BITS Whisperer."""

    def OnInit(self) -> bool:  # noqa: N802 — wx convention
        """Called by wxPython on application startup."""
        _setup_logging()
        logger.info("Starting %s", APP_NAME)

        # Log frozen-app status for diagnostics
        from bits_whisperer.core.sdk_installer import is_frozen

        if is_frozen():
            from bits_whisperer.utils.constants import SITE_PACKAGES_DIR

            logger.info("Running as frozen app; isolated site-packages: %s", SITE_PACKAGES_DIR)

        self.SetAppName(APP_NAME)

        # First-run setup wizard
        from bits_whisperer.ui.setup_wizard import SetupWizard, needs_wizard

        if needs_wizard():
            logger.info("First run detected — launching setup wizard")
            wizard = SetupWizard(None)
            wizard.ShowModal()
            wizard.Destroy()

        # Check and install required external dependencies (e.g. ffmpeg)
        from bits_whisperer.core.dependency_checker import check_and_install_dependencies

        dep_status = check_and_install_dependencies(parent_window=None)
        for dep, ok in dep_status.items():
            if not ok:
                logger.warning("Dependency '%s' is not available", dep)

        # Import here to avoid circular imports with wx startup
        from bits_whisperer.ui.main_frame import MainFrame

        frame = MainFrame(None)
        frame.Show()
        self.SetTopWindow(frame)
        return True

    def OnExit(self) -> int:  # noqa: N802
        """Clean-up on shutdown."""
        logger.info("Shutting down %s", APP_NAME)
        return 0
