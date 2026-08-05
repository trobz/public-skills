#!/usr/bin/env python3
"""Extract embedded images from a DOCX file."""

import argparse
import hashlib
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


def content_hash(data: bytes) -> str:
    """First 16 hex chars of sha256(data) — the content-address for an image."""
    return hashlib.sha256(data).hexdigest()[:16]


def content_hash_filename(data: bytes, original_name: str) -> str:
    """Content-addressed filename: sha256(bytes)[:16] + original extension.

    Kept identical to docx-to-markdown.py's helper of the same name so both
    scripts agree on a filename for the same image bytes. See that module's
    docstring for why Word-internal names (e.g. "image1339.png") aren't used.
    """
    ext = Path(original_name).suffix.lower()
    return f"{content_hash(data)}{ext}"


def build_existing_hash_index(existing_dir: "Path | None") -> dict[str, str]:
    """Map content hash → filename for files already in existing_dir (top-level only).

    Kept identical to docx-to-markdown.py's helper of the same name — see that
    module's docstring for why this stays non-recursive and why the two
    scripts must be pointed at the same directory to reuse names consistently.
    """
    index: dict[str, str] = {}
    if not existing_dir or not existing_dir.is_dir():
        return index
    for f in existing_dir.iterdir():
        if f.is_file():
            index[content_hash(f.read_bytes())] = f.name
    return index


def extract_images(
    docx_path: Path,
    output_dir: Path,
    existing_images_dir: Path | None = None,
) -> tuple[dict[str, str], int, int]:
    """Extract images to output_dir. Returns ({rId: filename}, total_count, reused_count).

    An image whose content hash matches a file already in existing_images_dir
    is left untouched on disk and its existing filename is reused in the
    returned map, instead of writing a duplicate under a fresh hash name.
    """
    from lxml import etree

    output_dir.mkdir(parents=True, exist_ok=True)
    existing_index = build_existing_hash_index(existing_images_dir)
    rId_map: dict[str, str] = {}

    with zipfile.ZipFile(docx_path) as z:
        media_files = [f for f in z.namelist() if f.startswith("word/media/")]
        media_hashes: dict[str, str] = {}
        reused = 0
        for media_path in media_files:
            data = z.read(media_path)
            h = content_hash(data)
            reused_name = existing_index.get(h)
            if reused_name:
                filename = reused_name
                reused += 1
            else:
                filename = content_hash_filename(data, media_path)
                with open(output_dir / filename, "wb") as dst:
                    dst.write(data)
            media_hashes[media_path] = filename

        try:
            with z.open("word/_rels/document.xml.rels") as f:
                tree = etree.parse(f)
            for rel in tree.getroot():
                rid = rel.get("Id")
                target = rel.get("Target", "")
                if "media/" not in target:
                    continue
                media_path = f"word/{target}"
                if media_path in media_hashes:
                    rId_map[rid] = media_hashes[media_path]
        except KeyError:
            pass

    return rId_map, len(media_files), reused


def main():
    parser = argparse.ArgumentParser(description="Extract images from a DOCX file")
    parser.add_argument("docx", help="Path to the DOCX file")
    parser.add_argument(
        "--output-dir",
        default="./images",
        metavar="DIR",
        help="Directory to extract images into (default: ./images)",
    )
    parser.add_argument(
        "--existing-images-dir",
        metavar="DIR",
        help=(
            "Directory to check for already-present images (matched by content "
            "hash) before extracting a new one. Skips writing a duplicate and "
            "reuses that file's existing name — pass the same directory as "
            "--output-dir to sync into a directory in place without renaming "
            "unchanged images."
        ),
    )
    args = parser.parse_args()

    check_deps()

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"Error: file not found: {docx_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    existing_images_dir = Path(args.existing_images_dir) if args.existing_images_dir else None
    rId_map, count, reused = extract_images(docx_path, output_dir, existing_images_dir)

    print(f"Extracted {count - reused} new images, reused {reused} unchanged → {output_dir}")
    print()
    for rid, filename in sorted(rId_map.items(), key=lambda x: x[0]):
        print(f"{rid}\t{filename}")


if __name__ == "__main__":
    main()
