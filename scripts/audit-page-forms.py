#!/usr/bin/env python3
"""Crawl Pages-tab URLs and detect lead-capture forms inside <main> (footer newsletter excluded)."""

from __future__ import annotations

import concurrent.futures
import json
import re
import subprocess
import html as html_lib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
OUT_JSON = ROOT / "page-forms.json"
OUT_JS = ROOT / "page-forms.data.js"

FORM_RULES: list[dict] = [
    {
        "type": "hubspot-custom-form",
        "label": "Custom form module",
        "patterns": [r"module_custom-form", r'\bcustom-form\b'],
    },
    {
        "type": "partnerships-form",
        "label": "Partnerships form",
        "patterns": [r"module_partnerships-form", r"partnerships-form"],
    },
    {
        "type": "form-and-meeting",
        "label": "Form + meeting embed",
        "patterns": [r"Form and Hubspot meeting", r"module_Form and Hubspot meeting"],
    },
    {
        "type": "hubspot-form",
        "label": "HubSpot form",
        "patterns": [
            r"widget-type-form",
            r"hs_cos_wrapper_type_form",
            r"hs_form_target_",
        ],
    },
    {
        "type": "html-form",
        "label": "HTML form",
        "patterns": [r"<form\b"],
    },
    {
        "type": "hubspot-meetings",
        "label": "HubSpot meetings",
        "patterns": [r"meetings\.hubspot\.com", r"hs-meetings-iframe"],
    },
    {
        "type": "typeform",
        "label": "Typeform embed",
        "patterns": [r"typeform\.com/to/", r"embed\.typeform\.com"],
    },
    {
        "type": "calendly",
        "label": "Calendly embed",
        "patterns": [r"calendly\.com/"],
    },
    {
        "type": "roi-calculator",
        "label": "ROI calculator",
        "patterns": [r"module_roi-calculator", r"roi-calculator", r"js-display-metrics"],
    },
]

INSTANCE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("hubspot-form", re.compile(r"hs_form_target_", re.I)),
    ("html-form", re.compile(r"<form\b", re.I)),
]


def extract_page_sections() -> list[dict]:
    html = INDEX.read_text()
    panel = html.split('id="panel-pages"')[1].split("</div><!-- /panel-pages -->")[0]
    sections: list[dict] = []
    for block in re.findall(r'<details class="phase">(.*?)</details>', panel, re.S):
        name_m = re.search(r"<h2>(.*?)</h2>", block, re.S)
        if not name_m:
            continue
        name = re.sub(r"<[^>]+>", "", name_m.group(1))
        name = html_lib.unescape(name.strip())
        section = {"name": name, "pages": []}
        for row in re.findall(r'<div class="pg-row">(.*?)</div>', block, re.S):
            title_m = re.search(r'pg-title">([^<]+)', row)
            url_m = re.search(r'href="(https://www\.roller\.software[^"]*)"', row)
            if not url_m:
                continue
            url = url_m.group(1).replace("&amp;", "&")
            section["pages"].append(
                {
                    "title": html_lib.unescape(title_m.group(1).strip()) if title_m else url,
                    "url": url,
                }
            )
        if section["pages"]:
            sections.append(section)
    return sections


def fetch(url: str) -> tuple[str, str]:
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "25", url],
            capture_output=True,
            text=True,
        )
        return url, r.stdout
    except Exception:
        return url, ""


def extract_main_html(body: str) -> str:
    m = re.search(r"<main\b[^>]*>(.*)</main>", body, re.I | re.S)
    if m:
        return m.group(1)
    body_m = re.search(r"<body\b[^>]*>(.*)</body>", body, re.I | re.S)
    chunk = body_m.group(1) if body_m else body
    chunk = re.sub(r"<header\b[^>]*>.*?</header>", "", chunk, flags=re.I | re.S)
    chunk = re.sub(r"<footer\b[^>]*>.*?</footer>", "", chunk, flags=re.I | re.S)
    return chunk


def detect_forms(main_html: str) -> list[dict]:
    forms: list[dict] = []
    for rule in FORM_RULES:
        if not any(re.search(pat, main_html, re.I) for pat in rule["patterns"]):
            continue
        count = 0
        for inst_type, pat in INSTANCE_PATTERNS:
            if inst_type == rule["type"]:
                count = len(pat.findall(main_html))
                break
        forms.append(
            {
                "type": rule["type"],
                "label": rule["label"],
                "count": count or 1,
            }
        )
    return forms


def audit_page(body: str) -> dict:
    if not body.strip():
        return {"hasForm": False, "formCount": 0, "forms": [], "error": "Failed to fetch page HTML"}
    main_html = extract_main_html(body)
    if not main_html.strip():
        return {"hasForm": False, "formCount": 0, "forms": [], "error": "No <main> content found"}
    forms = detect_forms(main_html)
    form_count = sum(item["count"] for item in forms)
    return {
        "hasForm": bool(forms),
        "formCount": form_count,
        "forms": forms,
        "error": None,
    }


def main() -> None:
    sections = extract_page_sections()
    pages = [p for s in sections for p in s["pages"]]
    print(f"Crawling {len(pages)} URLs for forms in <main>…")

    bodies: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as ex:
        for url, body in ex.map(fetch, [p["url"] for p in pages]):
            bodies[url] = body

    audited_sections = []
    with_forms = 0
    without_forms = 0
    total_forms = 0
    errors: list[str] = []

    for section in sections:
        audited_pages = []
        section_with = 0
        for page in section["pages"]:
            result = audit_page(bodies.get(page["url"], ""))
            entry = {**page, **result}
            audited_pages.append(entry)
            if result.get("error"):
                errors.append(page["url"])
            elif result["hasForm"]:
                with_forms += 1
                section_with += 1
                total_forms += result["formCount"]
            else:
                without_forms += 1
        audited_sections.append(
            {
                "name": section["name"],
                "pages": audited_pages,
                "sectionWithForms": section_with,
                "sectionTotal": len(audited_pages),
            }
        )

    data = {
        "version": 1,
        "audited": "2026-06",
        "pageCount": len(pages),
        "pagesWithForms": with_forms,
        "pagesWithoutForms": without_forms,
        "totalFormInstances": total_forms,
        "errors": errors,
        "sections": audited_sections,
    }

    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")
    OUT_JS.write_text("window.PAGE_FORMS=" + json.dumps(data, separators=(",", ":")) + ";\n")

    print(
        f"Wrote {OUT_JSON.name} — {len(pages)} pages, "
        f"{with_forms} with forms, {without_forms} without ({total_forms} form instances)"
    )
    if errors:
        print(f"  Errors: {len(errors)}")


if __name__ == "__main__":
    main()
