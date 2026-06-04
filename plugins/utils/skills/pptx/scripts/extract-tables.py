#!/usr/bin/env python3
"""Extract tables from PPTX slides as text or CSV."""

import argparse
import csv
import io
import os
import sys


def check_deps():
    try:
        import pptx  # noqa: F401
    except ImportError:
        print("Missing package: python-pptx", file=sys.stderr)
        print("Install with: pip install python-pptx", file=sys.stderr)
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


def extract_tables(pptx_path: str, slides: list[int] | None = None) -> list[dict]:
    from pptx import Presentation

    prs = Presentation(pptx_path)
    selected = set(slides) if slides else None

    results = []
    for index, slide in enumerate(prs.slides, start=1):
        if selected is not None and index not in selected:
            continue
        table_idx = 0
        for shape in slide.shapes:
            if not shape.has_table:
                continue
            table_idx += 1
            data = []
            for row in shape.table.rows:
                data.append([cell.text_frame.text.strip().replace("\n", " ") for cell in row.cells])
            if data:
                results.append({"slide": index, "table": table_idx, "data": data})

    return results


def format_as_csv(table_data: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(table_data)
    return buf.getvalue()


def format_as_text(table_data: list) -> str:
    col_widths = [max(len(str(cell or "")) for cell in col) for col in zip(*table_data)]
    lines = []
    for row in table_data:
        cells = [str(cell or "").ljust(col_widths[i]) for i, cell in enumerate(row)]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract tables from a PPTX deck")
    parser.add_argument("pptx", help="Path to the PPTX file")
    parser.add_argument("--slides", help="Slide range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--format", choices=["text", "csv"], default="text", help="Output format (default: text)")
    parser.add_argument("--output-dir", help="Write each table to a separate CSV file in this directory")
    args = parser.parse_args()

    check_deps()

    slides = parse_slides(args.slides) if args.slides else None
    tables = extract_tables(args.pptx, slides=slides)

    if not tables:
        print("No tables found.")
        return

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        for t in tables:
            filename = f"slide{t['slide']}_table{t['table']}.csv"
            filepath = os.path.join(args.output_dir, filename)
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(t["data"])
            print(f"Wrote: {filepath}")
    else:
        for t in tables:
            print(f"\n=== Slide {t['slide']}, Table {t['table']} ===")
            if args.format == "csv":
                print(format_as_csv(t["data"]))
            else:
                print(format_as_text(t["data"]))


if __name__ == "__main__":
    main()
