#!/usr/bin/env python3
"""Crawl Pages-tab URLs and audit HubSpot modules/sections on each live page."""

import concurrent.futures
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
HS_CATALOG = ROOT / "hs-catalog.json"
OUT_JSON = ROOT / "page-modules.json"
OUT_JS = ROOT / "page-modules.data.js"

SKIP_TAGS = frozenset(
    {"br", "img", "input", "meta", "link", "path", "svg", "source", "iframe", "noscript", "script", "style"}
)
GLOBAL_FOLDERS = frozenset(
    {
        "announcement",
        "button",
        "button-stack",
        "header-theme",
        "menu-section",
        "assets",
    }
)


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


def norm_url(url: str) -> str:
    return url.rstrip("/") or "https://www.roller.software"


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


def extract_outline(html: str, element_id: str, max_depth: int = 4, max_nodes: int = 12) -> str | None:
    pat = f'id="{re.escape(element_id)}"'
    idx = html.find(pat)
    if idx < 0:
        return None
    start = html.rfind("<", 0, idx)
    if start < 0:
        return None
    tag_end = html.find(">", idx)
    if tag_end < 0:
        return None
    open_tag = html[start : tag_end + 1]
    tag_m = re.match(r"<(\w+)", open_tag)
    if not tag_m:
        return None
    root_tag = tag_m.group(1)
    cls_m = re.search(r'class="([^"]*)"', open_tag)
    root_cls = cls_m.group(1).split()[0] if cls_m else ""
    root_label = f"{root_tag}.{root_cls}" if root_cls else root_tag

    chunk = html[tag_end + 1 : tag_end + 5000]
    lines = [root_label]
    depth = 0
    node_count = 1
    for m in re.finditer(r"<(/?)(\w+)([^>]*)>", chunk):
        closing, tag, attrs = m.group(1), m.group(2), m.group(3)
        if tag in SKIP_TAGS:
            continue
        if closing:
            depth = max(0, depth - 1)
            continue
        if node_count >= max_nodes:
            break
        if depth >= max_depth:
            continue
        cm = re.search(r'class="([^"]*)"', attrs)
        c = cm.group(1).split()[0] if cm else ""
        label = f"{tag}.{c}" if c else tag
        lines.append("  " * (depth + 1) + label)
        node_count += 1
        depth += 1
        if attrs.rstrip().endswith("/") or "/>" in m.group(0):
            depth -= 1
    return "\n".join(lines)


def wrapper_classes(html: str, element_id: str) -> str:
    for pat in (
        rf'id="{re.escape(element_id)}"[^>]*class="([^"]*)"',
        rf'class="([^"]*)"[^>]*id="{re.escape(element_id)}"',
    ):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return ""


def audit_page(body: str) -> dict:
    modules: list[dict] = []
    sections: list[dict] = []

    # CSS-linked HubSpot module assets (folder + asset module id from path)
    seen_css: set[str] = set()
    for m in re.finditer(r'href="([^"]*module_([^"/?]+)\.min\.css[^"]*)"', body):
        href = m.group(1).replace("&amp;", "&")
        folder = m.group(2)
        if folder.endswith("_sections"):
            asset_id = re.match(r"(\d+)_sections", folder)
            sections.append(
                {
                    "kind": "section-css",
                    "sectionAssetId": asset_id.group(1) if asset_id else folder,
                    "cssHref": href,
                }
            )
            continue
        if folder in seen_css:
            continue
        seen_css.add(folder)
        asset_id = None
        am = re.search(r"/module_assets/(?:\d+/)?(\d+)/", href)
        if am:
            asset_id = am.group(1)
        modules.append(
            {
                "kind": "module-css",
                "folder": folder,
                "assetModuleId": asset_id,
                "cssHref": href,
                "scope": "global" if folder in GLOBAL_FOLDERS else "content",
            }
        )

    for m in re.finditer(r"module_(\d+)_sections\.min\.css", body):
        sections.append(
            {
                "kind": "section-css",
                "sectionAssetId": m.group(1),
            }
        )

    # DND section templates (s-* classes on dnd-section rows)
    seen_sections: set[str] = set()
    for m in re.finditer(r'class="([^"]*\bdnd-section[^"]*)"', body):
        classes = m.group(1).split()
        s_classes = sorted(c for c in classes if c.startswith("s-") and c != "s-layout")
        if not s_classes:
            continue
        key = " ".join(s_classes)
        if key in seen_sections:
            continue
        seen_sections.add(key)
        sections.append(
            {
                "kind": "section-template",
                "classes": s_classes,
                "classString": key,
            }
        )

    # Module instances (numeric HubSpot instance ids on page)
    instance_ids = set(re.findall(r"hs_cos_wrapper_module_(\d+)", body))
    instance_types: dict[str, set[str]] = {}
    for m in re.finditer(r"([\w-]+)-module_(\d+)", body):
        instance_types.setdefault(m.group(2), set()).add(m.group(1))

    noise_types = {"button", "js-rp-prices", "js-back-to-top", "unknown"}

    for iid in sorted(instance_ids, key=int):
        types = sorted(instance_types.get(iid, set()) - noise_types)
        wrapper_id = f"hs_cos_wrapper_module_{iid}"
        struct_id = wrapper_id
        for t in types:
            if f"{t}-module_{iid}" in body:
                struct_id = f"{t}-module_{iid}"
                break
        outline = extract_outline(body, struct_id) or extract_outline(body, wrapper_id)
        modules.append(
            {
                "kind": "instance",
                "instanceId": iid,
                "types": types,
                "label": types[0] if types else "module",
                "wrapperId": wrapper_id,
                "classes": wrapper_classes(body, wrapper_id),
                "structure": outline,
                "scope": "global"
                if any(t in GLOBAL_FOLDERS for t in types)
                else "content",
            }
        )

    # Standalone widgets (not already captured as module instances)
    widget_names: dict[str, set[str]] = {}
    for m in re.finditer(r"([\w-]+)-widget_(\d+)", body):
        wid = m.group(2)
        name = m.group(1)
        if name in WIDGET_NAME_SKIP or wid in instance_ids:
            continue
        widget_names.setdefault(wid, set()).add(name)

    seen_widgets: set[str] = set()
    for wid, names in widget_names.items():
        if wid in seen_widgets:
            continue
        seen_widgets.add(wid)
        if "industry-selector" in names:
            name = "industry-selector"
        elif "features-selector" in names:
            name = "features-selector"
        else:
            name = max(names, key=lambda n: (WIDGET_NAME_PRIORITY.get(n, 0), n))
        dom_id = f"{name}-widget_{wid}"
        wrapper_widget = f"hs_cos_wrapper_widget_{wid}"
        modules.append(
            {
                "kind": "widget",
                "widgetId": wid,
                "name": name,
                "domId": dom_id,
                "wrapperId": wrapper_widget if wrapper_widget in body else dom_id,
                "classes": wrapper_classes(body, wrapper_widget)
                or wrapper_classes(body, dom_id),
                "structure": extract_outline(body, wrapper_widget)
                or extract_outline(body, dom_id),
                "scope": "content",
            }
        )

    # HubSpot default wrappers (logo, menu, text widgets without numeric module ids)
    seen_hs: set[str] = set()
    for m in re.finditer(
        r'id="(hs_cos_wrapper_[^"]+)"[^>]*class="([^"]*hs_cos_wrapper[^"]*)"',
        body,
    ):
        el_id, cls = m.group(1), m.group(2)
        if "hs_cos_wrapper_module_" in el_id or "hs_cos_wrapper_widget_" in el_id:
            continue
        if el_id in seen_hs:
            continue
        seen_hs.add(el_id)
        wt = re.search(r"widget-type-([\w-]+)", cls)
        modules.append(
            {
                "kind": "hubspot-widget",
                "wrapperId": el_id,
                "widgetType": wt.group(1) if wt else None,
                "classes": cls,
                "structure": extract_outline(body, el_id),
                "scope": "global",
            }
        )

    summary = {
        "moduleCss": sum(1 for x in modules if x["kind"] == "module-css"),
        "instances": sum(1 for x in modules if x["kind"] == "instance"),
        "widgets": sum(1 for x in modules if x["kind"] == "widget"),
        "hubspotWidgets": sum(1 for x in modules if x["kind"] == "hubspot-widget"),
        "sectionTemplates": sum(1 for x in sections if x["kind"] == "section-template"),
        "total": len(modules) + len(sections),
    }

    return {"modules": modules, "sections": sections, "summary": summary}


SLUG_ALIASES = {
    "faq": "FAQs",
    "faqs": "FAQs",
    "module-banner": "announcement",
    "logo-set": "logo-set-global",
    "testimonial-carousel": "testimonial-slider",
    "features-card": "features-card",
    "card-pricing": "features-pricing-card",
}

SELECTOR_WIDGET_MARKERS = {
    "features-selector-global": r"Explore all of ROLLER's features",
    "industry-selector-global": r"TAILORED FOR YOUR INDUSTRY",
}

SELECTOR_INSTANCE_NOISE = frozenset(
    {
        "dropdown-wrapper",
        "industrySelectorBTN",
        "js-ind-dropdown",
        "js-industryItemContainer",
    }
)

WIDGET_NAME_SKIP = frozenset(
    SELECTOR_INSTANCE_NOISE
    | {
        "js-rp-prices",
        "js-back-to-top",
        "unknown",
    }
)

WIDGET_NAME_PRIORITY = {
    "industry-selector": 100,
    "features-selector": 100,
}

WIDGET_TYPE_LABELS = {
    "menu": "HubSpot Menu",
    "form": "HubSpot Form",
    "rich_text": "HubSpot Rich text",
    "logo": "HubSpot Logo",
    "text": "HubSpot Text",
    "linked_image": "HubSpot Linked image",
    "icon": "HubSpot Icon",
}

STRUCTURE_SLUG_PATTERNS = [
    r"section\.([a-z0-9-]+)",
    r"div#([a-z0-9-]+)-module",
    r"\.(features-stacked-content|heading-composition|feature-block-list|features-unfold|card-pricing|stats-set|testimonial-carousel|testimonial-slider|icon-cards|features-card|cta-module|o-faq|services-section|results-list|comparison-table|logo-set|announcement-bar)",
]


def infer_module_slug(item: dict) -> str | None:
    blob = f"{item.get('structure') or ''} {item.get('classes') or ''}"
    for pat in STRUCTURE_SLUG_PATTERNS:
        m = re.search(pat, blob)
        if m:
            return m.group(1)
    return None


def lookup_module(catalog: dict, slug: str | None) -> dict | None:
    if not slug:
        return None
    slug = SLUG_ALIASES.get(slug, slug)
    modules = catalog["modules"]
    if slug in modules:
        return modules[slug]
    lower = {k.lower(): v for k, v in modules.items()}
    return lower.get(slug.lower())


def resolve_selector_widget_slug(body: str, default: str = "industry-selector-global") -> str:
    for slug, pattern in SELECTOR_WIDGET_MARKERS.items():
        if re.search(pattern, body):
            return slug
    return default


def lookup_section(catalog: dict, class_string: str) -> dict | None:
    sections = catalog["sections"]
    if class_string in sections:
        return sections[class_string]
    for slug, rec in sections.items():
        if slug in class_string.split():
            return rec
    return None


def resolve_page_catalog(page: dict, catalog: dict, body: str = "") -> dict:
    """Map raw detections to HubSpot theme library names; dedupe repetitions."""
    theme_modules: dict[str, dict] = {}
    theme_sections: dict[str, dict] = {}
    platform: dict[str, dict] = {}
    unmapped: list[dict] = []

    def theme_key(slug: str) -> str:
        rec = lookup_module(catalog, slug)
        return rec["slug"] if rec else slug

    def bump_theme(slug: str, source: str, scope: str, instance_id: str | None = None):
        rec = lookup_module(catalog, slug)
        key = theme_key(slug)
        if key not in theme_modules:
            theme_modules[key] = {
                "catalogType": "module",
                "slug": key,
                "label": rec["label"] if rec else slug,
                "folder": rec["folder"] if rec else f"{slug}.module",
                "moduleId": rec["moduleId"] if rec else None,
                "scope": scope,
                "placements": 0,
                "sources": [],
                "instanceIds": [],
                "inCatalog": rec is not None,
            }
        entry = theme_modules[key]
        entry["placements"] += 1
        if source not in entry["sources"]:
            entry["sources"].append(source)
        if instance_id and instance_id not in entry["instanceIds"]:
            entry["instanceIds"].append(instance_id)

    def bump_section(class_string: str, source: str):
        rec = lookup_section(catalog, class_string)
        key = rec["slug"] if rec else class_string
        if key not in theme_sections:
            theme_sections[key] = {
                "catalogType": "section",
                "slug": key,
                "label": rec["label"] if rec else class_string,
                "file": rec["file"] if rec else None,
                "sectionClass": class_string,
                "containsModules": rec["containsModules"] if rec else [],
                "placements": 0,
                "sources": [],
                "inCatalog": rec is not None,
            }
        entry = theme_sections[key]
        entry["placements"] += 1
        if source not in entry["sources"]:
            entry["sources"].append(source)

    def bump_platform(label: str, source: str, wrapper_id: str | None = None, widget_type: str | None = None):
        key = widget_type or label
        if key not in platform:
            platform[key] = {
                "catalogType": "platform",
                "label": label,
                "widgetType": widget_type,
                "wrapperId": wrapper_id,
                "placements": 0,
                "sources": [],
            }
        entry = platform[key]
        entry["placements"] += 1
        if source not in entry["sources"]:
            entry["sources"].append(source)
        if wrapper_id and not entry.get("wrapperId"):
            entry["wrapperId"] = wrapper_id

    noise_types = {"button", "js-rp-prices", "js-back-to-top", "unknown"}

    for item in page.get("modules", []):
        kind = item.get("kind")
        scope = item.get("scope", "content")

        if kind == "module-css":
            bump_theme(item["folder"], "CSS on page", scope)

        elif kind == "instance":
            types = item.get("types") or []
            selector_types = {"industry-selector", "features-selector"} & set(types)
            if selector_types:
                slug = (
                    "features-selector-global"
                    if "features-selector" in selector_types
                    else resolve_selector_widget_slug(body)
                )
                bump_theme(
                    slug,
                    f"instance {item['instanceId']}",
                    scope,
                    item["instanceId"],
                )
            elif types:
                for t in types:
                    if t in noise_types or t in SELECTOR_INSTANCE_NOISE:
                        continue
                    bump_theme(t, f"instance {item['instanceId']}", scope, item["instanceId"])
            else:
                cls = item.get("classes", "")
                wt = re.search(r"widget-type-([\w-]+)", cls)
                inferred = infer_module_slug(item)
                if inferred and lookup_module(catalog, inferred):
                    bump_theme(
                        inferred,
                        f"instance {item['instanceId']} (structure)",
                        scope,
                        item["instanceId"],
                    )
                elif wt:
                    wtype = wt.group(1)
                    bump_platform(
                        WIDGET_TYPE_LABELS.get(wtype, f"HubSpot {wtype.replace('_', ' ')}"),
                        f"instance {item['instanceId']}",
                        item.get("wrapperId"),
                        wtype,
                    )
                else:
                    unmapped.append(
                        {
                            "kind": "instance",
                            "instanceId": item["instanceId"],
                            "wrapperId": item.get("wrapperId"),
                            "classes": cls,
                            "structure": item.get("structure"),
                        }
                    )

        elif kind == "widget":
            name = item.get("name", "")
            if name in ("industry-selector", "features-selector"):
                slug = (
                    "features-selector-global"
                    if name == "features-selector"
                    else resolve_selector_widget_slug(body)
                )
                bump_theme(slug, f"widget {item.get('widgetId')}", scope, item.get("widgetId"))
            else:
                rec = lookup_module(catalog, name)
                if rec:
                    bump_theme(name, f"widget {item.get('widgetId')}", scope, item.get("widgetId"))
                else:
                    bump_platform(
                        f"Widget · {name}",
                        f"widget {item.get('widgetId')}",
                        item.get("wrapperId"),
                        name,
                    )

        elif kind == "hubspot-widget":
            wtype = item.get("widgetType")
            label = WIDGET_TYPE_LABELS.get(wtype, f"HubSpot {wtype or item.get('wrapperId', 'widget')}")
            bump_platform(label, item.get("wrapperId", "hubspot-widget"), item.get("wrapperId"), wtype)

    for item in page.get("sections", []):
        if item.get("kind") == "section-template":
            bump_section(item["classString"], "section row on page")

    modules_list = sorted(
        theme_modules.values(),
        key=lambda x: (x["scope"] == "global", x["label"].lower()),
    )
    sections_list = sorted(theme_sections.values(), key=lambda x: x["label"].lower())
    platform_list = sorted(platform.values(), key=lambda x: x["label"].lower())

    raw_total = page.get("summary", {}).get("total", 0)
    unique_total = len(modules_list) + len(sections_list) + len(platform_list) + len(unmapped)

    return {
        "modules": modules_list,
        "sections": sections_list,
        "platform": platform_list,
        "unmapped": unmapped,
        "summary": {
            "uniqueModules": len(modules_list),
            "uniqueSections": len(sections_list),
            "platformWidgets": len(platform_list),
            "unmapped": len(unmapped),
            "uniqueTotal": unique_total,
            "rawDetections": raw_total,
        },
    }


def main():
    urls, url_titles = extract_urls_and_titles()
    print(f"Crawling {len(urls)} URLs for HubSpot modules…")

    # Build / load HubSpot theme catalog from HS-components.html
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_hs_catalog", ROOT / "scripts" / "build-hs-catalog.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    catalog = mod.build_catalog()
    HS_CATALOG.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Loaded catalog — {catalog['moduleCount']} modules, {catalog['sectionCount']} sections")

    pages: dict[str, dict] = {}
    errors: list[dict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as ex:
        bodies = dict(ex.map(fetch, urls))

    for url in urls:
        key = norm_url(url)
        body = bodies.get(url, "")
        title = url_titles.get(url, url)
        if not body.strip():
            errors.append({"url": key, "title": title, "error": "empty response"})
            pages[key] = {
                "url": key,
                "title": title,
                "error": "empty response",
                "modules": [],
                "sections": [],
                "summary": {"total": 0},
                "catalog": {"modules": [], "sections": [], "platform": [], "unmapped": [], "summary": {}},
            }
            continue
        audit = audit_page(body)
        page_data = {"url": key, "title": title, **audit}
        page_data["catalog"] = resolve_page_catalog(page_data, catalog, body)
        pages[key] = page_data

    data = {
        "version": 2,
        "audited": "2026-06",
        "pageCount": len(pages),
        "registry": {
            "moduleCount": catalog["moduleCount"],
            "sectionCount": catalog["sectionCount"],
            "source": catalog["source"],
        },
        "errors": errors,
        "pages": pages,
    }

    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")
    OUT_JS.write_text(
        "window.PAGE_MODULES=" + json.dumps(data, separators=(",", ":")) + ";\n"
    )

    totals = sorted(
        ((k, v["catalog"]["summary"].get("uniqueTotal", 0)) for k, v in pages.items()),
        key=lambda x: -x[1],
    )
    print(f"Wrote {OUT_JSON.name} — {len(pages)} pages")
    print(f"  Errors: {len(errors)}")
    print("  Top pages by unique HubSpot items:")
    for url, count in totals[:8]:
        s = pages[url]["catalog"]["summary"]
        print(
            f"    {count:3d} unique ({s.get('uniqueModules',0)} modules, "
            f"{s.get('uniqueSections',0)} sections)  {pages[url]['title']}"
        )

    usage_script = ROOT / "scripts" / "build-hs-usage.py"
    if usage_script.exists():
        subprocess.run(["python3", str(usage_script)], check=False, cwd=ROOT)


if __name__ == "__main__":
    main()
