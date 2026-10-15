#!/usr/bin/env python3
"""Build the README SVGs from assets/src/*.svg.

Each template references fonts by face name (font-family="BG800", ...).
This script asks Google Fonts for a subset with only the characters used
in that template, and embeds it as base64 in place of the /*FONTS*/ marker,
so GitHub renders the real typefaces inside <img>.

Usage: python3 scripts/build_svgs.py
"""
import base64
import html
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"
OUT = ROOT / "assets"

# face name -> (Google Fonts family, axis spec)
FACES = {
    "BG800": ("Bricolage Grotesque", "opsz,wght@96,800"),
    "BG600": ("Bricolage Grotesque", "opsz,wght@24,600"),
    "BG400": ("Bricolage Grotesque", "opsz,wght@18,400"),
    "NR300": ("Newsreader", "opsz,wght@16,300"),
    "NR400": ("Newsreader", "opsz,wght@20,400"),
    "NRi": ("Newsreader", "ital,opsz,wght@1,24,400"),
}

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


def build(template: Path) -> None:
    svg = template.read_text(encoding="utf-8")
    faces = sorted(set(re.findall(r'font-family="(\w+)', svg)) & FACES.keys())
    chars = used_text(svg)
    fonts = "".join(font_face(face, chars) for face in faces)
    out = OUT / template.name
    out.write_text(svg.replace("/*FONTS*/", fonts), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}  {out.stat().st_size / 1024:.0f} KB  ({', '.join(faces)})")


if __name__ == "__main__":
    for path in sorted(SRC.glob("*.svg")):
        build(path)
