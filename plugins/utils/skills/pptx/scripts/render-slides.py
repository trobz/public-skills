#!/usr/bin/env python3
"""Render PPTX slides to PNG images via LibreOffice + pdf2image."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def check_deps():
    if shutil.which("soffice") is None:
        print("Missing system binary: soffice (LibreOffice)", file=sys.stderr)
        print("Install with: brew install --cask libreoffice  # macOS", file=sys.stderr)
        print("              apt install libreoffice          # Debian/Ubuntu", file=sys.stderr)
        sys.exit(1)
    try:
        from pdf2image import convert_from_path  # noqa: F401
    except ImportError:
        print("Missing package: pdf2image", file=sys.stderr)
        print("Install with: pip install pdf2image", file=sys.stderr)
        sys.exit(1)


def parse_slides(slides_str: str) -> list[int]:
    slides = []
    for part in slides_str.split(","):
        if "-" in part:
            start, end = part.split("-")
            slides.extend(range(int(start), int(end) + 1))
        else:
            slides.append(int(part))
    return slides


def render(pptx_path: str, output_dir: str, slides: list[int] | None, dpi: int) -> list[str]:
    from pdf2image import convert_from_path

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, pptx_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("soffice failed:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)

        base = os.path.splitext(os.path.basename(pptx_path))[0]
        pdf_path = os.path.join(tmp, f"{base}.pdf")
        if not os.path.exists(pdf_path):
            print(f"Expected PDF not produced at {pdf_path}", file=sys.stderr)
            sys.exit(1)

        convert_kwargs: dict = {"dpi": dpi}
        if slides:
            convert_kwargs["first_page"] = min(slides)
            convert_kwargs["last_page"] = max(slides)

        images = convert_from_path(pdf_path, **convert_kwargs)

    selected = set(slides) if slides else None
    base_index = (min(slides) if slides else 1)

    written: list[str] = []
    for offset, image in enumerate(images):
        slide_num = base_index + offset
        if selected is not None and slide_num not in selected:
            continue
        out_path = os.path.join(output_dir, f"slide-{slide_num}.png")
        image.save(out_path, "PNG")
        written.append(out_path)

    return written


def main():
    parser = argparse.ArgumentParser(description="Render PPTX slides to PNG images")
    parser.add_argument("pptx", help="Path to the PPTX file")
    parser.add_argument("--output-dir", required=True, help="Directory to write PNG files")
    parser.add_argument("--slides", help="Slide range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--dpi", type=int, default=150, help="Render DPI (default: 150)")
    args = parser.parse_args()

    check_deps()

    slides = parse_slides(args.slides) if args.slides else None
    written = render(args.pptx, args.output_dir, slides=slides, dpi=args.dpi)

    if not written:
        print("No slides rendered.")
        return

    for path in written:
        print(f"Wrote: {path}")


if __name__ == "__main__":
    main()
