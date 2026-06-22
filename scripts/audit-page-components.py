#!/usr/bin/env python3
"""Crawl Pages-tab URLs and audit Phase 3 standalone component usage."""

import concurrent.futures
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
OUT_JSON = ROOT / "page-components.json"
OUT_JS = ROOT / "page-components.data.js"

PHASE3_COMPONENTS = [
    {
        "key": "twocol",
        "id": "task-twocol",
        "label": "Two-column",
        "pillClass": "pg-comp-twocol",
        "detection": "features-stacked-content widget; module_features-stacked-content CSS; features-stacked-content section class",
        "patterns": [
            (r"module_features-stacked-content\.min\.css", "module_features-stacked-content CSS"),
            (r'features-stacked-content-widget_', "features-stacked-content widget"),
            (r'class="[^"]*\bfeatures-stacked-content\b', "features-stacked-content section"),
        ],
    },
    {
        "key": "faq",
        "id": "task-faq",
        "label": "FAQ",
        "pillClass": "pg-comp-faq",
        "detection": "dl.faqs; faq-widget; module_FAQs CSS; FAQPage JSON-LD; pricing accordion (js-faq-heading)",
        "patterns": [
            (r'<dl class="faqs">', "dl.faqs"),
            (r'id="faq-widget_', "faq-widget section"),
            (r"module_FAQs\.min\.css", "module_FAQs CSS"),
            (r'"@type"\s*:\s*"FAQPage"', "FAQPage JSON-LD"),
        ],
        "extra": "pricing_faq",
    },
    {
        "key": "twocol-bigger",
        "id": "task-twocol-bigger",
        "label": "Two-column · bigger left",
        "pillClass": "pg-comp-twocol-bigger",
        "detection": "Values page list variation (/about-us/values/)",
        "url_paths": ["/about-us/values"],
    },
    {
        "key": "flat-one-column",
        "id": "task-flat-one-column",
        "label": "Flat one column",
        "pillClass": "pg-comp-flat-one-column",
        "detection": "Values page dark flat sections (/about-us/values/)",
        "url_paths": ["/about-us/values"],
    },
    {
        "key": "features-list",
        "id": "task-features-list",
        "label": "Features list",
        "pillClass": "pg-comp-features-list",
        "detection": "module_feature-block-list CSS; Values page",
        "patterns": [(r"module_feature-block-list", "module_feature-block-list")],
        "url_paths": ["/about-us/values"],
    },
    {
        "key": "special-hero",
        "id": "task-special-hero-introduction",
        "label": "Special hero introduction",
        "pillClass": "pg-comp-special-hero",
        "detection": "module_special-heading; module_special-intro; module_feature-introduction",
        "patterns": [
            (r"module_special-heading", "module_special-heading"),
            (r"module_special-intro", "module_special-intro"),
            (r"module_feature-introduction", "module_feature-introduction"),
        ],
    },
    {
        "key": "iconcards",
        "id": "task-iconcards",
        "label": "Icon cards",
        "pillClass": "pg-comp-iconcards",
        "detection": "module_icon-cards CSS",
        "patterns": [(r"module_icon-cards", "module_icon-cards")],
    },
    {
        "key": "featuresunfold",
        "id": "task-featuresunfold",
        "label": "Features unfold",
        "pillClass": "pg-comp-featuresunfold",
        "detection": "module_features-unfold CSS",
        "patterns": [(r"module_features-unfold", "module_features-unfold")],
    },
    {
        "key": "categorylinks",
        "id": "task-categorylinks",
        "label": "Category links",
        "pillClass": "pg-comp-categorylinks",
        "detection": "module_link-cards CSS",
        "patterns": [(r"module_link-cards", "module_link-cards")],
    },
    {
        "key": "icon-list-grid",
        "id": "task-icon-list-grid",
        "label": "Icon list grid",
        "pillClass": "pg-comp-icon-list-grid",
        "detection": "module_icons-list CSS",
        "patterns": [(r"module_icons-list", "module_icons-list")],
    },
    {
        "key": "cards",
        "id": "task-cards",
        "label": "Cards",
        "pillClass": "pg-comp-cards",
        "detection": "Card Segmentation module (dl#cards-events); module_card-segmentation",
        "patterns": [
            (r'id="cards-events-module_', "Card Segmentation (cards-events)"),
            (r"module_card-segmentation", "Card Segmentation module"),
        ],
    },
    {
        "key": "services-section",
        "id": "task-services-section",
        "label": "Services section",
        "pillClass": "pg-comp-services-section",
        "detection": "Professional services page (/professional-services)",
        "url_paths": ["/professional-services"],
    },
    {
        "key": "service-detail",
        "id": "task-service-detail",
        "label": "Service detail",
        "pillClass": "pg-comp-service-detail",
        "detection": "module_features-detail on /features or /professional-services",
        "patterns": [(r"module_features-detail", "module_features-detail")],
        "url_paths": ["/professional-services", "/features"],
    },
    {
        "key": "video-hero",
        "id": "task-video-hero-section",
        "label": "Video hero section",
        "pillClass": "pg-comp-video-hero",
        "detection": "module_media-frame CSS (hero video/image frame)",
        "patterns": [(r"module_media-frame", "module_media-frame")],
    },
    {
        "key": "pricing-widget",
        "id": "task-pricing-widget",
        "label": "Pricing widget",
        "pillClass": "pg-comp-pricing-widget",
        "detection": "module_card-pricing CSS on /pricing/",
        "patterns": [(r"module_card-pricing", "module_card-pricing")],
        "url_paths": ["/pricing"],
    },
    {
        "key": "addons",
        "id": "task-addons",
        "label": "Addons",
        "pillClass": "pg-comp-addons",
        "detection": "module_tabs CSS on /pricing/",
        "patterns": [(r"module_tabs", "module_tabs")],
        "url_paths": ["/pricing"],
    },
    {
        "key": "stats-section",
        "id": "task-stats-section",
        "label": "Stats section",
        "pillClass": "pg-comp-stats-section",
        "detection": "module_stats-set CSS (page-level stats bar, not stacked global widget)",
        "patterns": [(r"module_stats-set\.min\.css", "module_stats-set")],
        "exclude_url_paths": ["/pricing"],
    },
    {
        "key": "horizontal-slider",
        "id": "task-horizontal-slider",
        "label": "Horizontal slider",
        "pillClass": "pg-comp-horizontal-slider",
        "detection": "features-horizontal-slide widget",
        "patterns": [(r"features-horizontal-slide-widget_", "features-horizontal-slide widget")],
    },
    {
        "key": "customer-story",
        "id": "task-customer-story",
        "label": "Customer story carousel",
        "pillClass": "pg-comp-customer-story",
        "detection": "HubSpot testimonial module (38732243047_testimonial)",
        "patterns": [(r"38732243047_testimonial", "testimonial module")],
    },
    {
        "key": "reports",
        "id": "task-reports",
        "label": "Reports",
        "pillClass": "pg-comp-reports",
        "detection": "module_information-card CSS",
        "patterns": [(r"module_information-card", "module_information-card")],
    },
    {
        "key": "features-index",
        "id": "task-features-index",
        "label": "Features index",
        "pillClass": "pg-comp-features-index",
        "detection": "module_features-detail on /features index",
        "url_paths": ["/features"],
        "patterns": [(r"module_features-detail", "module_features-detail")],
    },
    {
        "key": "dual-quote",
        "id": "task-dual-quote",
        "label": "Dual quote",
        "pillClass": "pg-comp-dual-quote",
        "detection": "Two or more module_quote sections on same page",
        "min_pattern_count": [(r"module_quote", 2)],
    },
    {
        "key": "announcement-bar",
        "id": "task-announcement-bar",
        "label": "Announcement bar",
        "pillClass": "pg-comp-announcement-bar",
        "detection": "Rendered banner only — element with announcement-bar and js-banner classes",
        "patterns": [
            (
                r'class="[^"]*\bannouncement-bar\b[^"]*\bjs-banner\b',
                "announcement-bar js-banner",
            ),
        ],
    },
]

# Phase 2 primitives + Phase 4 globals (HubSpot module mapping confirmed)
EXTRA_COMPONENTS = [
    {
        "key": "text",
        "id": "task-text",
        "label": "Text block",
        "pillClass": "pg-comp-text",
        "detection": "Header Composition module — rendered section.heading-composition",
        "patterns": [
            (
                r'<section class="heading-composition[^"]*custom-text-wrapper',
                "Header Composition section",
            ),
            (r"heading-composition-widget_", "Header Composition widget"),
        ],
    },
    {
        "key": "button",
        "id": "task-button",
        "label": "Button",
        "pillClass": "pg-comp-button",
        "detection": "Button stack (#js-button-stack) or Main Button module widget",
        "patterns": [
            (r'id="js-button-stack"', "Button stack"),
            (r"button-stack-widget_", "Button stack widget"),
            (r"107498943492", "Main Button module"),
            (r'class="[^"]*\bbutton-module\b', "Main Button section"),
        ],
    },
    {
        "key": "global-stats",
        "id": "task-global-stats",
        "label": "Global stats",
        "pillClass": "pg-comp-global-stats",
        "detection": "Stats Set Stacked module — stats-set-stacked-wrapper DOM",
        "patterns": [
            (r'stats-set-stacked-wrapper', "Stats Set Stacked"),
            (r'id="stats-set-stacked-module_', "Stats Set Stacked section"),
            (r"module_stats-set-stacked", "Stats Set Stacked module"),
        ],
    },
    {
        "key": "industries-widget",
        "id": "task-industries-widget",
        "label": "Industries widget",
        "pillClass": "pg-comp-industries-widget",
        "detection": "Industry Selector widget (industry-selector-widget_ / industry-selector DOM)",
        "patterns": [
            (r'industry-selector-widget_', "Industry Selector widget"),
            (r'id="industry-selector-', "Industry Selector section"),
            (r"module_industry-selector-global", "Industry Selector (Global)"),
            (r"module_industry-selector\.min\.css", "Industry Selector module"),
        ],
    },
]

ALL_COMPONENTS = PHASE3_COMPONENTS + EXTRA_COMPONENTS

# Phase 3 tasks with no reliable live-site marker yet (still wired in UI)
PHASE3_PLACEHOLDER = [
    ("twocol-text-heavy", "task-twocol-text-heavy", "Two-column · text-heavy", "pg-comp-twocol-text-heavy", "No unique HubSpot marker yet — variant of Two-column"),
    ("centeredtext", "task-centeredtext", "Centered text block", "pg-comp-centeredtext", "No unique HubSpot marker yet"),
    ("image-icon-grid-list", "task-image-icon-grid-list", "Image with icon grid list", "pg-comp-image-icon-grid-list", "No unique HubSpot marker yet"),
    ("introduction-summary", "task-introduction-summary", "Introduction summary", "pg-comp-introduction-summary", "No unique HubSpot marker yet"),
    ("use-case", "task-use-case-section", "Use case section", "pg-comp-use-case", "Not used on audited live pages — results-list marker was a false positive"),
    ("form-section", "task-form-section", "Form section", "pg-comp-form-section", "Uses shared custom-form module site-wide"),
    ("cta", "task-cta", "CTA section", "pg-comp-cta", "Uses shared conversion modules site-wide"),
    ("industry-vertical", "task-industry-vertical", "Industry vertical section", "pg-comp-industry-vertical", "No unique HubSpot marker yet"),
    ("implementation-packages", "task-implementation-packages", "Implementation packages", "pg-comp-implementation-packages", "No unique HubSpot marker yet"),
]


def extract_urls_and_titles():
    html = INDEX.read_text()
    panel = html.split('id="panel-pages"')[1].split("</div><!-- /panel-pages -->")[0]
    urls = []
    seen = set()
    for m in re.finditer(r'href="(https://www\.roller\.software[^"]+)"', panel):
        u = m.group(1).replace("&amp;", "&")
        if u not in seen:
            seen.add(u)
            urls.append(u)

    url_titles = {}
    for row in re.findall(r'<div class="pg-row">(.*?)</div>', panel, re.S):
        title_m = re.search(r'pg-title">([^<]+)', row)
        url_m = re.search(r'href="(https://www\.roller\.software[^"]+)"', row)
        if url_m:
            u = url_m.group(1).replace("&amp;", "&")
            url_titles[u] = title_m.group(1).strip() if title_m else u
    return urls, url_titles


def category(url: str) -> str:
    path = url.replace("https://www.roller.software", "") or "/"
    if path in ("", "/"):
        return "Single Pages"
    if path.startswith("/features") or path.startswith("/products"):
        return "Features"
    if path.startswith("/industries"):
        return "Industries"
    if path.startswith("/competitor"):
        return "Competitors"
    if path.startswith("/solutions"):
        return "Solutions"
    if path.startswith("/pricing"):
        return "Pricing"
    if path.startswith("/partners") or path.startswith("/integrations"):
        return "Partners/Integrations"
    if path.startswith("/events"):
        return "Events"
    if any(x in path for x in ("/rollup", "/report", "/playbook", "/benchmark", "/pulse")):
        return "Gated Content"
    if path.startswith("/people-and-culture") or path.startswith("/careers"):
        return "P&C"
    if path.startswith("/legal") or "privacy" in path or "terms" in path or path.startswith("/dpa"):
        return "Legal Pages"
    if path.startswith("/about") or path.startswith("/get-started") or path.startswith("/demo"):
        return "Single Pages"
    if path.startswith("/blog"):
        return "Other"
    if path.startswith("/contact"):
        return "Other"
    if path.startswith("/product-launch"):
        return "Campaigns"
    return "Others"


def norm_url(url: str) -> str:
    return url.rstrip("/") or "https://www.roller.software"


def path_match(url: str, paths) -> bool:
    p = url.replace("https://www.roller.software", "") or "/"
    for path in paths:
        if p == path or p.startswith(path + "/"):
            return True
    return False


def pricing_faq(body: str) -> bool:
    return bool(re.search(r"Frequently Asked Questions", body)) and bool(
        re.search(r'id="js-faq-heading"', body)
    )


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


def detect_component(comp: dict, url: str, body: str) -> str | None:
    if comp.get("exclude_url_paths") and path_match(url, comp["exclude_url_paths"]):
        return None

    marker = None

    if comp.get("url_paths") and path_match(url, comp["url_paths"]):
        marker = comp["url_paths"][0] + " path"

    for pattern, label in comp.get("patterns", []):
        if re.search(pattern, body):
            marker = label
            break

    if comp.get("extra") == "pricing_faq" and pricing_faq(body):
        marker = "pricing FAQ accordion"

    for pattern, min_count in comp.get("min_pattern_count", []):
        if len(re.findall(pattern, body)) >= min_count:
            marker = f"{min_count}+ {pattern}"

    return marker


def main():
    urls, url_titles = extract_urls_and_titles()
    print(f"Crawling {len(urls)} URLs…")

    bodies = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as ex:
        for url, body in ex.map(fetch, urls):
            bodies[url] = body

    # First pass: raw hits per component
    hits: dict[str, list[dict]] = {c["key"]: [] for c in ALL_COMPONENTS}

    for url in urls:
        body = bodies[url]
        title = url_titles.get(url, url)
        cat = category(url)
        for comp in ALL_COMPONENTS:
            marker = detect_component(comp, url, body)
            if marker:
                hits[comp["key"]].append(
                    {
                        "url": norm_url(url),
                        "title": title,
                        "category": cat,
                        "marker": marker,
                    }
                )

    # Apply exclude_if rules between components
    dual_urls = {p["url"] for p in hits.get("dual-quote", [])}
    _ = dual_urls  # reserved for future cross-component exclusions

    # Deduplicate pages per component by URL
    for key in hits:
        seen = set()
        deduped = []
        for p in hits[key]:
            if p["url"] in seen:
                continue
            seen.add(p["url"])
            deduped.append(p)
        hits[key] = deduped

    components = {}
    pages_map: dict[str, list[str]] = defaultdict(list)

    for comp in ALL_COMPONENTS:
        key = comp["key"]
        pages = hits[key]
        by_cat: dict[str, int] = defaultdict(int)
        for p in pages:
            by_cat[p["category"]] += 1
            if key not in pages_map[p["url"]]:
                pages_map[p["url"]].append(key)

        components[key] = {
            "id": comp["id"],
            "label": comp["label"],
            "pillClass": comp["pillClass"],
            "detection": comp["detection"],
            "pageCount": len(pages),
            "byCategory": dict(sorted(by_cat.items())),
            "pages": pages,
        }

    for key, task_id, label, pill_class, detection in PHASE3_PLACEHOLDER:
        if key in components:
            continue
        components[key] = {
            "id": task_id,
            "label": label,
            "pillClass": pill_class,
            "detection": detection,
            "pageCount": 0,
            "byCategory": {},
            "pages": [],
        }

    for key in ("faq", "twocol"):
        if key not in components:
            old = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
            if key in old.get("components", {}):
                components[key] = old["components"][key]

    data = {
        "version": 6,
        "audited": "2026-06",
        "phase": "2-4",
        "components": components,
        "pages": {k: sorted(v) for k, v in sorted(pages_map.items())},
    }

    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")
    OUT_JS.write_text(
        "window.PAGE_COMPONENTS=" + json.dumps(data, separators=(",", ":")) + ";\n"
    )

    print(f"Wrote {OUT_JSON.name} — {len(components)} components")
    for key, comp in sorted(components.items(), key=lambda x: -x[1]["pageCount"]):
        print(f"  {comp['pageCount']:3d}  {comp['label']}")


if __name__ == "__main__":
    main()
