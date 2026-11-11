#!/usr/bin/env python3
"""Package every skill under skills/ as dist/<name>.zip (Agensi / Claude upload) and dist/<name>.skill.

Created by Jessica Mosley | LinkedIn: https://www.linkedin.com/in/jessmosley/ | GitHub: https://github.com/j-m-o/
"""
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
shutil.rmtree(dist, ignore_errors=True)
dist.mkdir()
for skill in sorted(p for p in (root / "skills").iterdir() if (p / "SKILL.md").exists()):
    archive = dist / f"{skill.name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(skill.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, Path(skill.name) / f.relative_to(skill))
    shutil.copy(archive, dist / f"{skill.name}.skill")
    print(f"built {archive.relative_to(root)}")
agents = root / "agents"
if agents.exists():
    (dist / "agents").mkdir()
    for a in agents.glob("*.md"):
        shutil.copy(a, dist / "agents" / a.name)
        print(f"copied agents/{a.name}")
