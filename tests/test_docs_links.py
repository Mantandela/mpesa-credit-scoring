"""The documentation stays navigable and safe: README.md and docs/*.md.

- every relative markdown link points to a file that exists, and an #anchor matches a real heading of the target
  (GitHub-style slug: lowercase, spaces to hyphens, punctuation removed; repeated headings get -1, -2, ...);
- external links (http, https, mailto) are ignored;
- no Windows absolute path (like C:\\Users) and no database URL with a real-looking password appear in any doc.
  Placeholders are allowed: an upper-case word (PASSWORD), <angle brackets> or ${VARIABLE}.

docs/statement_summary.md is skipped: it is generated from the author's own statement, git-ignored and never shared.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = {"docs/statement_summary.md"}                 # git-ignored, local only
DOCS = [p for p in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
        if p.relative_to(ROOT).as_posix() not in PRIVATE]

LINK = re.compile(r"(?<!\\)\[(?:[^\]\\]|\\.)*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
FENCE = re.compile(r"^(```|~~~)")
WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\\\?[A-Za-z0-9_.$ -]")
DB_URL = re.compile(r"\b(postgres(?:ql)?(?:\+\w+)?)://([^:/@\s]+):([^@\s]+)@", re.IGNORECASE)
PLACEHOLDER = re.compile(r"^(<[^>]+>|[A-Z][A-Z0-9_]*|\$\{?[A-Z][A-Z0-9_]*\}?|\*+|\.\.\.)$")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: drop markdown emphasis and code marks, lowercase, keep letters, digits, spaces,
    hyphens and underscores, then spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)            # a link inside a heading keeps its text
    text = text.replace("`", "").replace("*", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set:
    out, seen, fenced = set(), {}, False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line.strip()):
            fenced = not fenced
            continue
        m = None if fenced else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            base = slug(m.group(2))
            n = seen.get(base, 0)
            out.add(base if n == 0 else f"{base}-{n}")
            seen[base] = n + 1
    return out


def links(path: Path) -> list:
    """(line number, target) of every markdown link outside code fences and inline code."""
    out, fenced = [], False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line.strip()):
            fenced = not fenced
            continue
        if fenced:
            continue
        for m in LINK.finditer(re.sub(r"`[^`]*`", "", line)):
            out.append((i, m.group(1)))
    return out


def test_the_docs_exist():
    names = {p.relative_to(ROOT).as_posix() for p in DOCS}
    assert {"README.md", "docs/README.md"} <= names and len(names) > 10


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_and_anchors_resolve(doc):
    problems = []
    for line, target in links(doc):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):          # http:, https:, mailto: ...
            continue
        file_part, _, anchor = target.partition("#")
        dest = doc if not file_part else (doc.parent / file_part).resolve()
        if not dest.exists():
            problems.append(f"line {line}: {target} -> missing file")
            continue
        if dest.relative_to(ROOT).as_posix() in PRIVATE:
            problems.append(f"line {line}: {target} -> links a private, git-ignored file")
        if anchor:
            if dest.suffix.lower() != ".md":
                problems.append(f"line {line}: {target} -> anchor on a non-markdown file")
            elif anchor not in anchors(dest):
                problems.append(f"line {line}: {target} -> no heading with that anchor")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_windows_paths_or_database_passwords(doc):
    text = doc.read_text(encoding="utf-8")
    assert not WINDOWS_PATH.search(text), f"Windows absolute path in {doc.name}: {WINDOWS_PATH.search(text).group(0)!r}"
    for m in DB_URL.finditer(text):
        password = m.group(3)
        assert PLACEHOLDER.match(password), f"{doc.name}: a database URL with a real-looking password"


def test_the_slug_and_checks_themselves():
    assert slug("## 3. Known limitations".lstrip("# ")) == "3-known-limitations"
    assert slug("Estimated eligibility (PROTOTYPE POLICY)") == "estimated-eligibility-prototype-policy"
    assert slug("`fuliza_late`") == "fuliza_late" and slug("Discrimination (test set)") == "discrimination-test-set"
    assert slug("Neon (hosted PostgreSQL, for the temporary deployment)") == \
        "neon-hosted-postgresql-for-the-temporary-deployment"
    assert WINDOWS_PATH.search(r"see C:\Users\someone\file") and not WINDOWS_PATH.search("ratio 3:1 and a:b")
    for url, ok in (("postgresql+psycopg://USER:PASSWORD@HOST/DB", True), ("postgresql://u:<password>@h/db", True),
                    ("postgres://ci:${PGPASSWORD}@localhost/db", True), ("postgresql://ci:hunter2@localhost/db", False)):
        m = DB_URL.search(url)
        assert bool(PLACEHOLDER.match(m.group(3))) is ok, url
    sample = "[a](x.md) `[not](y.md)` [b](https://example.com) [c](z.md#part)"
    assert [t for _, t in [(0, m.group(1)) for m in LINK.finditer(re.sub(r"`[^`]*`", "", sample))]] == \
        ["x.md", "https://example.com", "z.md#part"]
