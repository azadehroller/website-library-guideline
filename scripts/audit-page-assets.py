#!/usr/bin/env python3
"""Crawl Pages-tab URLs and extract unique media inside <main> only."""

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
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".ogv"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".aac"}
MEDIA_EXT = VIDEO_EXT | AUDIO_EXT

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

VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "wistia.net", "wistia.com", "loom.com", "vidyard.com")
INTERACTIVE_HOSTS = (
    "typeform.com",
    "calendly.com",
    "google.com/maps",
    "google.com/maps/embed",
    "hubspot.com",
    "hsforms.com",
    "spotify.com",
    "soundcloud.com",
    "codepen.io",
    "figma.com",
)


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


def filename_from_url(url: str) -> str:
    if url.startswith("data:"):
        return "inline data URI"
    path = unquote(urlparse(url).path)
    return path.rsplit("/", 1)[-1] or url


def classify_embed(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if any(h in host for h in VIDEO_HOSTS):
        return "video-embed"
    if any(h in host for h in INTERACTIVE_HOSTS):
        return "interactive"
    if host.endswith("roller.software"):
        return "interactive"
    return "interactive"


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

    path = re.sub(r"^/hs-fs/hubfs/", "/hubfs/", path, flags=re.I)

    ext = Path(path).suffix.lower()
    if ext and ext not in IMAGE_EXT:
        return None
    if not ext and "/hubfs/" not in path.lower():
        return None

    return f"https://www.roller.software{path}"


def normalize_media_file_url(url: str, page_url: str) -> str | None:
    url = html_lib.unescape(url.strip()).strip("'\"")
    if not url or url.startswith("data:"):
        return None
    full = urljoin(page_url, url)
    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return None
    if is_skippable_url(full):
        return None

    host = parsed.netloc.lower()
    path = unquote(parsed.path)
    ext = Path(path).suffix.lower()

    if host in ("www.roller.software", "roller.software"):
        qs = parse_qs(parsed.query)
        if "name" in qs and qs["name"]:
            path = f"/hubfs/{qs['name'][0].lstrip('/')}"
        path = re.sub(r"^/hs-fs/hubfs/", "/hubfs/", path, flags=re.I)
        if ext not in MEDIA_EXT:
            return None
        return f"https://www.roller.software{path}"

    if ext in MEDIA_EXT:
        return full
    return None


def normalize_embed_url(url: str, page_url: str) -> str | None:
    url = html_lib.unescape(url.strip()).strip("'\"")
    if not url or url.startswith("data:"):
        return None
    full = urljoin(page_url, url)
    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return None
    return full.split("#")[0]


def youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtu.be" in host:
        return parsed.path.strip("/").split("/")[0] or None
    if "youtube.com" in host:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        m = re.match(r"^/(embed|shorts)/([^/?]+)", parsed.path)
        if m:
            return m.group(2)
    return None


def vimeo_id(url: str) -> str | None:
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)", url, re.I)
    return m.group(1) if m else None


def wistia_thumbnail(wistia_id: str) -> str:
    return f"https://fast.wistia.com/embed/medias/{wistia_id}/swatch"


def embed_thumbnail(url: str, media_type: str, extra: dict | None = None) -> str:
    extra = extra or {}
    if media_type == "video-wistia" and extra.get("wistiaId"):
        return wistia_thumbnail(extra["wistiaId"])
    yt = youtube_id(url)
    if yt:
        return f"https://img.youtube.com/vi/{yt}/mqdefault.jpg"
    vm = vimeo_id(url)
    if vm:
        return f"https://vumbnail.com/{vm}.jpg"
    return ""


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
    return re.sub(r"\s+", " ", svg_html.strip())


def extract_assets(main_html: str, page_url: str) -> list[dict]:
    assets: dict[str, dict] = {}

    def add(asset: dict):
        key = asset["key"]
        if key in assets:
            existing = assets[key]
            for src in asset.get("sources", []):
                if src not in existing["sources"]:
                    existing["sources"].append(src)
            for field in ("alt", "title", "thumbnail", "embedUrl", "wistiaId"):
                if not existing.get(field) and asset.get(field):
                    existing[field] = asset[field]
            return
        assets[key] = asset

    def add_media_file(raw: str, source: str, title: str = ""):
        norm = normalize_media_file_url(raw, page_url)
        if not norm:
            return
        ext = Path(urlparse(norm).path).suffix.lower()
        kind = "audio" if ext in AUDIO_EXT else "video-file"
        add(
            {
                "key": f"{kind}:{norm}",
                "type": kind,
                "url": norm,
                "filename": filename_from_url(norm),
                "alt": title,
                "title": title or filename_from_url(norm),
                "sources": [source],
            }
        )

    def add_embed(raw: str, source: str, title: str = ""):
        norm = normalize_embed_url(raw, page_url)
        if not norm:
            return
        kind = classify_embed(norm)
        if "wistia" in norm.lower():
            kind = "video-embed"
        extra = {}
        thumb = embed_thumbnail(norm, kind, extra)
        label = title or filename_from_url(norm) or norm
        add(
            {
                "key": f"{kind}:{norm}",
                "type": kind,
                "url": norm,
                "embedUrl": norm,
                "filename": label,
                "alt": label,
                "title": label,
                "thumbnail": thumb,
                "sources": [source],
            }
        )

    def add_wistia(wistia_id: str, source: str, title: str = ""):
        wistia_id = wistia_id.strip().lower()
        embed = f"https://fast.wistia.net/embed/iframe/{wistia_id}"
        label = title or f"Wistia video {wistia_id}"
        add(
            {
                "key": f"video-wistia:{wistia_id}",
                "type": "video-wistia",
                "url": embed,
                "embedUrl": embed,
                "wistiaId": wistia_id,
                "filename": label,
                "alt": label,
                "title": label,
                "thumbnail": wistia_thumbnail(wistia_id),
                "sources": [source],
            }
        )

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
                add_media_file(raw, "img")
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
                    "title": alt or filename_from_url(norm),
                    "sources": ["img"],
                }
            )

    # <source> inside video/audio/picture
    for tag in re.findall(r"<source\b[^>]*>", main_html, re.I):
        srcset_m = re.search(r'\bsrcset="([^"]+)"', tag, re.I)
        src_m = re.search(r'\bsrc="([^"]+)"', tag, re.I)
        type_m = re.search(r'\btype="([^"]+)"', tag, re.I)
        mime = type_m.group(1).lower() if type_m else ""
        urls = []
        if srcset_m:
            for part in srcset_m.group(1).split(","):
                u = part.strip().split(" ")[0]
                if u:
                    urls.append(u)
        if src_m:
            urls.append(src_m.group(1))
        for raw in urls:
            if mime.startswith("audio/"):
                add_media_file(raw, "source[audio]")
            elif mime.startswith("video/"):
                add_media_file(raw, "source[video]")
            else:
                norm = normalize_image_url(raw, page_url)
                if norm:
                    add(
                        {
                            "key": f"image:{norm}",
                            "type": "image",
                            "url": norm,
                            "filename": filename_from_url(norm),
                            "alt": "",
                            "title": filename_from_url(norm),
                            "sources": ["source"],
                        }
                    )
                else:
                    add_media_file(raw, "source")

    # background-image: url(...)
    for match in re.finditer(r"background-image\s*:\s*url\((['\"]?)([^)'\"]+)\1\)", main_html, re.I):
        raw = match.group(2)
        norm = normalize_image_url(raw, page_url)
        if norm:
            add(
                {
                    "key": f"background:{norm}",
                    "type": "background",
                    "url": norm,
                    "filename": filename_from_url(norm),
                    "alt": "",
                    "title": filename_from_url(norm),
                    "sources": ["background-image"],
                }
            )
        else:
            add_media_file(raw, "background-image")

    # <video> blocks — poster, src, and nested sources
    for block in re.findall(r"<video\b[\s\S]*?(?:</video>|/>)", main_html, re.I):
        title_m = re.search(r'\btitle="([^"]+)"', block, re.I)
        title = html_lib.unescape(title_m.group(1)) if title_m else ""
        poster_m = re.search(r'\bposter="([^"]+)"', block, re.I)
        if poster_m:
            norm = normalize_image_url(poster_m.group(1), page_url)
            if norm:
                add(
                    {
                        "key": f"image:{norm}",
                        "type": "image",
                        "url": norm,
                        "filename": filename_from_url(norm) + " (poster)",
                        "alt": title,
                        "title": (title or "Video poster"),
                        "sources": ["video[poster]"],
                    }
                )
        src_m = re.search(r'\bsrc="([^"]+)"', block, re.I)
        if src_m:
            add_media_file(src_m.group(1), "video[src]", title)
        for src in re.findall(r'<source\b[^>]*\bsrc="([^"]+)"', block, re.I):
            add_media_file(src, "video[source]", title)

    # <audio> blocks
    for block in re.findall(r"<audio\b[\s\S]*?(?:</audio>|/>)", main_html, re.I):
        title_m = re.search(r'\btitle="([^"]+)"', block, re.I)
        title = html_lib.unescape(title_m.group(1)) if title_m else ""
        src_m = re.search(r'\bsrc="([^"]+)"', block, re.I)
        if src_m:
            add_media_file(src_m.group(1), "audio[src]", title)
        for src in re.findall(r'<source\b[^>]*\bsrc="([^"]+)"', block, re.I):
            add_media_file(src, "audio[source]", title)

    # iframes — video players and interactive embeds
    for tag in re.findall(r"<iframe\b[^>]*>", main_html, re.I):
        src_m = re.search(r'\bsrc="([^"]+)"', tag, re.I)
        title_m = re.search(r'\btitle="([^"]+)"', tag, re.I)
        title = html_lib.unescape(title_m.group(1)) if title_m else ""
        if src_m:
            add_embed(src_m.group(1), "iframe", title)

    # embed / object
    for tag in re.findall(r"<(?:embed|object)\b[^>]*>", main_html, re.I):
        for attr in ("src", "data"):
            m = re.search(rf'\b{attr}="([^"]+)"', tag, re.I)
            if m:
                add_embed(m.group(1), f"{tag[:6]}[{attr}]", "")

    # Wistia async/popover embeds
    for wistia_id in re.findall(r"wistia_async_([a-z0-9]+)", main_html, re.I):
        add_wistia(wistia_id, "wistia-async")
    for wistia_id in re.findall(r"wistia\.com/embed/medias/([a-z0-9]+)", main_html, re.I):
        add_wistia(wistia_id, "wistia-url")
    for wistia_id in re.findall(r"wistia\.net/embed/iframe/([a-z0-9]+)", main_html, re.I):
        add_wistia(wistia_id, "wistia-iframe-url")

    # YouTube / Vimeo URLs in attributes or inline links
    for raw in re.findall(
        r"https?://(?:www\.)?(?:youtube\.com/[^\s\"'<>]+|youtu\.be/[^\s\"'<>]+|vimeo\.com/[^\s\"'<>]+)",
        main_html,
        re.I,
    ):
        add_embed(raw.rstrip("\\\",')"), "embedded-url")

    # data-* media hints
    for attr, source in (
        (r'data-video-url="([^"]+)"', "data-video-url"),
        (r'data-src="([^"]+)"', "data-src"),
        (r'data-embed-url="([^"]+)"', "data-embed-url"),
        (r'data-wistia-id="([^"]+)"', "data-wistia-id"),
    ):
        for raw in re.findall(attr, main_html, re.I):
            cleaned = html_lib.unescape(raw)
            if re.fullmatch(r"[a-z0-9]+", cleaned, re.I) and "wistia" in source:
                add_wistia(cleaned, source)
            elif cleaned.startswith("http"):
                if classify_embed(cleaned) == "video-embed":
                    add_embed(cleaned, source)
                else:
                    add_media_file(cleaned, source)
            else:
                add_media_file(cleaned, source)

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
                "title": label,
                "svgId": digest,
                "preview": preview,
                "sources": ["inline-svg"],
            }
        )

    # HubSpot hubfs image URLs embedded in markup
    for raw in re.findall(
        r"https?://(?:www\.)?roller\.software/(?:hs-fs/)?hubfs/[^\s\"'<>]+",
        main_html,
        re.I,
    ):
        cleaned = html_lib.unescape(raw.rstrip("\\\",')"))
        norm = normalize_image_url(cleaned, page_url)
        if norm:
            ext = Path(urlparse(norm).path).suffix.lower()
            kind = "svg-image" if ext == ".svg" else "image"
            add(
                {
                    "key": f"{kind}:{norm}",
                    "type": kind,
                    "url": norm,
                    "filename": filename_from_url(norm),
                    "alt": "",
                    "title": filename_from_url(norm),
                    "sources": ["embedded-url"],
                }
            )
        else:
            add_media_file(cleaned, "embedded-url")

    # Standalone media file URLs in markup
    for raw in re.findall(
        r"https?://[^\s\"'<>]+\.(?:mp4|webm|mov|m4v|mp3|wav|ogg|m4a|aac)(?:\?[^\s\"'<>]*)?",
        main_html,
        re.I,
    ):
        add_media_file(html_lib.unescape(raw.rstrip("\\\",')")), "embedded-url")

    result = list(assets.values())
    type_order = {
        "image": 0,
        "svg-image": 1,
        "background": 2,
        "video-wistia": 3,
        "video-file": 4,
        "video-embed": 5,
        "audio": 6,
        "interactive": 7,
        "svg-inline": 8,
    }
    result.sort(key=lambda a: (type_order.get(a["type"], 9), a.get("filename", "").lower()))
    for item in result:
        item.pop("key", None)
    return result


def main():
    sections = extract_page_sections()
    pages = [p for s in sections for p in s["pages"]]
    print(f"Crawling {len(pages)} URLs for main-content media…")

    bodies: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as ex:
        for url, body in ex.map(fetch, [p["url"] for p in pages]):
            bodies[url] = body

    audited_sections = []
    total_assets = 0
    unique_keys: set[str] = set()
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
                        unique_keys.add(a["type"] + ":" + a["url"])
                    elif a.get("svgId"):
                        unique_keys.add("svg-inline:" + a["svgId"])
            audited_pages.append(entry)
        audited_sections.append({"name": section["name"], "pages": audited_pages})

    data = {
        "version": 2,
        "audited": "2026-06",
        "pageCount": len(pages),
        "totalAssets": total_assets,
        "uniqueAssets": len(unique_keys),
        "errors": errors,
        "sections": audited_sections,
    }

    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")
    OUT_JS.write_text("window.PAGE_ASSETS=" + json.dumps(data, separators=(",", ":")) + ";\n")

    print(f"Wrote {OUT_JSON.name} — {len(pages)} pages, {total_assets} media items ({len(unique_keys)} unique)")
    if errors:
        print(f"  Errors: {len(errors)}")


if __name__ == "__main__":
    main()
