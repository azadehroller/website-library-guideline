#!/usr/bin/env python3
"""Aggregate HubSpot catalog usage from page-modules.json audit."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE_MODULES = ROOT / "page-modules.json"
HS_CATALOG = ROOT / "hs-catalog.json"
OUT_JSON = ROOT / "hs-usage.json"
OUT_JS = ROOT / "hs-usage.data.js"


def build_usage(page_modules: dict, catalog: dict) -> dict:
    mod_pages: dict[str, set[str]] = {}
    sec_pages: dict[str, set[str]] = {}

    for url, page in page_modules.get("pages", {}).items():
        cat = page.get("catalog") or {}
        for item in cat.get("modules") or []:
            if item.get("inCatalog") and item.get("slug"):
                mod_pages.setdefault(item["slug"], set()).add(url)
        for item in cat.get("sections") or []:
            if item.get("inCatalog") and item.get("slug"):
                sec_pages.setdefault(item["slug"], set()).add(url)

    modules: dict[str, dict] = {}
    by_folder: dict[str, dict] = {}
    for slug, rec in catalog.get("modules", {}).items():
        pages = sorted(mod_pages.get(slug, ()))
        page_count = len(pages)
        entry = {
            "slug": slug,
            "label": rec.get("label", slug),
            "folder": rec.get("folder"),
            "pageCount": page_count,
            "used": page_count > 0,
        }
        modules[slug] = entry
        if rec.get("folder"):
            by_folder[rec["folder"].lower()] = entry

    sections: dict[str, dict] = {}
    by_file: dict[str, dict] = {}
    for slug, rec in catalog.get("sections", {}).items():
        pages = sorted(sec_pages.get(slug, ()))
        page_count = len(pages)
        entry = {
            "slug": slug,
            "label": rec.get("label", slug),
            "file": rec.get("file"),
            "pageCount": page_count,
            "used": page_count > 0,
        }
        sections[slug] = entry
        if rec.get("file"):
            by_file[rec["file"]] = entry

    used_modules = sum(1 for m in modules.values() if m["used"])
    used_sections = sum(1 for s in sections.values() if s["used"])

    return {
        "version": 1,
        "audited": page_modules.get("audited"),
        "pageCount": page_modules.get("pageCount"),
        "modules": modules,
        "sections": sections,
        "byFolder": by_folder,
        "byFile": by_file,
        "stats": {
            "catalogModules": len(modules),
            "catalogSections": len(sections),
            "usedModules": used_modules,
            "unusedModules": len(modules) - used_modules,
            "usedSections": used_sections,
            "unusedSections": len(sections) - used_sections,
        },
    }


def main():
    page_modules = json.loads(PAGE_MODULES.read_text())
    catalog = json.loads(HS_CATALOG.read_text())
    usage = build_usage(page_modules, catalog)
    OUT_JSON.write_text(json.dumps(usage, indent=2) + "\n")
    OUT_JS.write_text("window.HS_USAGE=" + json.dumps(usage, separators=(",", ":")) + ";\n")
    s = usage["stats"]
    print(
        f"Wrote {OUT_JSON.name} — "
        f"{s['usedModules']}/{s['catalogModules']} modules on site, "
        f"{s['usedSections']}/{s['catalogSections']} sections on site"
    )


if __name__ == "__main__":
    main()
