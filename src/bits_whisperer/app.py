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

    def OnInit(self) -> bool:
        """Called by wxPython on application startup."""
        _setup_logging()
        logger.info("Starting %s", APP_NAME)

        # Log frozen-app status for diagnostics
        from bits_whisperer.core.sdk_installer import is_frozen

        if is_frozen():
            from bits_whisperer.utils.constants import SITE_PACKAGES_DIR

            logger.info("Running as frozen app; isolated site-packages: %s", SITE_PACKAGES_DIR)

        self.SetAppName(APP_NAME)

        # Single-instance check — prevent duplicate processes
        self._instance_checker = wx.SingleInstanceChecker(f"{APP_NAME}-{wx.GetUserId()}")
        if self._instance_checker.IsAnotherRunning():
            wx.MessageBox(
                f"{APP_NAME} is already running.\n\nOnly one instance can run at a time.",
                APP_NAME,
                wx.OK | wx.ICON_INFORMATION,
            )
            return False

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

        # ---- Licence / trial activation gate ----
        from bits_whisperer.core.feature_flags import FeatureFlagService
        from bits_whisperer.core.registration_service import BITS_RegistrationService
        from bits_whisperer.storage.key_store import KeyStore

        key_store = KeyStore()
        feature_flags = FeatureFlagService()
        feature_flags.refresh()
        reg_service = BITS_RegistrationService(key_store, feature_flag_service=feature_flags)

        if reg_service.needs_activation():
            from bits_whisperer.core.beta_service import BetaService
            from bits_whisperer.core.member_verification import MemberVerificationService
            from bits_whisperer.ui.welcome_dialog import (
                WELCOME_EXIT,
                WelcomeDialog,
            )

            beta_service = BetaService(key_store=key_store)
            member_service = MemberVerificationService(key_store=key_store)
            logger.info("No active licence or trial — showing welcome dialog")
            dlg = WelcomeDialog(
                None,
                reg_service,
                beta_service=beta_service,
                member_service=member_service,
                activation_mode=reg_service.activation_mode,
            )
            result = dlg.ShowModal()
            dlg.Destroy()

            if result == WELCOME_EXIT:
                logger.info("User chose to exit from welcome dialog")
                return False

        # Import here to avoid circular imports with wx startup
        from bits_whisperer.ui.main_frame import MainFrame

        frame = MainFrame(None)
        frame.Show()
        self.SetTopWindow(frame)
        return True

    def OnExit(self) -> int:
        """Clean-up on shutdown — release resources to avoid _MEI lock errors.

        In frozen (PyInstaller) builds, lingering file handles or threads
        can prevent the bootloader from removing its temporary directory,
        causing a "Failed to remove temporary directory" warning.  We
        aggressively close logging handlers and run garbage collection to
        release as many resources as possible before the process exits.
        """
        logger.info("Shutting down %s", APP_NAME)

        import gc
        import tempfile
        import threading
        from pathlib import Path

        for t in threading.enumerate():
            if t is not threading.main_thread() and t.daemon:
                logger.debug("Daemon thread still alive at shutdown: %s", t.name)

        # Remove any lingering bw_* temp files from THIS session
        # (safety net in case service.stop() was not called)
        tmp_dir = Path(tempfile.gettempdir())
        for prefix in ("bw_transcode_", "bw_preprocess_"):
            for p in tmp_dir.glob(f"{prefix}*"):
                try:
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass

        # Close all logging file handlers so _MEI files are not locked
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            try:
                handler.close()
                root_logger.removeHandler(handler)
            except Exception:
                pass

        # Force garbage collection to release file handles / DLLs
        gc.collect()

        return 0
