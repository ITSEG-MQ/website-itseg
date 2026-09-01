#!/usr/bin/env python3
"""Build deterministic, lightweight UI assets from legacy brand sources."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/pic/brand/logo.png"
OUTPUT = ROOT / "assets/ui/itseg-logo.webp"
MAX_DIMENSION = 320
WEBP_QUALITY = 82
WEBP_METHOD = 6


def render_logo() -> tuple[bytes, tuple[int, int]]:
    """Return the generated WebP bytes and intrinsic dimensions."""
    with Image.open(SOURCE) as source:
        source.load()
        logo = source.convert("RGBA")
    logo.thumbnail(
        (MAX_DIMENSION, MAX_DIMENSION),
        Image.Resampling.LANCZOS,
        reducing_gap=3.0,
    )
    rendered = io.BytesIO()
    logo.save(
        rendered,
        format="WEBP",
        lossless=False,
        quality=WEBP_QUALITY,
        method=WEBP_METHOD,
        exact=True,
    )
    return rendered.getvalue(), logo.size


def asset_errors() -> list[str]:
    """Report missing, stale, or incorrectly sized generated UI assets."""
    if not SOURCE.is_file():
        return [f"UI asset source is missing: {SOURCE.relative_to(ROOT)}"]
    expected, dimensions = render_logo()
    if max(dimensions) > MAX_DIMENSION:
        return [
            f"generated UI logo exceeds {MAX_DIMENSION}px: "
            f"{dimensions[0]}x{dimensions[1]}"
        ]
    if not OUTPUT.is_file():
        return [f"generated UI asset is missing: {OUTPUT.relative_to(ROOT)}"]
    if OUTPUT.read_bytes() != expected:
        return [
            f"generated UI asset is stale: run python3 "
            f"{Path(__file__).relative_to(ROOT)}"
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the committed output without modifying it",
    )
    args = parser.parse_args()

    if args.check:
        errors = asset_errors()
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        with Image.open(OUTPUT) as logo:
            width, height = logo.size
        print(
            f"PASS: {OUTPUT.relative_to(ROOT)} is current "
            f"({width}x{height}, {OUTPUT.stat().st_size} bytes)"
        )
        return 0

    rendered, (width, height) = render_logo()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUTPUT.is_file() or OUTPUT.read_bytes() != rendered:
        OUTPUT.write_bytes(rendered)
    print(
        f"Built {OUTPUT.relative_to(ROOT)} from {SOURCE.relative_to(ROOT)} "
        f"({width}x{height}, {len(rendered)} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
