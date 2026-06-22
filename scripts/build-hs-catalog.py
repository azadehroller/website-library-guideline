#!/usr/bin/env python3
"""Build hs-catalog.json from HS-components.html (HubSpot theme library)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HS = ROOT / "HS-components.html"
OUT = ROOT / "hs-catalog.json"


def build_catalog() -> dict:
    hs = HS.read_text()
    modules: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    sections: dict[str, dict] = {}

    for m in re.finditer(
        r'data-kind="module"[^>]*><td><a[^>]*>([^<]+)</a></td>'
        r"<td><code>([^<]+)</code></td><td><code>(\d+|—)</code></td><td><code>([^<]*)</code>",
        hs,
    ):
        label, folder, mid, suffix = m.group(1), m.group(2), m.group(3), m.group(4)
        slug = folder.replace(".module", "")
        rec = {
            "label": label.strip(),
            "folder": folder,
            "slug": slug,
            "moduleId": mid if mid != "—" else None,
            "suffix": suffix if suffix and suffix != "—" else None,
        }
        modules[slug] = rec
        if rec["moduleId"]:
            by_id[rec["moduleId"]] = rec
        if rec["suffix"]:
            by_id[rec["suffix"]] = rec

    for m in re.finditer(
        r'data-kind="section"[^>]*><td><a[^>]*>([^<]+)</a></td>'
        r"<td><code>([^<]+)</code></td><td>([^<]*)</td><td>([^<]*)</td>"
        r"<td>([^<]*)</td><td>([^<]*)</td>",
        hs,
    ):
        label, file, _mid, _suffix, contains, mod_count = m.groups()
        slug = file.replace(".html", "")
        child_modules = []
        if contains and "module(s)" not in contains and contains.strip() not in ("—", ""):
            raw = contains.replace(" +1 more", "").replace(" +5 more", "")
            child_modules = [x.strip() for x in raw.split(",") if x.strip()]
        sections[slug] = {
            "label": label.strip(),
            "file": file,
            "slug": slug,
            "sectionClass": slug,
            "containsModules": child_modules,
            "moduleCount": mod_count.strip() if mod_count else None,
        }

    return {
        "source": "HS-components.html",
        "moduleCount": len(modules),
        "sectionCount": len(sections),
        "modules": modules,
        "sections": sections,
        "byId": by_id,
    }


def main():
    catalog = build_catalog()
    OUT.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Wrote {OUT.name} — {catalog['moduleCount']} modules, {catalog['sectionCount']} sections")


if __name__ == "__main__":
    main()
