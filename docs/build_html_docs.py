#!/usr/bin/env python3
"""Build HTML versions of all project Markdown documentation.

Usage:
    python docs/build_html_docs.py

Reads every .md file listed in DOCS and writes a styled .html file to docs/.
Requires the ``markdown`` package (already in requirements.txt).
"""

from __future__ import annotations

from pathlib import Path

import markdown  # type: ignore[import-untyped]
from markdown.extensions.codehilite import CodeHiliteExtension  # type: ignore[import-untyped]
from markdown.extensions.fenced_code import FencedCodeExtension  # type: ignore[import-untyped]
from markdown.extensions.tables import TableExtension  # type: ignore[import-untyped]
from markdown.extensions.toc import TocExtension  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"

# (source_md_path, output_html_name, html_title)
DOCS: list[tuple[Path, str, str]] = [
    (
        DOCS_DIR / "README.md",
        "README.html",
        "BITS Whisperer \u2014 README",
    ),
    (
        DOCS_DIR / "ANNOUNCEMENT.md",
        "ANNOUNCEMENT.html",
        "BITS Whisperer \u2014 Announcement",
    ),
    (
        DOCS_DIR / "PRD.md",
        "PRD.html",
        "BITS Whisperer \u2014 Product Requirements Document",
    ),
    (
        DOCS_DIR / "USER_GUIDE.md",
        "USER_GUIDE.html",
        "BITS Whisperer \u2014 User Guide",
    ),
]

CSS_STYLES = """
  :root {{
    --bg: #ffffff;
    --fg: #1a1a1a;
    --accent: #0969da;
    --border: #d0d7de;
    --code-bg: #f6f8fa;
    --table-alt: #f6f8fa;
    --blockquote: #57606a;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117;
      --fg: #e6edf3;
      --accent: #58a6ff;
      --border: #30363d;
      --code-bg: #161b22;
      --table-alt: #161b22;
      --blockquote: #8b949e;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Helvetica, Arial, sans-serif,
                 "Apple Color Emoji", "Segoe UI Emoji";
    font-size: 16px;
    line-height: 1.6;
    color: var(--fg);
    background: var(--bg);
    max-width: 980px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
  }}
  h1, h2, h3, h4, h5, h6 {{
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
    line-height: 1.25;
  }}
  h1 {{
    font-size: 2em;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.3em;
  }}
  h2 {{
    font-size: 1.5em;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.3em;
  }}
  h3 {{ font-size: 1.25em; }}
  p {{ margin: 0.5em 0 1em; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{
    font-family: "SFMono-Regular", Consolas,
                 "Liberation Mono", Menlo, monospace;
    font-size: 0.875em;
    background: var(--code-bg);
    padding: 0.2em 0.4em;
    border-radius: 6px;
  }}
  pre {{
    background: var(--code-bg);
    padding: 1em;
    border-radius: 6px;
    overflow-x: auto;
    margin: 1em 0;
    line-height: 1.45;
  }}
  pre code {{
    background: none;
    padding: 0;
    font-size: 0.85em;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
  }}
  th, td {{
    border: 1px solid var(--border);
    padding: 0.5em 0.75em;
    text-align: left;
  }}
  th {{
    background: var(--code-bg);
    font-weight: 600;
  }}
  tr:nth-child(even) {{ background: var(--table-alt); }}
  .text-center {{ text-align: center; }}
  .text-right {{ text-align: right; }}
  blockquote {{
    border-left: 4px solid var(--accent);
    padding: 0.5em 1em;
    margin: 1em 0;
    color: var(--blockquote);
  }}
  hr {{
    border: none;
    border-top: 1px solid var(--border);
    margin: 2em 0;
  }}
  ul, ol {{ margin: 0.5em 0 1em 1.5em; }}
  li {{ margin: 0.25em 0; }}
  img {{ max-width: 100%; height: auto; }}
  .toc {{
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1em 1.5em;
    margin: 1em 0 2em;
  }}
  .toc ul {{ list-style: none; margin: 0; padding: 0; }}
  .toc ul ul {{ padding-left: 1.5em; }}
  .toc li {{ margin: 0.25em 0; }}
  strong {{ font-weight: 600; }}
  .footer {{
    margin-top: 3em;
    padding-top: 1em;
    border-top: 1px solid var(--border);
    font-size: 0.85em;
    color: var(--blockquote);
    text-align: center;
  }}
"""

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="docs.css">
</head>
<body>
{body}
<div class="footer">
  Generated from <code>{source}</code> &mdash; BITS Whisperer Documentation
</div>
</body>
</html>
"""


def convert_md_to_html(md_text: str, title: str, source_name: str) -> str:
    """Convert Markdown text to a full styled HTML document."""
    md = markdown.Markdown(
        extensions=[
            TableExtension(),
            FencedCodeExtension(),
            CodeHiliteExtension(css_class="highlight", guess_lang=False),
            TocExtension(permalink=False, toc_depth=3),
        ],
        output_format="html",
    )
    body_html = md.convert(md_text)
    body_html = _replace_table_alignment(body_html)
    # Insert TOC at the top if it has content
    toc_html = getattr(md, "toc", "")
    if toc_html and "<li>" in toc_html:
        toc_section = (
            '<nav class="toc">'
            '<strong>Table of Contents</strong>\n'
            f'{toc_html}</nav>\n'
        )
        body_html = toc_section + body_html
    return HTML_TEMPLATE.format(
        title=title, body=body_html, source=source_name,
    )


def _replace_table_alignment(html: str) -> str:
    """Replace inline table alignment styles with CSS classes."""
    replacements = {
        '<th style="text-align: center;">': '<th class="text-center">',
        '<td style="text-align: center;">': '<td class="text-center">',
        '<th style="text-align: right;">': '<th class="text-right">',
        '<td style="text-align: right;">': '<td class="text-right">',
    }
    for old, new in replacements.items():
        html = html.replace(old, new)
    return html


def build_all() -> None:
    """Build HTML for all documentation files."""
    DOCS_DIR.mkdir(exist_ok=True)
    css_path = DOCS_DIR / "docs.css"
    css_path.write_text(
        CSS_STYLES.strip() + "\n", encoding="utf-8",
    )
    for src_path, out_name, title in DOCS:
        if not src_path.exists():
            print(f"  SKIP  {src_path} (not found)")
            continue
        md_text = src_path.read_text(encoding="utf-8")
        html = convert_md_to_html(md_text, title, src_path.name)
        out_path = DOCS_DIR / out_name
        out_path.write_text(html, encoding="utf-8")
        print(
            f"  OK    {src_path.relative_to(ROOT)}"
            f" -> docs/{out_name}",
        )


if __name__ == "__main__":
    print("Building HTML documentation...")
    build_all()
    print("Done.")
