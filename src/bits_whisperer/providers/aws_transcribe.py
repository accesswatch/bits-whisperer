"""Amazon Transcribe provider adapter."""

from __future__ import annotations

import contextlib
import logging
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)

logger = logging.getLogger(__name__)


class AWSTranscribeProvider(TranscriptionProvider):
    """Cloud transcription via Amazon Transcribe.

    Amazon Transcribe is a highly accurate, fully managed ASR service.
    Supports custom vocabulary, content redaction, automatic language
    identification, and speaker diarization for up to 10 speakers.

    Pricing: ~$0.024/min (standard), ~$0.012/min (batch).
    Free tier: 60 minutes/month for 12 months.
    """

    RATE_PER_MINUTE: float = 0.024

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="Amazon Transcribe",
            provider_type="cloud",
            supports_streaming=True,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=2000,
            supported_languages=["auto", "en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="60 minutes/month free for 12 months.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate AWS credentials.

        For AWS, api_key is expected as 'ACCESS_KEY:SECRET_KEY:REGION'.
        """
        try:
            parts = api_key.split(":")
            if len(parts) < 3:
                return False
            import boto3

            client = boto3.client(
                "transcribe",
                aws_access_key_id=parts[0],
                aws_secret_access_key=parts[1],
                region_name=parts[2],
            )
            client.list_transcription_jobs(MaxResults=1)
            return True
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        return (duration_seconds / 60.0) * self.RATE_PER_MINUTE

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
        """Transcribe audio via Amazon Transcribe.

        Uses the start_transcription_job API with file upload to S3
        or direct streaming. For simplicity this implementation uses
        the synchronous `start_medical_transcription_job` pattern
        with polling.

        api_key format: 'ACCESS_KEY:SECRET_KEY:REGION[:BUCKET]'
        """
        try:
            import json

            import boto3
        except ImportError:
            raise RuntimeError("boto3 package not installed. pip install boto3") from None

        if not api_key:
            raise RuntimeError(
                "AWS credentials are required. " "Format: ACCESS_KEY:SECRET_KEY:REGION"
            )

        parts = api_key.split(":")
        if len(parts) < 3:
            raise RuntimeError(
                "Invalid AWS credentials format. " "Expected: ACCESS_KEY:SECRET_KEY:REGION"
            )

        access_key, secret_key, region = parts[0], parts[1], parts[2]
        bucket = parts[3] if len(parts) > 3 else "bits-whisperer-temp"

        if progress_callback:
            progress_callback(5.0)

        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        transcribe = boto3.client(
            "transcribe",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

        # Ensure bucket exists
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            try:
                if region == "us-east-1":
                    s3.create_bucket(Bucket=bucket)
                else:
                    s3.create_bucket(
                        Bucket=bucket,
                        CreateBucketConfiguration={"LocationConstraint": region},
                    )
            except Exception as exc:
                raise RuntimeError(f"Cannot access or create S3 bucket '{bucket}': {exc}") from exc

        # Upload audio
        file_name = Path(audio_path).name
        s3_key = f"bits-whisperer-uploads/{file_name}"
        logger.info("Uploading %s to S3 bucket %s", file_name, bucket)
        s3.upload_file(audio_path, bucket, s3_key)

        if progress_callback:
            progress_callback(20.0)

        # Start transcription job
        job_name = f"bw-{int(time.time())}-{file_name[:20]}"
        job_params: dict = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": f"s3://{bucket}/{s3_key}"},
            "OutputBucketName": bucket,
        }

        if language != "auto":
            job_params["LanguageCode"] = language.replace("auto", "en-US")
        else:
            job_params["IdentifyLanguage"] = True

        if include_diarization:
            job_params["Settings"] = {
                "ShowSpeakerLabels": True,
                "MaxSpeakerLabels": 10,
            }

        logger.info("Starting Amazon Transcribe job: %s", job_name)
        transcribe.start_transcription_job(**job_params)

        if progress_callback:
            progress_callback(30.0)

        # Poll for completion with timeout
        _MAX_POLLS = 2160  # 3 hours at 5s intervals
        output_uri: str = ""
        try:
            for poll_idx in range(_MAX_POLLS):
                resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
                job_info = resp["TranscriptionJob"]
                status = job_info["TranscriptionJobStatus"]

                if status == "COMPLETED":
                    output_uri = job_info.get("Transcript", {}).get("TranscriptFileUri", "")
                    break
                elif status == "FAILED":
                    reason = job_info.get("FailureReason", "Unknown")
                    raise RuntimeError(f"Amazon Transcribe job failed: {reason}")

                if progress_callback:
                    progress_callback(min(85.0, 30.0 + 55.0 * (poll_idx / _MAX_POLLS)))
                time.sleep(5)
            else:
                raise RuntimeError(
                    "Amazon Transcribe job timed out after 3 hours. "
                    "Check your AWS console for job status."
                )
        except Exception:
            # Clean up S3 upload on failure
            with contextlib.suppress(Exception):
                s3.delete_object(Bucket=bucket, Key=s3_key)
            raise

        if progress_callback:
            progress_callback(85.0)

        # Download results — use the actual output URI from AWS
        output_key: str = ""
        try:
            if output_uri:
                parsed = urllib.parse.urlparse(output_uri)
                # S3 URI path starts with /bucket-name/key...
                path_parts = parsed.path.lstrip("/").split("/", 1)
                output_key = path_parts[1] if len(path_parts) > 1 else f"{job_name}.json"
            else:
                output_key = f"{job_name}.json"

            result_obj = s3.get_object(Bucket=bucket, Key=output_key)
            result_data = json.loads(result_obj["Body"].read().decode("utf-8"))
        except Exception:
            # Clean up S3 upload on failure
            with contextlib.suppress(Exception):
                s3.delete_object(Bucket=bucket, Key=s3_key)
            raise

        # Parse results
        transcripts = result_data.get("results", {}).get("transcripts", [])
        full_text = transcripts[0]["transcript"] if transcripts else ""

        segments: list[TranscriptSegment] = []
        items = result_data.get("results", {}).get("items", [])
        current_text = ""
        current_start = 0.0
        current_end = 0.0
        confidence = 0.0

        for item in items:
            if item["type"] == "pronunciation":
                start = float(item.get("start_time", 0))
                end = float(item.get("end_time", 0))
                word = item["alternatives"][0]["content"]
                confidence = float(item["alternatives"][0].get("confidence", 0))

                if not current_text:
                    current_start = start
                current_text += (" " if current_text else "") + word
                current_end = end

            elif item["type"] == "punctuation":
                current_text += item["alternatives"][0]["content"]

                # End segment on sentence-ending punctuation
                if item["alternatives"][0]["content"] in (".", "!", "?"):
                    segments.append(
                        TranscriptSegment(
                            start=current_start,
                            end=current_end,
                            text=current_text.strip(),
                            confidence=confidence,
                        )
                    )
                    current_text = ""
                    confidence = 0.0

        # Flush remaining
        if current_text.strip():
            segments.append(
                TranscriptSegment(
                    start=current_start,
                    end=current_end,
                    text=current_text.strip(),
                    confidence=confidence,
                )
            )

        # Clean up S3
        try:
            s3.delete_object(Bucket=bucket, Key=s3_key)
            if output_key:
                s3.delete_object(Bucket=bucket, Key=output_key)
        except Exception:
            pass

        if progress_callback:
            progress_callback(100.0)

        detected_lang = result_data.get("results", {}).get("language_code", language)

        return TranscriptionResult(
            job_id="",
            audio_file=file_name,
            provider="aws_transcribe",
            model="Amazon Transcribe",
            language=detected_lang,
            duration_seconds=current_end,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
