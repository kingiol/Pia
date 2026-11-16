"""Check repository-relative Markdown destinations without network access."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    for document in documents:
        for match in re.finditer(r"!?\[[^\]]*\]\(([^)\n]+)\)", document.read_text()):
            destination = match.group(1).strip().split(' "')[0].strip("<>")
            parsed = urlsplit(destination)
            if parsed.scheme or not parsed.path:
                continue
            target = ROOT / unquote(parsed.path).lstrip("/") if parsed.path.startswith("/") else document.parent / unquote(parsed.path)
            if not target.exists():
                errors.append(f"{document.relative_to(ROOT)}: missing {destination}")
    index = (ROOT / "docs/INDEX.md").read_text()
    for path in documents[1:]:
        if path.name != "INDEX.md" and path.name not in index:
            errors.append(f"docs/INDEX.md: missing {path.name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated links and navigation for {len(documents)} documents.")


if __name__ == "__main__":
    main()
