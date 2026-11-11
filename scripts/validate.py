#!/usr/bin/env python3
"""Structural and marketplace-safety checks for this skill repo.

Checks frontmatter, name and description limits, relative links, agent
definitions, and that bundled scripts make no network calls and hold no
secrets, so the package passes marketplace security scans.

Created by Jessica Mosley | LinkedIn: https://www.linkedin.com/in/jessmosley/ | GitHub: https://github.com/j-m-o/
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
errors = []
FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
NETWORK = re.compile(r"^\s*(import|from)\s+(urllib|requests|http\.client|socket|httpx|aiohttp)\b", re.M)
SECRET = re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}['\"]", re.I)


def check_front(file: Path, need_name: str | None):
    m = FRONT.match(file.read_text(encoding="utf-8"))
    if not m:
        errors.append(f"Missing frontmatter: {file}")
        return
    fm = m.group(1)
    name = re.search(r"^name: (.+)$", fm, re.M)
    desc = re.search(r"^description: (.+)$", fm, re.M)
    if not name or (need_name and name.group(1).strip() != need_name):
        errors.append(f"Bad name in {file}")
    if not desc or not desc.group(1).strip():
        errors.append(f"Missing description in {file}")
    elif len(desc.group(1)) > 1024:
        errors.append(f"Description over 1024 chars in {file}")


skills = [p for p in (root / "skills").iterdir() if p.is_dir()]
if not skills:
    errors.append("No skills found")
for s in skills:
    f = s / "SKILL.md"
    if not f.exists():
        errors.append(f"Missing {f}")
        continue
    check_front(f, s.name)
    body = f.read_text(encoding="utf-8")
    for link in re.findall(r"\]\(([^)#]+)(?:#[^)]+)?\)", body):
        if not link.startswith(("http:", "https:", "mailto:")) and not (s / link).exists():
            errors.append(f"Broken link in {f}: {link}")
    for ref in re.findall(r"`((?:references|scripts|assets)/[^`\s]+)`", body):
        if not (s / ref).exists() and "<" not in ref:
            errors.append(f"Referenced file missing in {f}: {ref}")
    for py in s.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if NETWORK.search(text):
            errors.append(f"Network import in bundled script: {py}")
        if SECRET.search(text):
            errors.append(f"Possible secret in: {py}")
for a in (root / "agents").glob("*.md"):
    check_front(a, a.stem)
for doc in ["README.md", "NOTICE.md"]:
    if not (root / doc).exists():
        errors.append(f"Missing {doc}")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"OK: {len(skills)} skill(s) validated")
