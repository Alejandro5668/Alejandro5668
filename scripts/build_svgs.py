#!/usr/bin/env python3
"""Build the README SVGs from assets/src/*.svg.

Each template references fonts by face name (font-family="JM400", ...).
This script asks Google Fonts for a subset with only the characters used
in that template, and embeds it as base64 in place of the /*FONTS*/ marker,
so GitHub renders the real typefaces inside <img>.

Templates may also use {{KEY}} placeholders. They are filled with the
portrait (as a data URI) and with the GitHub activity of the last year,
fetched from the GraphQL API with the token in GH_TOKEN or GITHUB_TOKEN
(falling back to `gh auth token`).

Usage: python3 scripts/build_svgs.py
"""
import base64
import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"
OUT = ROOT / "assets"
LOGIN = "Alejandro5668"

# face name -> (Google Fonts family, axis spec)
FACES = {
    "JM400": ("JetBrains Mono", "wght@400"),
    "JM500": ("JetBrains Mono", "wght@500"),
    "JM700": ("JetBrains Mono", "wght@700"),
    "JM700i": ("JetBrains Mono", "ital,wght@1,700"),
    "MS600": ("Mona Sans", "wght@600"),
}

# Contribution heatmap: empty, then lavender to pink as activity grows.
SHADES = ["#1A1820", "#3E3560", "#7A68B0", "#C69BD6", "#F5AEC1"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def used_text(svg: str) -> str:
    chunks = re.findall(r"<text\b[^>]*>(.*?)</text>", svg, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "", "".join(chunks)))
    return "".join(sorted(set(text + " ")))


def font_face(face: str, chars: str) -> str:
    family, axes = FACES[face]
    query = urllib.parse.urlencode({"family": f"{family}:{axes}", "text": chars})
    css = fetch(f"https://fonts.googleapis.com/css2?{query}").decode()
    url = re.search(r"src:\s*url\(([^)]+)\)", css).group(1)
    data = base64.b64encode(fetch(url)).decode()
    return f"@font-face{{font-family:{face};src:url(data:font/woff2;base64,{data}) format('woff2')}}"


def token() -> str:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def activity() -> dict:
    query = """query($login:String!){user(login:$login){contributionsCollection{
      totalCommitContributions totalPullRequestContributions
      contributionCalendar{totalContributions weeks{contributionDays{contributionCount date}}}}}}"""
    body = json.dumps({"query": query, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token()}", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]["contributionsCollection"]


def shade(count: int) -> str:
    if count == 0:
        return SHADES[0]
    if count <= 5:
        return SHADES[1]
    if count <= 20:
        return SHADES[2]
    if count <= 50:
        return SHADES[3]
    return SHADES[4]


def month_label(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{MONTHS[d.month - 1]} {d.year}"


def thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def activity_values() -> dict:
    data = activity()
    weeks = data["contributionCalendar"]["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]

    streak = best_streak = 0
    for c in counts:
        streak = streak + 1 if c else 0
        best_streak = max(best_streak, streak)

    # 53 columns x 7 rows inside the 848 px wide pane, 16 px pitch.
    pitch, size, left, top = 16, 13, 22, 880
    cells = []
    for col, week in enumerate(weeks[-53:]):
        for day in week["contributionDays"]:
            row = date.fromisoformat(day["date"]).isoweekday() % 7
            cells.append(
                f'<rect x="{left + col * pitch}" y="{top + row * pitch}" width="{size}" '
                f'height="{size}" rx="2" fill="{shade(day["contributionCount"])}"/>'
            )

    return {
        "HEATMAP": "".join(cells),
        "FROM": month_label(days[0]["date"]),
        "TO": month_label(days[-1]["date"]),
        "CONTRIB": thousands(data["contributionCalendar"]["totalContributions"]),
        "COMMITS": thousands(data["totalCommitContributions"]),
        "PRS": thousands(data["totalPullRequestContributions"]),
        "ACTIVE": thousands(sum(1 for c in counts if c)),
        "STREAK": thousands(best_streak),
        "BEST": thousands(max(counts)),
    }


def values_for(svg: str, cache: dict) -> dict:
    keys = set(re.findall(r"\{\{(\w+)\}\}", svg))
    if "PORTRAIT" in keys and "PORTRAIT" not in cache:
        data = base64.b64encode((SRC / "portrait.jpg").read_bytes()).decode()
        cache["PORTRAIT"] = f"data:image/jpeg;base64,{data}"
    if keys - {"PORTRAIT"} and "HEATMAP" not in cache:
        cache.update(activity_values())
    return cache


def build(template: Path, cache: dict) -> None:
    svg = template.read_text(encoding="utf-8")
    values = values_for(svg, cache)
    svg = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], svg)
    faces = sorted(set(re.findall(r'font-family="(\w+)', svg)) & FACES.keys())
    chars = used_text(svg)
    fonts = "".join(font_face(face, chars) for face in faces)
    out = OUT / template.name
    out.write_text(svg.replace("/*FONTS*/", fonts), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}  {out.stat().st_size / 1024:.0f} KB  ({', '.join(faces)})")


if __name__ == "__main__":
    cache: dict = {}
    for path in sorted(SRC.glob("*.svg")):
        build(path, cache)
