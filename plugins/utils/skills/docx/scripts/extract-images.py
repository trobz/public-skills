#!/usr/bin/env python3
"""Extract embedded images from a DOCX file."""

import argparse
import sys
import zipfile
from pathlib import Path


def check_deps():
    try:
        from lxml import etree  # noqa: F401
    except ImportError:
        print("Missing package: lxml", file=sys.stderr)
        print(
            f'Install with: uv sync --project "{Path(__file__).parent}"',
            file=sys.stderr,
        )
        sys.exit(1)


def extract_images(docx_path: Path, output_dir: Path) -> tuple[dict[str, str], int]:
    """Extract all images to output_dir. Returns ({rId: filename}, total_count)."""
    from lxml import etree

    output_dir.mkdir(parents=True, exist_ok=True)
    rId_map: dict[str, str] = {}

    with zipfile.ZipFile(docx_path) as z:
        media_files = [f for f in z.namelist() if f.startswith("word/media/")]
        for media_path in media_files:
            filename = Path(media_path).name
            with z.open(media_path) as src, open(output_dir / filename, "wb") as dst:
                dst.write(src.read())

        try:
            with z.open("word/_rels/document.xml.rels") as f:
                tree = etree.parse(f)
            for rel in tree.getroot():
                rid = rel.get("Id")
                target = rel.get("Target", "")
                if "media/" in target:
                    rId_map[rid] = Path(target).name
        except KeyError:
            pass

    return rId_map, len(media_files)


def main():
    parser = argparse.ArgumentParser(description="Extract images from a DOCX file")
    parser.add_argument("docx", help="Path to the DOCX file")
    parser.add_argument(
        "--output-dir",
        default="./images",
        metavar="DIR",
        help="Directory to extract images into (default: ./images)",
    )
    args = parser.parse_args()

    check_deps()

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"Error: file not found: {docx_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    rId_map, count = extract_images(docx_path, output_dir)

    print(f"Extracted {count} images → {output_dir}")
    print()
    for rid, filename in sorted(rId_map.items(), key=lambda x: x[0]):
        print(f"{rid}\t{filename}")


if __name__ == "__main__":
    main()
