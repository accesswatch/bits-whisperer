"""GitHub OAuth Device Flow authentication for desktop applications.

Implements RFC 8628 (Device Authorization Grant) against GitHub's OAuth
endpoints.  This allows users to authenticate by opening a browser and
entering a short code — no Copilot CLI ``auth login`` step required.

The resulting ``gho_`` / ``ghu_`` access token is passed to the SDK's
``CopilotClient({"github_token": token})`` option.

Usage::

    flow = GitHubDeviceFlow(client_id="Iv1.xxxx")
    info = flow.request_device_code()
    # Show info.user_code to the user, open info.verification_uri
    token = flow.poll_for_token(info)
    # Store token and pass to CopilotClient

Architecture
------------
Desktop App → GitHub Device Flow → ``gho_`` token → SDK → CLI (server)
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub endpoints
# ---------------------------------------------------------------------------
_DEVICE_CODE_URL: Final[str] = "https://github.com/login/device/code"
_TOKEN_URL: Final[str] = "https://github.com/login/oauth/access_token"  # noqa: S105

# Default scope for GitHub Copilot access
DEFAULT_SCOPES: Final[list[str]] = ["copilot"]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceCodeInfo:
    """Response from GitHub's device code endpoint.

    Attributes:
        device_code: Server-side device verification code (40 chars).
        user_code: Human-readable code the user enters in the browser.
        verification_uri: URL where the user enters the code.
        expires_in: Seconds until codes expire (default 900 = 15 min).
        interval: Minimum seconds between token poll requests.
    """

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DeviceFlowError(Exception):
    """Base error for the GitHub Device Flow."""


class DeviceFlowExpiredError(DeviceFlowError):
    """The device code expired before the user authorized."""


class DeviceFlowDeniedError(DeviceFlowError):
    """The user denied the authorization request."""


class DeviceFlowCancelledError(DeviceFlowError):
    """The flow was cancelled by the application."""


class DeviceFlowDisabledError(DeviceFlowError):
    """Device flow is not enabled for this OAuth App."""


# ---------------------------------------------------------------------------
# Device Flow implementation
# ---------------------------------------------------------------------------


class GitHubDeviceFlow:
    """Implements the GitHub OAuth Device Flow (RFC 8628).

    This flow is ideal for desktop applications and is the same mechanism
    used by the GitHub CLI (``gh auth login``):

    1. Request a device code from GitHub.
    2. Show the user a short code and open their browser.
    3. Poll GitHub until the user enters the code and authorizes.
    4. Receive an access token (``gho_`` prefix).

    No ``client_secret`` is required for the device flow.

    Args:
        client_id: The OAuth App client ID from github.com/settings/applications.
        scopes: OAuth scopes to request (default: ``['copilot']``).
    """

    def __init__(
        self,
        client_id: str,
        scopes: list[str] | None = None,
    ) -> None:
        if not client_id:
            raise ValueError(
                "client_id is required for OAuth Device Flow. "
                "Register a GitHub OAuth App at: "
                "https://github.com/settings/applications/new"
            )
        self._client_id = client_id
        self._scopes = scopes or list(DEFAULT_SCOPES)

    # ------------------------------------------------------------------ #
    # Step 1: Request device codes                                         #
    # ------------------------------------------------------------------ #

    def request_device_code(self) -> DeviceCodeInfo:
        """Request device and user verification codes from GitHub.

        Returns:
            DeviceCodeInfo with the user code, verification URI, etc.

        Raises:
            DeviceFlowError: If the request fails.
            DeviceFlowDisabledError: If device flow is not enabled for the app.
        """
        data = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "scope": " ".join(self._scopes),
            }
        ).encode()

        req = urllib.request.Request(
            _DEVICE_CODE_URL,
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        logger.info(
            "Requesting device code from GitHub (client_id=%s..., scopes=%s)",
            self._client_id[:8],
            self._scopes,
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
                error = error_body.get("error", "")
                desc = error_body.get("error_description", str(exc))
            except Exception:
                error = ""
                desc = str(exc)
            logger.error("Device code request HTTP error: %s — %s", error, desc)
            if error == "device_flow_disabled":
                raise DeviceFlowDisabledError(
                    "Device flow is not enabled for this OAuth App. "
                    "Enable it in the app settings at: "
                    "https://github.com/settings/applications"
                ) from exc
            raise DeviceFlowError(f"Failed to request device code: {desc}") from exc
        except Exception as exc:
            logger.exception("Failed to request device code: %s", exc)
            raise DeviceFlowError(f"Failed to request device code: {exc}") from exc

        if "error" in body:
            error = body["error"]
            desc = body.get("error_description", "")
            logger.error("Device code request error: %s — %s", error, desc)
            if error == "device_flow_disabled":
                raise DeviceFlowDisabledError(
                    "Device flow is not enabled for this OAuth App. "
                    "Enable it at: https://github.com/settings/applications"
                )
            raise DeviceFlowError(f"GitHub error: {error} — {desc}")

        info = DeviceCodeInfo(
            device_code=body["device_code"],
            user_code=body["user_code"],
            verification_uri=body["verification_uri"],
            expires_in=body.get("expires_in", 900),
            interval=body.get("interval", 5),
        )
        logger.info(
            "Device code received: user_code=%s, uri=%s, expires_in=%ds",
            info.user_code,
            info.verification_uri,
            info.expires_in,
        )
        return info

    # ------------------------------------------------------------------ #
    # Step 3: Poll for the access token                                    #
    # ------------------------------------------------------------------ #

    def poll_for_token(
        self,
        device_info: DeviceCodeInfo,
        *,
        on_status: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Poll GitHub until the user authorizes or the code expires.

        This is a blocking call — run it in a background thread.

        Args:
            device_info: The ``DeviceCodeInfo`` from :meth:`request_device_code`.
            on_status: Optional callback with human-readable status updates.
            cancel_event: Optional ``threading.Event`` to abort polling.

        Returns:
            The access token string (``gho_...``).

        Raises:
            DeviceFlowExpiredError: If codes expired before authorization.
            DeviceFlowDeniedError: If the user clicked Cancel in the browser.
            DeviceFlowCancelledError: If ``cancel_event`` was set.
            DeviceFlowError: For unexpected errors.
        """
        interval = device_info.interval
        deadline = time.monotonic() + device_info.expires_in

        logger.info(
            "Starting token polling (interval=%ds, expires_in=%ds)",
            interval,
            device_info.expires_in,
        )

        while time.monotonic() < deadline:
            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                logger.info("Device flow cancelled by user")
                raise DeviceFlowCancelledError("Authentication cancelled")

            # Wait for the required interval (respects cancel_event)
            if cancel_event:
                cancel_event.wait(interval)
                if cancel_event.is_set():
                    raise DeviceFlowCancelledError("Authentication cancelled")
            else:
                time.sleep(interval)

            # Poll GitHub for the token
            data = urllib.parse.urlencode(
                {
                    "client_id": self._client_id,
                    "device_code": device_info.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                }
            ).encode()

            req = urllib.request.Request(
                _TOKEN_URL,
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                logger.warning("Token poll request failed: %s", exc)
                if on_status:
                    on_status(f"Network error, retrying... ({exc})")
                continue

            # Success — got a token!
            if "access_token" in body:
                token = body["access_token"]
                token_type = body.get("token_type", "bearer")
                scope = body.get("scope", "")
                logger.info(
                    "Access token received (type=%s, scope=%s, prefix=%s...)",
                    token_type,
                    scope,
                    token[:7] if len(token) > 7 else "***",
                )
                if on_status:
                    on_status("Authorized!")
                return token

            # Handle error responses
            error = body.get("error", "")

            if error == "authorization_pending":
                remaining = max(0, int(deadline - time.monotonic()))
                logger.debug("Authorization pending, %ds remaining", remaining)
                if on_status:
                    on_status(f"Waiting for authorization... ({remaining}s remaining)")

            elif error == "slow_down":
                # GitHub is rate-limiting us — back off
                interval += 5
                logger.info("Received slow_down, increasing interval to %ds", interval)
                if on_status:
                    on_status(f"Rate limited — waiting {interval}s between checks")

            elif error == "expired_token":
                logger.warning("Device code expired")
                raise DeviceFlowExpiredError(
                    "The authorization code has expired. Please try again."
                )

            elif error == "access_denied":
                logger.warning("User denied authorization")
                raise DeviceFlowDeniedError(
                    "Authorization was denied. You may have clicked Cancel " "in the browser."
                )

            elif error == "incorrect_client_credentials":
                logger.error("Invalid client_id for device flow")
                raise DeviceFlowError("Invalid OAuth App client ID. Check the configuration.")

            elif error == "incorrect_device_code":
                logger.error("Invalid device_code")
                raise DeviceFlowError("Invalid device code. This is unexpected — please try again.")

            elif error == "device_flow_disabled":
                logger.error("Device flow is disabled for this OAuth App")
                raise DeviceFlowDisabledError(
                    "Device flow is disabled for this OAuth App. "
                    "Enable it in the app's settings on GitHub."
                )

            else:
                desc = body.get("error_description", error)
                logger.error("Unexpected token poll error: %s — %s", error, desc)
                raise DeviceFlowError(f"GitHub error: {desc}")

        # Expired after the loop
        logger.warning("Device flow timed out after %ds", device_info.expires_in)
        raise DeviceFlowExpiredError("The authorization code has expired. Please try again.")

    # ------------------------------------------------------------------ #
    # Token validation helper                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_token(token: str) -> dict[str, str] | None:
        """Validate a GitHub token by calling the user endpoint.

        Args:
            token: The access token to validate.

        Returns:
            Dict with ``login`` and ``name`` if valid, or None.
        """
        if not token:
            return None

        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "BITS-Whisperer",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = {
                    "login": data.get("login", ""),
                    "name": data.get("name", ""),
                }
                logger.info(
                    "Token validated: login=%s, name=%s",
                    result["login"],
                    result["name"],
                )
                return result
        except urllib.error.HTTPError as exc:
            logger.warning("Token validation failed: HTTP %d", exc.code)
            return None
        except Exception as exc:
            logger.warning("Token validation failed: %s", exc)
            return None
