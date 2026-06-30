#!/usr/bin/env python3
"""Crawl Pages-tab URLs and extract unique visual assets inside <main> only."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import subprocess
import html as html_lib
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
OUT_JSON = ROOT / "page-assets.json"
OUT_JS = ROOT / "page-assets.data.js"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".ico"}
SKIP_PATH_PARTS = (
    "/hub_generated/module_assets/",
    "/hub_generated/template_assets/",
    ".min.css",
    ".min.js",
    "/hs/hsstatic/",
)
SKIP_IMAGE_NAMES = {
    "favicon",
    "apple-touch-icon",
    "spacer.gif",
    "blank.gif",
    "pixel.gif",
    "1x1",
}


def extract_page_sections() -> list[dict]:
    html = INDEX.read_text()
    panel = html.split('id="panel-pages"')[1].split("</div><!-- /panel-pages -->")[0]
    sections: list[dict] = []
    for block in re.findall(r"<details class=\"phase\">(.*?)</details>", panel, re.S):
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
    # Fallback: body minus header/footer landmarks when main is missing
    body_m = re.search(r"<body\b[^>]*>(.*)</body>", body, re.I | re.S)
    chunk = body_m.group(1) if body_m else body
    chunk = re.sub(r"<header\b[^>]*>.*?</header>", "", chunk, flags=re.I | re.S)
    chunk = re.sub(r"<footer\b[^>]*>.*?</footer>", "", chunk, flags=re.I | re.S)
    return chunk


def is_skippable_url(url: str) -> bool:
    lower = url.lower()
    if any(part in lower for part in SKIP_PATH_PARTS):
        return True
    path = unquote(urlparse(url).path).lower()
    name = path.rsplit("/", 1)[-1]
    if any(skip in name for skip in SKIP_IMAGE_NAMES):
        return True
    return False


def normalize_image_url(url: str, page_url: str) -> str | None:
    url = html_lib.unescape(url.strip()).strip("'\"")
    if not url or url.startswith("data:"):
        return url if url.startswith("data:") else None
    full = urljoin(page_url, url)
    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return None
    if is_skippable_url(full):
        return None

    host = parsed.netloc.lower()
    if host not in ("www.roller.software", "roller.software"):
        return None

    path = unquote(parsed.path)
    qs = parse_qs(parsed.query)
    if "name" in qs and qs["name"]:
        filename = qs["name"][0]
        path = f"/hubfs/{filename.lstrip('/')}"

    # hs-fs/hubfs → hubfs canonical path
    path = re.sub(r"^/hs-fs/hubfs/", "/hubfs/", path, flags=re.I)

    ext = Path(path).suffix.lower()
    if ext and ext not in IMAGE_EXT:
        return None
    if not ext and "/hubfs/" not in path.lower():
        return None

    return f"https://www.roller.software{path}"


def filename_from_url(url: str) -> str:
    if url.startswith("data:"):
        return "inline data URI"
    path = unquote(urlparse(url).path)
    return path.rsplit("/", 1)[-1] or url


def svg_label(svg_html: str) -> str:
    aria = re.search(r'aria-label="([^"]+)"', svg_html, re.I)
    if aria:
        return aria.group(1).strip()
    title = re.search(r"<title[^>]*>([^<]+)</title>", svg_html, re.I)
    if title:
        return title.group(1).strip()
    cls = re.search(r'class="([^"]+)"', svg_html, re.I)
    if cls:
        return cls.group(1).strip().split()[0]
    view = re.search(r'viewBox="([^"]+)"', svg_html, re.I)
    if view:
        parts = view.group(1).split()
        if len(parts) == 4:
            return f"SVG {parts[2]}×{parts[3]}"
    w = re.search(r'\bwidth="([0-9.]+)"', svg_html, re.I)
    h = re.search(r'\bheight="([0-9.]+)"', svg_html, re.I)
    if w and h:
        return f"SVG {w.group(1)}×{h.group(1)}"
    return "Inline SVG"


def normalize_svg(svg_html: str) -> str:
    inner = re.sub(r"\s+", " ", svg_html.strip())
    return inner


def extract_assets(main_html: str, page_url: str) -> list[dict]:
    assets: dict[str, dict] = {}

    def add(asset: dict):
        key = asset["key"]
        if key in assets:
            existing = assets[key]
            for src in asset.get("sources", []):
                if src not in existing["sources"]:
                    existing["sources"].append(src)
            if not existing.get("alt") and asset.get("alt"):
                existing["alt"] = asset["alt"]
            return
        assets[key] = asset

    # <img src> and srcset
    for tag in re.findall(r"<img\b[^>]*>", main_html, re.I):
        src_m = re.search(r'\bsrc="([^"]+)"', tag, re.I)
        alt_m = re.search(r'\balt="([^"]*)"', tag, re.I)
        alt = html_lib.unescape(alt_m.group(1)) if alt_m else ""
        urls = []
        if src_m:
            urls.append(src_m.group(1))
        srcset_m = re.search(r'\bsrcset="([^"]+)"', tag, re.I)
        if srcset_m:
            for part in srcset_m.group(1).split(","):
                u = part.strip().split(" ")[0]
                if u:
                    urls.append(u)
        for raw in urls:
            norm = normalize_image_url(raw, page_url)
            if not norm:
                continue
            ext = Path(urlparse(norm).path).suffix.lower()
            kind = "svg-image" if ext == ".svg" else "image"
            add(
                {
                    "key": f"{kind}:{norm}",
                    "type": kind,
                    "url": norm,
                    "filename": filename_from_url(norm),
                    "alt": alt,
                    "sources": ["img"],
                }
            )

    # <source srcset> inside picture/video
    for tag in re.findall(r"<source\b[^>]*>", main_html, re.I):
        srcset_m = re.search(r'\bsrcset="([^"]+)"', tag, re.I)
        src_m = re.search(r'\bsrc="([^"]+)"', tag, re.I)
        urls = []
        if srcset_m:
            for part in srcset_m.group(1).split(","):
                u = part.strip().split(" ")[0]
                if u:
                    urls.append(u)
        if src_m:
            urls.append(src_m.group(1))
        for raw in urls:
            norm = normalize_image_url(raw, page_url)
            if not norm:
                continue
            add(
                {
                    "key": f"image:{norm}",
                    "type": "image",
                    "url": norm,
                    "filename": filename_from_url(norm),
                    "alt": "",
                    "sources": ["source"],
                }
            )

    # background-image: url(...)
    for match in re.finditer(r"background-image\s*:\s*url\((['\"]?)([^)'\"]+)\1\)", main_html, re.I):
        norm = normalize_image_url(match.group(2), page_url)
        if not norm:
            continue
        add(
            {
                "key": f"background:{norm}",
                "type": "background",
                "url": norm,
                "filename": filename_from_url(norm),
                "alt": "",
                "sources": ["background-image"],
            }
        )

    # <video poster> and src
    for tag in re.findall(r"<video\b[^>]*>", main_html, re.I):
        for attr in ("poster", "src"):
            m = re.search(rf'\b{attr}="([^"]+)"', tag, re.I)
            if not m:
                continue
            norm = normalize_image_url(m.group(1), page_url)
            if not norm:
                continue
            add(
                {
                    "key": f"video:{norm}",
                    "type": "video",
                    "url": norm,
                    "filename": filename_from_url(norm),
                    "alt": "",
                    "sources": [f"video[{attr}]"],
                }
            )

    # Inline SVG blocks
    for svg in re.findall(r"<svg\b[\s\S]*?</svg>", main_html, re.I):
        normalized = normalize_svg(svg)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
        label = svg_label(svg)
        preview = normalized if len(normalized) <= 1200 else normalized[:1200] + "…"
        add(
            {
                "key": f"svg-inline:{digest}",
                "type": "svg-inline",
                "url": "",
                "filename": label,
                "alt": label,
                "svgId": digest,
                "preview": preview,
                "sources": ["inline-svg"],
            }
        )

    # HubSpot image URLs embedded in attributes / JSON-ish blobs
    for raw in re.findall(
        r"https?://(?:www\.)?roller\.software/(?:hs-fs/)?hubfs/[^\s\"'<>]+",
        main_html,
        re.I,
    ):
        cleaned = html_lib.unescape(raw.rstrip("\\\",')"))
        norm = normalize_image_url(cleaned, page_url)
        if not norm:
            continue
        ext = Path(urlparse(norm).path).suffix.lower()
        kind = "svg-image" if ext == ".svg" else "image"
        add(
            {
                "key": f"{kind}:{norm}",
                "type": kind,
                "url": norm,
                "filename": filename_from_url(norm),
                "alt": "",
                "sources": ["embedded-url"],
            }
        )

    result = list(assets.values())
    type_order = {"image": 0, "svg-image": 1, "background": 2, "video": 3, "svg-inline": 4}
    result.sort(key=lambda a: (type_order.get(a["type"], 9), a.get("filename", "").lower()))
    for item in result:
        item.pop("key", None)
    return result


def audit_page(page: dict, body: str) -> dict:
    url = page["url"]
    if not body.strip():
        return {
            **page,
            "assetCount": 0,
            "assets": [],
            "error": "Failed to fetch page HTML",
        }
    main_html = extract_main_html(body)
    if not main_html.strip():
        return {
            **page,
            "assetCount": 0,
            "assets": [],
            "error": "No <main> content found",
        }
    assets = extract_assets(main_html, url)
    return {**page, "assetCount": len(assets), "assets": assets, "error": None}


def main():
    sections = extract_page_sections()
    pages = [p for s in sections for p in s["pages"]]
    print(f"Crawling {len(pages)} URLs for main-content assets…")

    bodies: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as ex:
        for url, body in ex.map(fetch, [p["url"] for p in pages]):
            bodies[url] = body

    audited_sections = []
    total_assets = 0
    unique_urls: set[str] = set()
    errors = []

    for section in sections:
        audited_pages = []
        for page in section["pages"]:
            body = bodies.get(page["url"], "")
            main_html = extract_main_html(body) if body.strip() else ""
            if not body.strip():
                entry = {**page, "assetCount": 0, "assets": [], "error": "Failed to fetch page HTML"}
                errors.append(page["url"])
            elif not main_html.strip():
                entry = {**page, "assetCount": 0, "assets": [], "error": "No <main> content found"}
                errors.append(page["url"])
            else:
                assets = extract_assets(main_html, page["url"])
                entry = {**page, "assetCount": len(assets), "assets": assets, "error": None}
                total_assets += len(assets)
                for a in assets:
                    if a.get("url"):
                        unique_urls.add(a["url"])
                    elif a.get("svgId"):
                        unique_urls.add(f"svg:{a['svgId']}")
            audited_pages.append(entry)
        audited_sections.append({"name": section["name"], "pages": audited_pages})

    data = {
        "version": 1,
        "audited": "2026-06",
        "pageCount": len(pages),
        "totalAssets": total_assets,
        "uniqueAssets": len(unique_urls),
        "errors": errors,
        "sections": audited_sections,
    }

    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")
    OUT_JS.write_text("window.PAGE_ASSETS=" + json.dumps(data, separators=(",", ":")) + ";\n")

    print(f"Wrote {OUT_JSON.name} — {len(pages)} pages, {total_assets} assets ({len(unique_urls)} unique)")
    if errors:
        print(f"  Errors: {len(errors)}")


if __name__ == "__main__":
    main()
