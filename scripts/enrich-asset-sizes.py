#!/usr/bin/env python3
"""Add fileSize (bytes) to each asset in page-assets.json via HEAD requests."""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "page-assets.json"
OUT_JS = ROOT / "page-assets.data.js"


def encode_request_url(url: str) -> str:
    parts = urlsplit(url)
    path = quote(parts.path, safe="/:@!$&'()*+,;=-._~")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def head_content_length(url: str) -> int | None:
    request_url = encode_request_url(url)
    try:
        r = subprocess.run(
            ["curl", "-sI", "--max-time", "15", request_url],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            if line.lower().startswith("content-length:"):
                value = line.split(":", 1)[1].strip()
                if value.isdigit():
                    return int(value)
        return None
    except Exception:
        return None


def inline_svg_bytes(asset: dict) -> int | None:
    preview = asset.get("preview")
    if not preview:
        return None
    return len(preview.encode("utf-8"))


def collect_unique_urls(data: dict) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for section in data.get("sections", []):
        for page in section.get("pages", []):
            for asset in page.get("assets", []):
                url = asset.get("url") or asset.get("embedUrl")
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)
    return urls


def enrich_asset_sizes(data: dict, workers: int = 20) -> tuple[int, int]:
    url_sizes: dict[str, int | None] = {}
    urls = collect_unique_urls(data)
    print(f"Fetching sizes for {len(urls)} unique URLs…")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for url, size in ex.map(lambda u: (u, head_content_length(u)), urls):
            url_sizes[url] = size

    resolved = sum(1 for s in url_sizes.values() if s is not None)
    print(f"  Resolved {resolved}/{len(urls)} URL sizes")

    enriched = 0
    for section in data.get("sections", []):
        for page in section.get("pages", []):
            for asset in page.get("assets", []):
                size = None
                if asset.get("type") == "svg-inline":
                    size = inline_svg_bytes(asset)
                else:
                    url = asset.get("url") or asset.get("embedUrl")
                    if url:
                        size = url_sizes.get(url)
                if size is not None:
                    asset["fileSize"] = size
                    enriched += 1
                else:
                    asset.pop("fileSize", None)

    return enriched, len(urls)


def write_outputs(data: dict) -> None:
    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")
    OUT_JS.write_text("window.PAGE_ASSETS=" + json.dumps(data, separators=(",", ":")) + ";\n")


def main() -> None:
    if not OUT_JSON.is_file():
        raise SystemExit(f"Missing {OUT_JSON.name}. Run scripts/audit-page-assets.py first.")

    data = json.loads(OUT_JSON.read_text())
    enriched, unique = enrich_asset_sizes(data)
    write_outputs(data)
    print(f"Wrote {OUT_JSON.name} — fileSize on {enriched} assets ({unique} unique URLs checked)")


if __name__ == "__main__":
    main()
