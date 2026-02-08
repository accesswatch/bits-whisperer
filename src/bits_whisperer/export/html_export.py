"""HTML export formatter."""

from __future__ import annotations

from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult
from bits_whisperer.export.base import ExportFormatter, format_timestamp

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transcript: {title}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.7; max-width: 800px; margin: 2rem auto; padding: 0 1rem;
    color: #222; background: #fafafa;
  }}
  h1 {{ font-size: 1.5rem; border-bottom: 2px solid #0078d4; padding-bottom: .5rem; }}
  .meta {{ color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .segment {{ margin-bottom: 1rem; }}
  .timestamp {{ color: #0078d4; font-size: 0.85rem; font-family: monospace; }}
  .speaker {{ font-weight: bold; color: #333; }}
  .confidence {{ color: #888; font-size: 0.8rem; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #ddd; background: #1e1e1e; }}
    h1 {{ border-color: #4fc3f7; }}
    .timestamp {{ color: #4fc3f7; }}
    .speaker {{ color: #eee; }}
    .meta {{ color: #aaa; }}
  }}
</style>
</head>
<body>
<h1>Transcript: {title}</h1>
<div class="meta">
  <p>Provider: {provider} | Model: {model} | Language: {language}
  | Duration: {duration} | Date: {date}</p>
</div>
<div class="transcript">
{segments_html}
</div>
</body>
</html>
"""


class HTMLFormatter(ExportFormatter):
    """Export transcript as a styled HTML document."""

    @property
    def format_id(self) -> str:
        return "html"

    @property
    def display_name(self) -> str:
        return "HTML Document (.html)"

    @property
    def file_extension(self) -> str:
        return ".html"

    def export(
        self,
        result: TranscriptionResult,
        output_path: str | Path,
        include_timestamps: bool = True,
        include_speakers: bool = True,
        include_confidence: bool = False,
    ) -> Path:
        """Export transcript as HTML.

        Args:
            result: Transcription data.
            output_path: Destination file path.
            include_timestamps: Include timestamp spans.
            include_speakers: Include speaker labels.
            include_confidence: Show confidence badges.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_path)
        seg_parts: list[str] = []

        if result.segments:
            for seg in result.segments:
                parts: list[str] = ['<div class="segment">']
                if include_timestamps:
                    parts.append(
                        f'<span class="timestamp">[{format_timestamp(seg.start)} — '
                        f"{format_timestamp(seg.end)}]</span> "
                    )
                if include_speakers and seg.speaker:
                    parts.append(f'<span class="speaker">{_esc(seg.speaker)}:</span> ')
                parts.append(f"<span>{_esc(seg.text)}</span>")
                if include_confidence and seg.confidence > 0:
                    parts.append(f' <span class="confidence">({seg.confidence:.0%})</span>')
                parts.append("</div>")
                seg_parts.append("".join(parts))
        else:
            seg_parts.append(f"<p>{_esc(result.full_text)}</p>")

        html = _HTML_TEMPLATE.format(
            title=_esc(result.audio_file),
            provider=_esc(result.provider),
            model=_esc(result.model),
            language=_esc(result.language),
            duration=format_timestamp(result.duration_seconds),
            date=_esc(result.created_at),
            segments_html="\n".join(seg_parts),
        )
        output_path.write_text(html, encoding="utf-8")
        return output_path


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
