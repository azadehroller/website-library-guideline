#!/usr/bin/env python3
"""Extract HubSpot module/section cards from HS-components.html for the standalone library UI."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HS = ROOT / "HS-components.html"
OUT_JSON = ROOT / "hs-library.json"
OUT_JS = ROOT / "hs-library.data.js"


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def parse_meta(header_html: str) -> list[dict]:
    meta = []
    for m in re.finditer(
        r'<div><span class="label">([^<]+)</span>(.*?)</div>', header_html, re.S
    ):
        meta.append({"label": m.group(1).strip(), "html": m.group(2).strip()})
    return meta


def parse_sections(body_html: str) -> list[dict]:
    sections = []
    for m in re.finditer(r"<section>(.*?)</section>", body_html, re.S):
        chunk = m.group(1)
        h3 = re.search(r"<h3>(.*?)</h3>", chunk, re.S)
        heading = strip_tags(h3.group(1)) if h3 else ""
        content = chunk[h3.end() :] if h3 else chunk
        sections.append({"heading": heading, "html": content.strip()})
    return sections


def parse_card(kind: str, attrs: str, body: str) -> dict:
    def attr(name: str) -> str | None:
        m = re.search(rf'{name}="([^"]*)"', attrs)
        return m.group(1) if m else None

    card_id = attr("id") or ""
    header_m = re.match(r"\s*<header>(.*?)</header>(.*)", body, re.S)
    header_html = header_m.group(1) if header_m else ""
    body_html = header_m.group(2).strip() if header_m else body.strip()

    h2_m = re.search(r"<h2>(.*?)</h2>", header_html, re.S)
    title = strip_tags(h2_m.group(1)) if h2_m else card_id

    rec: dict = {
        "id": card_id,
        "kind": kind,
        "title": title,
        "label": attr("data-label") or title.lower(),
        "meta": parse_meta(header_html),
        "sections": parse_sections(body_html),
    }

    if kind == "module":
        folder = attr("data-folder") or ""
        rec["folder"] = folder
        rec["slug"] = folder.replace(".module", "") if folder else card_id.replace("module-", "")
        rec["moduleId"] = attr("data-id")
        rec["search"] = f"{rec['label']} {folder} {rec.get('moduleId') or ''}".lower()
    else:
        file_name = attr("data-file") or ""
        rec["file"] = file_name
        rec["slug"] = file_name.replace(".html", "") if file_name else card_id.replace("section-", "")
        rec["search"] = f"{rec['label']} {file_name}".lower()

    return rec


def extract_cards(html: str, class_name: str, kind: str) -> list[dict]:
    cards = []
    pattern = rf'<article class="{class_name}[^"]*"([^>]*)>(.*?)</article>'
    for m in re.finditer(pattern, html, re.S):
        cards.append(parse_card(kind, m.group(1), m.group(2)))
    return cards


def build_library() -> dict:
    html = HS.read_text()
    modules = extract_cards(html, "module-card item-mod", "module")
    sections = extract_cards(html, "section-card item-sec", "section")
    return {
        "source": "HS-components.html",
        "moduleCount": len(modules),
        "sectionCount": len(sections),
        "modules": modules,
        "sections": sections,
    }


def main():
    library = build_library()
    OUT_JSON.write_text(json.dumps(library, indent=2) + "\n")
    OUT_JS.write_text(
        "window.HS_LIBRARY=" + json.dumps(library, separators=(",", ":")) + ";\n"
    )
    print(
        f"Wrote {OUT_JSON.name} — "
        f"{library['moduleCount']} modules, {library['sectionCount']} sections"
    )


if __name__ == "__main__":
    main()
