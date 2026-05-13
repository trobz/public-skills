#!/usr/bin/env python3
"""Convert PDFs to Markdown using pymupdf4llm with footer noise removal."""

import argparse
from collections import Counter
import re
import sys


REPEATED_FOOTER_MIN_COUNT = 3


def check_deps():
    try:
        import pymupdf4llm  # noqa: F401
    except ImportError:
        print("Missing package: pymupdf4llm", file=sys.stderr)
        print("Install with: pip install pymupdf4llm", file=sys.stderr)
        sys.exit(1)


def parse_pages(pages_str: str) -> list[int]:
    pages = []
    for part in pages_str.split(","):
        if "-" in part:
            start, end = part.split("-")
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def normalize_footer_candidate(line: str) -> str:
    """Normalize quote markers and whitespace before comparing repeated lines."""
    line = re.sub(r"^\s*>\s*", "", line)
    return re.sub(r"\s+", " ", line).strip()


def is_probable_footer_line(line: str) -> bool:
    if not line:
        return False

    lower = line.lower()
    has_separator = bool(re.search(r"[_\-\u2013\u2014]{8,}", line))
    has_contact = bool(
        re.search(
            r"\b[\w.+-]+@[\w.-]+\.\w+\b|https?://|www\.|\b\w+\.\w{2,}\b",
            lower,
        )
    )
    has_footer_word = bool(re.search(r"\b(page|copyright|confidential|all rights reserved)\b", lower))
    has_address_layout = line.count("|") >= 2

    return has_separator or has_footer_word or (has_contact and has_address_layout)


def remove_repeated_footer_lines(text: str) -> str:
    lines = text.splitlines()
    normalized_counts = Counter(
        normalize_footer_candidate(line)
        for line in lines
        if normalize_footer_candidate(line)
    )

    cleaned_lines = []
    for line in lines:
        normalized = normalize_footer_candidate(line)
        if (
            normalized_counts[normalized] >= REPEATED_FOOTER_MIN_COUNT
            and is_probable_footer_line(normalized)
        ):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def clean_footers(text: str, footer_pattern: str | None) -> str:
    # Strip standalone page numbers (e.g. lines with only digits)
    text = re.sub(r"(?m)^\s*\d+\s*$", "", text)
    text = remove_repeated_footer_lines(text)

    if footer_pattern:
        text = re.sub(footer_pattern, "", text, flags=re.DOTALL | re.MULTILINE)

    # Collapse 3+ consecutive blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_to_markdown(pdf_path: str, pages: list[int] | None = None) -> str:
    import pymupdf4llm

    kwargs: dict = {}
    if pages:
        # pymupdf4llm uses 0-based page indices
        kwargs["pages"] = [p - 1 for p in pages]

    return pymupdf4llm.to_markdown(pdf_path, **kwargs)


def main():
    parser = argparse.ArgumentParser(description="Convert PDF to Markdown")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--pages", help="Page range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--footer-pattern", help="Regex to strip repeating footer noise")
    parser.add_argument("--no-clean", action="store_true", help="Skip footer cleaning")
    parser.add_argument("--output", help="Write output to this file instead of stdout")
    args = parser.parse_args()

    check_deps()

    pages = parse_pages(args.pages) if args.pages else None
    md = pdf_to_markdown(args.pdf, pages=pages)

    if not args.no_clean:
        md = clean_footers(md, args.footer_pattern)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Markdown written to: {args.output}")
    else:
        print(md)


if __name__ == "__main__":
    main()
