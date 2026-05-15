#!/usr/bin/env python3
"""Extract tables from PDFs using pdfplumber."""

import argparse
import csv
import io
import sys


def check_deps():
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        print("Missing package: pdfplumber", file=sys.stderr)
        print("Install with: pip install pdfplumber", file=sys.stderr)
        sys.exit(1)


def extract_tables(pdf_path: str, pages: list[int] | None = None) -> list[dict]:
    import pdfplumber

    results = []
    with pdfplumber.open(pdf_path) as pdf:
        page_iter = (
            [(i, pdf.pages[i - 1]) for i in pages if 0 < i <= len(pdf.pages)]
            if pages
            else enumerate(pdf.pages, start=1)
        )
        for page_num, page in page_iter:
            tables = page.extract_tables()
            for table_idx, table in enumerate(tables, start=1):
                if table:
                    results.append({"page": page_num, "table": table_idx, "data": table})

    return results


def format_as_csv(table_data: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(table_data)
    return buf.getvalue()


def format_as_text(table_data: list) -> str:
    lines = []
    col_widths = [max(len(str(cell or "")) for cell in col) for col in zip(*table_data)]
    for row in table_data:
        cells = [str(cell or "").ljust(col_widths[i]) for i, cell in enumerate(row)]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract tables from a PDF")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--pages", help="Page range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--format", choices=["text", "csv"], default="text", help="Output format (default: text)")
    parser.add_argument("--output-dir", help="Write each table to a separate CSV file in this directory")
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

    tables = extract_tables(args.pdf, pages=pages)

    if not tables:
        print("No tables found.")
        return

    if args.output_dir:
        import os
        os.makedirs(args.output_dir, exist_ok=True)
        for t in tables:
            filename = f"page{t['page']}_table{t['table']}.csv"
            filepath = os.path.join(args.output_dir, filename)
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(t["data"])
            print(f"Wrote: {filepath}")
    else:
        for t in tables:
            print(f"\n=== Page {t['page']}, Table {t['table']} ===")
            if args.format == "csv":
                print(format_as_csv(t["data"]))
            else:
                print(format_as_text(t["data"]))


if __name__ == "__main__":
    main()
