#!/usr/bin/env python3
"""Extract text from scanned PDFs using OCR (tesseract + pdf2image)."""

import argparse
import sys


def check_deps():
    missing = []
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        missing.append("pytesseract")
    try:
        from pdf2image import convert_from_path  # noqa: F401
    except ImportError:
        missing.append("pdf2image")
    if missing:
        print(f"Missing packages: {', '.join(missing)}", file=sys.stderr)
        print(f"Install with: pip install {' '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def ocr_pdf(pdf_path: str, pages: list[int] | None = None, lang: str = "eng") -> str:
    import pytesseract
    from pdf2image import convert_from_path

    convert_kwargs: dict = {}
    if pages:
        convert_kwargs["first_page"] = min(pages)
        convert_kwargs["last_page"] = max(pages)

    images = convert_from_path(pdf_path, **convert_kwargs)
    parts = []
    for i, image in enumerate(images):
        page_num = (min(pages) + i) if pages else (i + 1)
        text = pytesseract.image_to_string(image, lang=lang)
        parts.append(f"=== Page {page_num} ===\n{text}")

    return "\n\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="OCR text from a scanned PDF")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--pages", help="Page range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--lang", default="eng", help="Tesseract language code (default: eng)")
    parser.add_argument("--output", help="Write output to this file instead of stdout")
    args = parser.parse_args()

    check_deps()

    pages: list[int] | None = None
    if args.pages:
        pages = []
        for part in args.pages.split(","):
            if "-" in part:
                start, end = part.split("-")
                pages.extend(range(int(start), int(end) + 1))
            else:
                pages.append(int(part))

    text = ocr_pdf(args.pdf, pages=pages, lang=args.lang)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"OCR text written to: {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
