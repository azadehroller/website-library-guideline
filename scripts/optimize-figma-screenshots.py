#!/usr/bin/env python3
"""Resize and compress figma-screenshots/ PNGs for the guideline site.

Thumbnails render at max-height 200px; lightbox uses the same files at full
resolution. Caps dimensions at 1280×1800 then runs pngquant when available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "figma-screenshots"
MAX_W = 1280
MAX_H = 1800


def dims(path: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        text=True,
    )
    w = h = 0
    for line in out.splitlines():
        if "pixelWidth" in line:
            w = int(line.split()[-1])
        if "pixelHeight" in line:
            h = int(line.split()[-1])
    return w, h


def resize(path: Path) -> bool:
    w, h = dims(path)
    scale = min(1.0, MAX_W / w, MAX_H / h)
    if scale >= 1.0:
        return False
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    subprocess.run(
        ["sips", "-z", str(nh), str(nw), str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return True


def compress(path: Path) -> bool:
    if not shutil.which("pngquant"):
        return False
    tmp = path.with_suffix(".tmp.png")
    result = subprocess.run(
        [
            "pngquant",
            "--force",
            "--skip-if-larger",
            "--quality=65-90",
            "--output",
            str(tmp),
            str(path),
        ],
        capture_output=True,
    )
    if result.returncode == 0 and tmp.exists():
        tmp.replace(path)
        return True
    if tmp.exists():
        tmp.unlink()
    return False


def main() -> int:
    if not SHOTS.is_dir():
        print(f"Missing {SHOTS}", file=sys.stderr)
        return 1
    resized = compressed = 0
    before_total = sum(p.stat().st_size for p in SHOTS.glob("*.png"))
    for path in sorted(SHOTS.glob("*.png")):
        if resize(path):
            resized += 1
        if compress(path):
            compressed += 1
    after_total = sum(p.stat().st_size for p in SHOTS.glob("*.png"))
    saved = before_total - after_total
    print(
        f"figma-screenshots: resized {resized}, compressed {compressed}, "
        f"saved {saved / 1024 / 1024:.1f} MB ({before_total / 1024 / 1024:.1f} → {after_total / 1024 / 1024:.1f} MB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
