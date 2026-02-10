import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

pattern = re.compile(r"^_{3,}\s*$")
changes = []
for p in DOCS.glob("*.md"):
    text = p.read_text(encoding="utf-8")
    original = text
    # Replace lines of 3+ underscores with a standard HR
    text = re.sub(r"(?m)^_{3,}\s*$", "---", text)
    # Remove stray trailing backslashes at ends of lines
    text = re.sub(r"\\\s*$", "", text, flags=re.M)
    # Normalize CRLF to LF
    text = text.replace("\r\n", "\n")
    # Ensure file ends with a single newline
    if not text.endswith("\n"):
        text += "\n"
    # Write back if changed
    if text != original:
        p.write_text(text, encoding="utf-8")
        changes.append(str(p.relative_to(ROOT)))

print("Modified files:")
for c in changes:
    print(c)
