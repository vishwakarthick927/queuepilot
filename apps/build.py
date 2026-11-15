"""Builds the two self-contained pages (no build tools, no server needed): apps/golden/index.html and apps/concrete/index.html.
Each page has its data inlined, so it opens by double-click or from any static server:
    python -m http.server 5175 --directory apps/golden      ->  http://localhost:5175
    python -m http.server 5176 --directory apps/concrete    ->  http://localhost:5176
Run from repo root:  python apps/build.py   (after python -m engine.golden and python -m engine.concrete)"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
HERE = Path(__file__).parent
FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">'


def page(name, title, accent, data, body, script):
    css = (HERE / "_style.css").read_text().replace("VAR_ACC", accent)
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>{FONTS}<style>{css}</style></head><body>
{body}
<script>const DATA = {json.dumps(data, separators=(",", ":"))};</script>
<script>{script}</script></body></html>"""
    out = HERE / name
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print("wrote", out / "index.html", len(html) // 1024, "KB")


if __name__ == "__main__":
    g = json.loads((ROOT / "data" / "golden" / "golden.json").read_text())
    page("golden", "QueuePilot Golden Hour", "#f0a63a", g, (HERE / "golden.body.html").read_text(), (HERE / "golden.js").read_text())
    c = json.loads((ROOT / "data" / "concrete" / "concrete.json").read_text())
    page("concrete", "QueuePilot Concrete", "#9ccf4a", c, (HERE / "concrete.body.html").read_text(), (HERE / "concrete.js").read_text())
