"""Auphonic cloud audio post-production and transcription provider.

Auphonic provides professional audio post-production (leveling, loudness
normalization, noise reduction, filtering) with built-in speech recognition.
This adapter uses the Auphonic JSON API to upload audio, apply audio
algorithms, run speech recognition, and download the results.

API Reference: https://auphonic.com/help/api/
Authentication: https://auphonic.com/help/api/authentication.html
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auphonic API constants
# ---------------------------------------------------------------------------
API_BASE = "https://auphonic.com/api"
SIMPLE_API = f"{API_BASE}/simple/productions.json"
PRODUCTIONS_URL = f"{API_BASE}/productions.json"
USER_URL = f"{API_BASE}/user.json"
INFO_ALGORITHMS_URL = f"{API_BASE}/info/algorithms.json"
INFO_SERVICES_URL = f"{API_BASE}/info/service_types.json"
INFO_OUTPUT_FILES_URL = f"{API_BASE}/info/output_files.json"

# Production status codes (from /api/info/production_status.json)
STATUS_INCOMPLETE = 0
STATUS_WAITING = 1
STATUS_ERROR = 2
STATUS_DONE = 3
STATUS_AUDIO_PROCESSING = 4
STATUS_ENCODING = 5
STATUS_WAITING_FOR_REVIEW = 6
STATUS_AUDIO_MONO_MIXDOWN = 7
STATUS_AUDIO_SPLITTING = 8
STATUS_AUDIO_UPLOAD = 9
STATUS_AUDIO_OUTRO = 11
STATUS_AUDIO_INTRO = 12
STATUS_SPEECH_RECOGNITION = 13
STATUS_FILE_TRANSFER = 14

# How long to wait between status polls (seconds)
_POLL_INTERVAL = 5
# Maximum number of polls before giving up (5s x 360 = 30 minutes)
_MAX_POLLS = 360

# Auphonic pricing: 2 hours free per month recurring. After that, credits.
# Credits cost roughly $0.01/min for one-time, varies for plans.
RATE_PER_MINUTE_USD = 0.01

# Available speech recognition services in Auphonic
SPEECH_SERVICES = {
    "whisper": "Auphonic Whisper (built-in)",
    "google": "Google Speech-to-Text",
    "amazon": "Amazon Transcribe",
    "speechmatics": "Speechmatics",
}

# Default Auphonic settings (used when no provider_defaults configured)
_DEFAULT_AUPHONIC_SETTINGS: dict[str, Any] = {
    "leveler": True,
    "loudness_normalization": True,
    "loudness_target": -16,
    "noise_reduction": True,
    "noise_reduction_amount": 0,  # 0 = automatic
    "hum_reduction": False,
    "filtering": True,
    "silence_cutting": False,
    "silence_cutting_threshold": -40,
    "filler_cutting": False,
    "cough_cutting": False,
    "crosstalk_detection": False,
    "speech_service": "whisper",
    "output_format": "mp3",
    "output_bitrate": "192",
}


class AuphonicProvider(TranscriptionProvider):
    """Cloud audio post-production and transcription via the Auphonic API.

    Auphonic processes audio through adaptive leveling, loudness
    normalization, noise/hum reduction, and filtering algorithms. It
    also supports built-in speech recognition (Whisper, Google, Amazon,
    Speechmatics) and exports transcripts in SRT, VTT, HTML, and TXT.

    Authentication uses a Bearer API token obtained from:
    https://auphonic.com/accounts/settings/#api-key

    Provider-specific settings (via ``configure()``):
        leveler: bool -- Adaptive leveler (default True)
        loudness_normalization: bool -- Loudness normalisation (default True)
        loudness_target: int -- Target LUFS (default -16)
        noise_reduction: bool -- Auto noise reduction (default True)
        noise_reduction_amount: int -- 0=auto, 1-100 manual (default 0)
        hum_reduction: bool -- Remove 50/60 Hz hum (default False)
        filtering: bool -- High-pass, auto-EQ (default True)
        silence_cutting: bool -- Remove silence (default False)
        silence_cutting_threshold: int -- Threshold dB (default -40)
        filler_cutting: bool -- Remove filler words (default False)
        cough_cutting: bool -- Remove coughs (default False)
        crosstalk_detection: bool -- Detect crosstalk (default False)
        speech_service: str -- whisper|google|amazon|speechmatics
        output_format: str -- mp3|aac|flac|wav|opus|ogg|alac|m4a
        output_bitrate: str -- Bitrate for lossy formats (default 192)
    """

    def __init__(self) -> None:
        """Initialise with default Auphonic settings."""
        self._settings: dict[str, Any] = dict(_DEFAULT_AUPHONIC_SETTINGS)

    def configure(self, settings: dict[str, Any]) -> None:
        """Apply Auphonic-specific production settings.

        Args:
            settings: Dict of Auphonic-specific settings to override.
        """
        for key, value in settings.items():
            if key in _DEFAULT_AUPHONIC_SETTINGS:
                self._settings[key] = value

    def get_capabilities(self) -> ProviderCapabilities:
        """Return Auphonic capabilities.

        Returns:
            ProviderCapabilities describing Auphonic's features.
        """
        return ProviderCapabilities(
            name="Auphonic",
            provider_type="cloud",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=True,
            max_file_size_mb=500,
            supported_languages=["auto", "en", "de", "fr", "es", "it", "pt", "nl", "ja", "zh"],
            rate_per_minute_usd=RATE_PER_MINUTE_USD,
            free_tier_description="2 hours free per month (recurring credits).",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate an API key by querying the user account endpoint.

        Args:
            api_key: Auphonic API token (Bearer token).

        Returns:
            True if the key is valid and returns user data.
        """
        try:
            import httpx

            resp = httpx.get(
                USER_URL,
                headers=_auth_header(api_key),
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status_code") == 200
            return False
        except Exception as exc:
            logger.debug("Auphonic key validation failed: %s", exc)
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate cost for processing audio of the given duration.

        Auphonic provides 2 free hours/month of recurring credits. Cost
        after free tier is approximately $0.01/minute.

        Args:
            duration_seconds: Audio length in seconds.

        Returns:
            Estimated cost in USD (0.0 if within free tier).
        """
        return (duration_seconds / 60.0) * RATE_PER_MINUTE_USD

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via Auphonic with full post-production.

        Creates an Auphonic production with:
        - Adaptive Leveler (enabled)
        - Loudness Normalization (−16 LUFS)
        - Noise Reduction (auto)
        - Filtering (enabled)
        - Auphonic Whisper Speech Recognition

        Args:
            audio_path: Path to audio file.
            language: Language code or 'auto'.
            model: Ignored (Auphonic selects internally).
            include_timestamps: Request timestamped transcript.
            include_diarization: Ignored (not supported by Auphonic).
            api_key: Auphonic API token (Bearer token).
            progress_callback: Optional progress callback (0–100).

        Returns:
            TranscriptionResult with segments and full text.

        Raises:
            RuntimeError: On API errors or processing failures.
        """
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx package not installed. pip install httpx") from None

        if not api_key:
            raise RuntimeError("Auphonic API key is required.")

        headers = _auth_header(api_key)
        audio_file = Path(audio_path)

        if progress_callback:
            progress_callback(5.0)

        # 1. Create the production with algorithms + speech recognition
        logger.info("Creating Auphonic production for: %s", audio_file.name)
        production_data = _build_production_request(
            title=f"BITS Whisperer -- {audio_file.stem}",
            language=language,
            include_timestamps=include_timestamps,
            settings=self._settings,
        )

        prod_resp = httpx.post(
            PRODUCTIONS_URL,
            headers={**headers, "Content-Type": "application/json"},
            content=json.dumps(production_data),
            timeout=30.0,
        )
        _check_response(prod_resp, "create production")
        prod_uuid = prod_resp.json()["data"]["uuid"]
        logger.info("Auphonic production created: %s", prod_uuid)

        if progress_callback:
            progress_callback(15.0)

        # 2. Upload the audio file
        upload_url = f"{API_BASE}/production/{prod_uuid}/upload.json"
        logger.info("Uploading audio to Auphonic: %s", audio_file.name)
        with open(audio_path, "rb") as f:
            upload_resp = httpx.post(
                upload_url,
                headers=headers,
                files={"input_file": (audio_file.name, f, "audio/mpeg")},
                timeout=300.0,  # Large files may take a while
            )
        _check_response(upload_resp, "upload audio")

        if progress_callback:
            progress_callback(30.0)

        # 3. Start the production
        start_url = f"{API_BASE}/production/{prod_uuid}/start.json"
        logger.info("Starting Auphonic production: %s", prod_uuid)
        start_resp = httpx.post(start_url, headers=headers, timeout=30.0)
        _check_response(start_resp, "start production")

        if progress_callback:
            progress_callback(35.0)

        # 4. Poll for completion
        status_url = f"{API_BASE}/production/{prod_uuid}/status.json"
        result_data = _poll_until_done(
            status_url=status_url,
            detail_url=f"{API_BASE}/production/{prod_uuid}.json",
            headers=headers,
            progress_callback=progress_callback,
        )

        if progress_callback:
            progress_callback(90.0)

        # 5. Extract transcript from the production result
        segments, full_text, duration = _extract_transcript(result_data, include_timestamps)

        if progress_callback:
            progress_callback(100.0)

        return TranscriptionResult(
            job_id="",
            audio_file=audio_file.name,
            provider="auphonic",
            model="auphonic-whisper",
            language=language,
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )


# ---------------------------------------------------------------------------
# Auphonic standalone service for audio post-processing only
# ---------------------------------------------------------------------------


class AuphonicService:
    """Standalone Auphonic API client for audio post-production.

    Use this service to process audio through Auphonic's algorithms
    (leveling, loudness normalization, noise reduction, filtering)
    WITHOUT transcription. Useful as a preprocessing step before
    sending audio to another transcription provider.

    Authentication:
        Requires an Auphonic API token (Bearer token).
        Obtain from: https://auphonic.com/accounts/settings/#api-key

    Capabilities:
        - Adaptive Leveler: Corrects level differences between speakers
        - Loudness Normalization: Target LUFS (e.g., -16 for podcasts)
        - Noise & Hum Reduction: Automatic detection and removal
        - Filtering: High-pass, auto-EQ, bandwidth extension
        - Silence & Filler Cutting: Remove silences and filler words
        - Intro/Outro: Automatically prepend/append audio segments
        - Output Formats: MP3, AAC, FLAC, WAV, Opus, Vorbis, ALAC
        - Publishing: Export to Dropbox, SoundCloud, YouTube, FTP, etc.
        - Presets: Save and reuse processing configurations
        - Webhooks: HTTP callbacks when processing completes
        - Speech Recognition: Built-in Whisper or external services
    """

    def __init__(self, api_key: str) -> None:
        """Initialize the Auphonic service.

        Args:
            api_key: Auphonic API token (Bearer token).
        """
        try:
            import httpx

            _ = httpx  # availability check
        except ImportError:
            raise RuntimeError("httpx package not installed. pip install httpx") from None
        self._api_key = api_key
        self._headers = _auth_header(api_key)

    # ------------------------------------------------------------------ #
    # Account
    # ------------------------------------------------------------------ #

    def get_user_info(self) -> dict[str, Any]:
        """Get information about the authenticated Auphonic account.

        Returns:
            Dict with username, credits, email, recharge_date, etc.

        Raises:
            RuntimeError: On API errors.
        """
        import httpx

        resp = httpx.get(USER_URL, headers=self._headers, timeout=15.0)
        _check_response(resp, "get user info")
        return resp.json()["data"]

    def get_remaining_credits(self) -> float:
        """Get remaining credits in hours.

        Returns:
            Available credits in hours (combined recurring + one-time).
        """
        info = self.get_user_info()
        return float(info.get("credits", 0.0))

    # ------------------------------------------------------------------ #
    # Presets
    # ------------------------------------------------------------------ #

    def list_presets(self, minimal: bool = True) -> list[dict[str, Any]]:
        """List all user presets.

        Args:
            minimal: If True, return minimal data only.

        Returns:
            List of preset dicts.
        """
        import httpx

        params = {}
        if minimal:
            params["minimal_data"] = "1"
        resp = httpx.get(
            f"{API_BASE}/presets.json",
            headers=self._headers,
            params=params,
            timeout=15.0,
        )
        _check_response(resp, "list presets")
        return resp.json()["data"]

    def get_preset(self, uuid: str) -> dict[str, Any]:
        """Get details of a specific preset.

        Args:
            uuid: Preset UUID.

        Returns:
            Preset detail dict.
        """
        import httpx

        resp = httpx.get(
            f"{API_BASE}/preset/{uuid}.json",
            headers=self._headers,
            timeout=15.0,
        )
        _check_response(resp, "get preset")
        return resp.json()["data"]

    def create_preset(
        self,
        name: str,
        *,
        algorithms: dict[str, Any] | None = None,
        output_files: list[dict[str, Any]] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> str:
        """Create a new Auphonic preset.

        Args:
            name: Preset name.
            algorithms: Audio algorithm configuration.
            output_files: Output file format specifications.
            settings: Auphonic provider settings dict (used if algorithms is None).

        Returns:
            UUID of the created preset.
        """
        import httpx

        if algorithms is None:
            algorithms = _default_algorithms(settings)
        data: dict[str, Any] = {
            "preset_name": name,
            "algorithms": algorithms,
        }
        if output_files:
            data["output_files"] = output_files

        resp = httpx.post(
            f"{API_BASE}/presets.json",
            headers={**self._headers, "Content-Type": "application/json"},
            content=json.dumps(data),
            timeout=30.0,
        )
        _check_response(resp, "create preset")
        return resp.json()["data"]["uuid"]

    # ------------------------------------------------------------------ #
    # Productions
    # ------------------------------------------------------------------ #

    def list_productions(
        self,
        limit: int = 10,
        offset: int = 0,
        minimal: bool = True,
    ) -> list[dict[str, Any]]:
        """List productions for the authenticated user.

        Args:
            limit: Maximum number of productions to return.
            offset: Pagination offset.
            minimal: If True, return minimal data only.

        Returns:
            List of production dicts.
        """
        import httpx

        params: dict[str, str] = {
            "limit": str(limit),
            "offset": str(offset),
        }
        if minimal:
            params["minimal_data"] = "1"
        resp = httpx.get(
            PRODUCTIONS_URL,
            headers=self._headers,
            params=params,
            timeout=15.0,
        )
        _check_response(resp, "list productions")
        return resp.json()["data"]

    def get_production(self, uuid: str) -> dict[str, Any]:
        """Get full details of a production.

        Args:
            uuid: Production UUID.

        Returns:
            Production detail dict including status, output_files,
            statistics, metadata, etc.
        """
        import httpx

        resp = httpx.get(
            f"{API_BASE}/production/{uuid}.json",
            headers=self._headers,
            timeout=15.0,
        )
        _check_response(resp, "get production")
        return resp.json()["data"]

    def get_production_status(self, uuid: str) -> tuple[int, str]:
        """Get the current status of a production.

        Args:
            uuid: Production UUID.

        Returns:
            Tuple of (status_code, status_string).
        """
        import httpx

        resp = httpx.get(
            f"{API_BASE}/production/{uuid}/status.json",
            headers=self._headers,
            timeout=15.0,
        )
        _check_response(resp, "get production status")
        data = resp.json()["data"]
        return int(data["status"]), str(data["status_string"])

    def process_audio(
        self,
        audio_path: str,
        *,
        title: str = "",
        preset_uuid: str = "",
        algorithms: dict[str, Any] | None = None,
        output_files: list[dict[str, Any]] | None = None,
        loudness_target: int = -16,
        webhook_url: str = "",
        wait_for_completion: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Process an audio file through Auphonic's algorithms.

        This is the main entry point for audio post-production. Creates
        a production, uploads the audio, configures algorithms, starts
        processing, and optionally waits for completion.

        Args:
            audio_path: Path to the local audio file.
            title: Production title (defaults to filename).
            preset_uuid: Use an existing preset instead of algorithms.
            algorithms: Audio algorithm configuration dict.
            output_files: Output format specifications.
            loudness_target: Loudness target in LUFS.
            webhook_url: URL to call when processing completes.
            wait_for_completion: If True, poll until done.
            progress_callback: Progress callback (0–100).

        Returns:
            Production detail dict with results.

        Raises:
            RuntimeError: On API errors or processing failures.
        """
        import httpx

        audio_file = Path(audio_path)
        if not title:
            title = audio_file.stem

        if progress_callback:
            progress_callback(5.0)

        # Build the production request
        data: dict[str, Any] = {"metadata": {"title": title}}
        if preset_uuid:
            data["preset"] = preset_uuid
        else:
            data["algorithms"] = algorithms or _default_algorithms()
        if output_files:
            data["output_files"] = output_files
        else:
            data["output_files"] = [{"format": "mp3", "bitrate": "192"}]
        if webhook_url:
            data["webhook"] = webhook_url

        # Create production
        resp = httpx.post(
            PRODUCTIONS_URL,
            headers={**self._headers, "Content-Type": "application/json"},
            content=json.dumps(data),
            timeout=30.0,
        )
        _check_response(resp, "create production")
        uuid = resp.json()["data"]["uuid"]

        if progress_callback:
            progress_callback(15.0)

        # Upload audio
        upload_url = f"{API_BASE}/production/{uuid}/upload.json"
        with open(audio_path, "rb") as f:
            upload_resp = httpx.post(
                upload_url,
                headers=self._headers,
                files={"input_file": (audio_file.name, f, "audio/mpeg")},
                timeout=300.0,
            )
        _check_response(upload_resp, "upload audio")

        if progress_callback:
            progress_callback(30.0)

        # Start production
        start_resp = httpx.post(
            f"{API_BASE}/production/{uuid}/start.json",
            headers=self._headers,
            timeout=30.0,
        )
        _check_response(start_resp, "start production")

        if progress_callback:
            progress_callback(35.0)

        if not wait_for_completion:
            return {"uuid": uuid, "status": "started"}

        # Poll until done
        result = _poll_until_done(
            status_url=f"{API_BASE}/production/{uuid}/status.json",
            detail_url=f"{API_BASE}/production/{uuid}.json",
            headers=self._headers,
            progress_callback=progress_callback,
        )

        if progress_callback:
            progress_callback(100.0)

        return result

    def download_result(
        self,
        production_uuid: str,
        output_dir: str,
    ) -> list[Path]:
        """Download all output files from a completed production.

        Args:
            production_uuid: UUID of the completed production.
            output_dir: Directory to save downloaded files.

        Returns:
            List of paths to downloaded files.

        Raises:
            RuntimeError: On download errors.
        """
        import httpx

        production = self.get_production(production_uuid)
        output_files = production.get("output_files", [])
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        downloaded: list[Path] = []
        for of in output_files:
            url = of.get("download_url")
            filename = of.get("filename")
            if not url or not filename:
                continue
            try:
                resp = httpx.get(
                    url,
                    headers=self._headers,
                    follow_redirects=True,
                    timeout=120.0,
                )
                resp.raise_for_status()
                dest = out_path / filename
                dest.write_bytes(resp.content)
                downloaded.append(dest)
                logger.info("Downloaded: %s", dest)
            except Exception as exc:
                logger.warning("Failed to download %s: %s", filename, exc)

        return downloaded

    # ------------------------------------------------------------------ #
    # External Services
    # ------------------------------------------------------------------ #

    def list_services(self) -> list[dict[str, Any]]:
        """List all registered external services (Dropbox, FTP, etc.).

        Returns:
            List of service dicts with type, uuid, display_name, etc.
        """
        import httpx

        resp = httpx.get(
            f"{API_BASE}/services.json",
            headers=self._headers,
            timeout=15.0,
        )
        _check_response(resp, "list services")
        return resp.json()["data"]

    # ------------------------------------------------------------------ #
    # Info queries
    # ------------------------------------------------------------------ #

    def get_available_algorithms(self) -> dict[str, Any]:
        """Query all available audio algorithm parameters.

        Returns:
            Dict of algorithm names to parameter details.
        """
        import httpx

        resp = httpx.get(INFO_ALGORITHMS_URL, timeout=15.0)
        _check_response(resp, "get algorithms")
        return resp.json()["data"]

    def get_output_formats(self) -> dict[str, Any]:
        """Query all supported output file formats.

        Returns:
            Dict of format names to bitrate/ending details.
        """
        import httpx

        resp = httpx.get(
            f"{API_BASE}/info/output_files.json",
            timeout=15.0,
        )
        _check_response(resp, "get output formats")
        return resp.json()["data"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _auth_header(api_key: str) -> dict[str, str]:
    """Build the Authorization header for Auphonic API requests.

    Args:
        api_key: Auphonic API token.

    Returns:
        Headers dict with Bearer authorization.
    """
    return {"Authorization": f"Bearer {api_key}"}


def _default_algorithms(
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return audio algorithm configuration from settings.

    Args:
        settings: Auphonic provider settings dict.
            If None, uses _DEFAULT_AUPHONIC_SETTINGS.

    Returns:
        Algorithm configuration dict for the Auphonic API.
    """
    cfg = settings or _DEFAULT_AUPHONIC_SETTINGS
    algorithms: dict[str, Any] = {
        "leveler": cfg.get("leveler", True),
        "normloudness": cfg.get("loudness_normalization", True),
        "loudnesstarget": cfg.get("loudness_target", -16),
        "filtering": cfg.get("filtering", True),
        "denoise": cfg.get("noise_reduction", True),
        "denoiseamount": cfg.get("noise_reduction_amount", 0),
    }
    # Hum reduction (50/60 Hz)
    if cfg.get("hum_reduction", False):
        algorithms["dehum"] = True
    # Silence cutting
    if cfg.get("silence_cutting", False):
        algorithms["remove_silence"] = True
        threshold = cfg.get("silence_cutting_threshold", -40)
        if threshold:
            algorithms["silence_threshold"] = threshold
    # Filler word cutting
    if cfg.get("filler_cutting", False):
        algorithms["remove_filler_words"] = True
    # Cough cutting
    if cfg.get("cough_cutting", False):
        algorithms["remove_coughing"] = True
    # Crosstalk detection
    if cfg.get("crosstalk_detection", False):
        algorithms["crosstalk"] = True
    return algorithms


def _build_production_request(
    title: str,
    language: str = "auto",
    include_timestamps: bool = True,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON body for creating an Auphonic production.

    Configures audio algorithms, speech recognition service, and
    output file formats based on provider settings.

    Args:
        title: Production title.
        language: Language code for speech recognition.
        include_timestamps: Whether to include timestamped output.
        settings: Auphonic provider settings dict.

    Returns:
        Production request dict.
    """
    cfg = settings or _DEFAULT_AUPHONIC_SETTINGS
    out_fmt = cfg.get("output_format", "mp3")
    out_bitrate = cfg.get("output_bitrate", "192")

    data: dict[str, Any] = {
        "metadata": {"title": title},
        "algorithms": _default_algorithms(cfg),
        "output_files": [
            {"format": out_fmt, "bitrate": out_bitrate},
        ],
        "speech_recognition": {
            "language": language if language != "auto" else "en",
        },
    }

    # Configure speech recognition service
    speech_service = cfg.get("speech_service", "whisper")
    if speech_service and speech_service != "whisper":
        data["speech_recognition"]["service"] = speech_service

    # Add subtitle output for timestamps
    if include_timestamps:
        data["output_files"].append({"format": "speech", "ending": "json"})
        data["output_files"].append({"format": "subtitle", "ending": "srt"})
    else:
        data["output_files"].append({"format": "transcript", "ending": "txt"})

    return data


def _check_response(resp: Any, action: str) -> None:
    """Raise RuntimeError if an Auphonic API response indicates failure.

    Args:
        resp: httpx.Response object.
        action: Description of the action for error messages.

    Raises:
        RuntimeError: If the response status is not 2xx.
    """
    if resp.status_code >= 400:
        try:
            body = resp.json()
            msg = body.get("error_message", resp.text[:500])
        except Exception:
            msg = resp.text[:500]
        raise RuntimeError(
            f"Auphonic API error during '{action}': HTTP {resp.status_code} -- {msg}"
        )


def _poll_until_done(
    status_url: str,
    detail_url: str,
    headers: dict[str, str],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Poll the Auphonic production status until done or error.

    Args:
        status_url: URL for the status endpoint.
        detail_url: URL for the full production detail endpoint.
        headers: Authorization headers.
        progress_callback: Optional progress callback.

    Returns:
        Full production detail dict when done.

    Raises:
        RuntimeError: If the production fails or times out.
    """
    import httpx

    for i in range(_MAX_POLLS):
        time.sleep(_POLL_INTERVAL)

        try:
            resp = httpx.get(status_url, headers=headers, timeout=15.0)
            if resp.status_code != 200:
                continue
            status_data = resp.json().get("data", {})
            status = status_data.get("status", STATUS_INCOMPLETE)
            status_str = status_data.get("status_string", "Unknown")
        except Exception as exc:
            logger.debug("Poll error: %s", exc)
            continue

        logger.debug("Auphonic status: %s (%d)", status_str, status)

        # Map processing stages to progress percentages
        if progress_callback:
            progress_map = {
                STATUS_WAITING: 40.0,
                STATUS_AUDIO_UPLOAD: 45.0,
                STATUS_AUDIO_INTRO: 50.0,
                STATUS_AUDIO_PROCESSING: 55.0,
                STATUS_AUDIO_MONO_MIXDOWN: 60.0,
                STATUS_SPEECH_RECOGNITION: 65.0,
                STATUS_ENCODING: 75.0,
                STATUS_FILE_TRANSFER: 80.0,
                STATUS_AUDIO_OUTRO: 80.0,
                STATUS_AUDIO_SPLITTING: 70.0,
            }
            pct = progress_map.get(status, 35.0 + (i / _MAX_POLLS) * 50.0)
            progress_callback(min(pct, 89.0))

        if status == STATUS_DONE:
            # Fetch full production details
            detail_resp = httpx.get(detail_url, headers=headers, timeout=30.0)
            _check_response(detail_resp, "get production result")
            return detail_resp.json()["data"]

        if status == STATUS_ERROR:
            error_msg = status_data.get("error_message", "Unknown error")
            raise RuntimeError(f"Auphonic production failed: {error_msg}")

    raise RuntimeError(
        "Auphonic production timed out after " f"{_MAX_POLLS * _POLL_INTERVAL} seconds."
    )


def _extract_transcript(
    production_data: dict[str, Any],
    include_timestamps: bool,
) -> tuple[list[TranscriptSegment], str, float]:
    """Extract transcript data from a completed Auphonic production.

    Args:
        production_data: Full production detail dict.
        include_timestamps: Whether to extract timestamped segments.

    Returns:
        Tuple of (segments, full_text, duration_seconds).
    """
    import httpx

    duration = float(production_data.get("length", 0.0))
    segments: list[TranscriptSegment] = []
    full_text = ""

    # Try to download the speech recognition JSON result
    output_files = production_data.get("output_files", [])
    speech_json_url = None
    transcript_txt_url = None

    for of in output_files:
        fmt = of.get("format", "")
        ending = of.get("ending", "")
        url = of.get("download_url", "")
        if fmt == "speech" and ending == "json" and url:
            speech_json_url = url
        elif fmt == "transcript" and ending == "txt" and url:
            transcript_txt_url = url

    # Auphonic download URLs are pre-authenticated — no extra headers needed.

    if speech_json_url and include_timestamps:
        try:
            resp = httpx.get(
                speech_json_url,
                follow_redirects=True,
                timeout=60.0,
            )
            if resp.status_code == 200:
                speech_data = resp.json()
                # Auphonic speech JSON format contains segments with
                # start, end, text, and optionally speaker info
                if isinstance(speech_data, list):
                    for item in speech_data:
                        segments.append(
                            TranscriptSegment(
                                start=float(item.get("start", 0.0)),
                                end=float(item.get("end", 0.0)),
                                text=str(item.get("text", "")).strip(),
                            )
                        )
                elif isinstance(speech_data, dict):
                    for item in speech_data.get("segments", []):
                        segments.append(
                            TranscriptSegment(
                                start=float(item.get("start", 0.0)),
                                end=float(item.get("end", 0.0)),
                                text=str(item.get("text", "")).strip(),
                            )
                        )
        except Exception as exc:
            logger.warning("Failed to parse speech JSON: %s", exc)

    # Build full text from segments or download transcript
    if segments:
        full_text = " ".join(seg.text for seg in segments)
    elif transcript_txt_url:
        try:
            resp = httpx.get(
                transcript_txt_url,
                follow_redirects=True,
                timeout=60.0,
            )
            if resp.status_code == 200:
                full_text = resp.text.strip()
        except Exception as exc:
            logger.warning("Failed to download transcript: %s", exc)

    if not full_text and not segments:
        logger.warning("No transcript data found in Auphonic production.")
        full_text = "(No transcript available — speech recognition may not have been enabled.)"

    return segments, full_text, duration
