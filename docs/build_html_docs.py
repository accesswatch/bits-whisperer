#!/usr/bin/env python3
"""Build HTML versions of all project Markdown documentation.

Usage:
    python docs/build_html_docs.py

Reads every .md file listed in DOCS and writes a styled .html file to docs/.
Requires the ``markdown`` package (already in requirements.txt).
"""

from __future__ import annotations

from pathlib import Path

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"

# (source_md_path, output_html_name, html_title)
DOCS: list[tuple[Path, str, str]] = [
    (DOCS_DIR / "README.md", "README.html", "BITS Whisperer — README"),
    (DOCS_DIR / "ANNOUNCEMENT.md", "ANNOUNCEMENT.html", "BITS Whisperer — Announcement"),
    (DOCS_DIR / "PRD.md", "PRD.html", "BITS Whisperer — Product Requirements Document"),
    (DOCS_DIR / "USER_GUIDE.md", "USER_GUIDE.html", "BITS Whisperer — User Guide"),
]

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
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
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
                 sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
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
  h1 {{ font-size: 2em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }}
  h2 {{ font-size: 1.5em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }}
  h3 {{ font-size: 1.25em; }}
  p {{ margin: 0.5em 0 1em; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
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
</style>
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
    # Insert TOC at the top if it has content
    toc_html = getattr(md, "toc", "")
    if toc_html and "<li>" in toc_html:
        toc_section = f'<nav class="toc"><strong>Table of Contents</strong>\n{toc_html}</nav>\n'
        body_html = toc_section + body_html
    return HTML_TEMPLATE.format(title=title, body=body_html, source=source_name)


def build_all() -> None:
    """Build HTML for all documentation files."""
    DOCS_DIR.mkdir(exist_ok=True)
    for src_path, out_name, title in DOCS:
        if not src_path.exists():
            print(f"  SKIP  {src_path} (not found)")
            continue
        md_text = src_path.read_text(encoding="utf-8")
        html = convert_md_to_html(md_text, title, src_path.name)
        out_path = DOCS_DIR / out_name
        out_path.write_text(html, encoding="utf-8")
        print(f"  OK    {src_path.relative_to(ROOT)} -> docs/{out_name}")


if __name__ == "__main__":
    print("Building HTML documentation...")
    build_all()
    print("Done.")
