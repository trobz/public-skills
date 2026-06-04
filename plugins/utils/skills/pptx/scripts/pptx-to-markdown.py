#!/usr/bin/env python3
"""Convert PPTX decks to Markdown with speaker notes and inline image references."""

import argparse
import io
import os
import sys


def check_deps(ocr: bool = False):
    missing = []
    try:
        import pptx  # noqa: F401
    except ImportError:
        missing.append("python-pptx")
    if ocr:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            missing.append("pytesseract")
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            missing.append("Pillow")
    if missing:
        print(f"Missing packages: {', '.join(missing)}", file=sys.stderr)
        print(f"Install with: pip install {' '.join(missing)}", file=sys.stderr)
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


def _slide_title(slide) -> str:
    title_shape = slide.shapes.title
    if title_shape is not None and title_shape.has_text_frame:
        # Collapse internal newlines so a multi-paragraph title stays on one heading line
        text = " ".join(title_shape.text_frame.text.split())
        if text:
            return text
    return ""


def _is_decorative_placeholder(shape) -> bool:
    """True for slide-number, date, and footer placeholders (chrome, not content)."""
    from pptx.enum.shapes import PP_PLACEHOLDER

    if not shape.is_placeholder:
        return False
    return shape.placeholder_format.type in (
        PP_PLACEHOLDER.SLIDE_NUMBER,
        PP_PLACEHOLDER.DATE,
        PP_PLACEHOLDER.FOOTER,
    )


def _image_alt(shape) -> str:
    """Read the picture's alt-text (the descr attribute set by the author).

    Deliberately does NOT fall back to shape.name: exporters like Google Slides
    auto-generate names such as "Google Shape;39;p8" that are noise, not alt text.
    """
    try:
        cNvPr = shape._element.nvPicPr.cNvPr
        alt = (cNvPr.get("descr") or "").strip()
        if alt:
            return " ".join(alt.split())
    except Exception:
        pass
    return ""


def _ocr_blob(blob: bytes, lang: str) -> str:
    import pytesseract
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(blob))
        return " ".join(pytesseract.image_to_string(img, lang=lang).split())
    except Exception as exc:  # noqa: BLE001 - surface OCR failure inline, don't crash
        return f"[OCR failed: {exc}]"


def _format_chart(shape) -> str:
    chart = shape.chart
    try:
        lines = []
        if chart.has_title:
            lines.append(f"**Chart: {chart.chart_title.text_frame.text}**")
        category_names = [c.label for c in chart.plots[0].categories]
        series_names = [s.name for s in chart.series]
        header = ["Category"] + series_names
        rows = []
        for idx, category in enumerate(category_names):
            row = [str(category)]
            for series in chart.series:
                val = series.values[idx]
                row.append("" if val is None else str(val))
            rows.append(row)
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)
    except ValueError as exc:
        if "unsupported plot type" in str(exc):
            return "[unsupported chart]"
        return f"[chart error: {exc}]"
    except Exception as exc:
        return f"[chart error: {exc}]"


def _format_table(shape) -> str:
    table = shape.table
    rows = []
    for row in table.rows:
        rows.append([cell.text_frame.text.strip().replace("\n", " ") for cell in row.cells])
    if not rows:
        return ""

    header, *body = rows
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _image_segment(
    shape,
    slide_index: int,
    img_index: int,
    images_dir: str | None,
    extract: bool,
    ocr: bool,
    lang: str,
) -> list[str]:
    """Emit the inline marker for one picture, extracting the file when enabled.

    Images are never silently dropped: when extraction is off, a `[not extracted]`
    marker is still emitted so the agent knows content is missing.
    """
    stub = f"slide{slide_index}_img{img_index}"
    if not extract or images_dir is None:
        return [f"> [IMAGE: not extracted — {stub}]"]

    image = shape.image
    ext = image.ext or "png"
    filename = f"{stub}.{ext}"
    os.makedirs(images_dir, exist_ok=True)
    filepath = os.path.join(images_dir, filename)
    with open(filepath, "wb") as f:
        f.write(image.blob)

    alt = _image_alt(shape) or "no alt text"
    lines = [f"> [IMAGE: {filepath} — {alt}]"]
    if ocr:
        text = _ocr_blob(image.blob, lang)
        if text:
            lines.append(f"> OCR: {text}")
    return lines


def _render_body(
    slide,
    slide_index: int,
    title: str,
    images_dir: str | None,
    extract_images: bool,
    ocr: bool,
    lang: str,
) -> list[list[str]]:
    """Walk shapes in order, returning a list of content segments (each a block of
    lines). Bullets, tables, and image markers appear in their slide position."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    title_shape = slide.shapes.title
    title_id = id(title_shape) if title_shape is not None else None
    skip_key = "".join(title.split()).lower() if title else ""

    segments: list[list[str]] = []
    bullets: list[str] = []
    img_index = 0

    def flush_bullets():
        nonlocal bullets
        if bullets:
            segments.append(bullets)
            bullets = []

    for shape in slide.shapes:
        if id(shape) == title_id:
            continue
        if _is_decorative_placeholder(shape):
            continue

        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            img_index += 1
            flush_bullets()
            segments.append(
                _image_segment(
                    shape, slide_index, img_index, images_dir, extract_images, ocr, lang
                )
            )
            continue

        if shape.has_chart:
            flush_bullets()
            chart_md = _format_chart(shape)
            if chart_md:
                segments.append(chart_md.split("\n"))
            continue

        if shape.has_table:
            flush_bullets()
            table_md = _format_table(shape)
            if table_md:
                segments.append(table_md.split("\n"))
            continue

        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                # paragraph.text preserves intra-paragraph spacing across runs
                text = paragraph.text.strip()
                if not text:
                    continue
                if skip_key and "".join(text.split()).lower() == skip_key:
                    continue
                indent = "  " * (paragraph.level or 0)
                bullets.append(f"{indent}- {text}")

    flush_bullets()
    return segments


def _notes_text(slide) -> str:
    if not slide.has_notes_slide:
        return ""
    notes_frame = slide.notes_slide.notes_text_frame
    if notes_frame is None:
        return ""
    return notes_frame.text.strip()


def pptx_to_markdown(
    pptx_path: str,
    slides: list[int] | None = None,
    include_notes: bool = True,
    images_dir: str | None = None,
    extract_images: bool = True,
    ocr: bool = False,
    lang: str = "eng",
) -> str:
    from pptx import Presentation

    prs = Presentation(pptx_path)
    selected = set(slides) if slides else None

    parts: list[str] = []
    for index, slide in enumerate(prs.slides, start=1):
        if selected is not None and index not in selected:
            continue

        title = _slide_title(slide)
        heading = f"# {title}" if title else f"# Slide {index}"
        block = [f"<!-- Slide number: {index} -->", heading]

        for segment in _render_body(
            slide, index, title, images_dir, extract_images, ocr, lang
        ):
            block.append("")
            block.extend(segment)

        if include_notes:
            # Always emit the notes section so the structure is consistent per slide
            if block and block[-1] != "":
                block.append("")
            block.append("### Notes:")
            notes = _notes_text(slide)
            if notes:
                block.append("")
                block.append(notes)

        parts.append("\n".join(block).rstrip())

    return "\n\n".join(parts) + "\n"


def _default_images_dir(pptx_path: str, output: str | None) -> str:
    stem = os.path.splitext(os.path.basename(pptx_path))[0]
    parent = os.path.dirname(output) if output else "."
    return os.path.join(parent, f"{stem}_imgs")


def main():
    parser = argparse.ArgumentParser(description="Convert PPTX to Markdown")
    parser.add_argument("pptx", help="Path to the PPTX file")
    parser.add_argument("--slides", help="Slide range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--no-notes", action="store_true", help="Skip speaker notes")
    parser.add_argument(
        "--images-dir",
        help="Extract embedded images here (default: <deck>_imgs/ next to output)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image extraction (emits [not extracted] markers)",
    )
    parser.add_argument(
        "--ocr", action="store_true", help="OCR each extracted image, embed text inline"
    )
    parser.add_argument("--lang", default="eng", help="Tesseract language code for --ocr")
    parser.add_argument("--output", help="Write output to this file instead of stdout")
    args = parser.parse_args()

    check_deps(ocr=args.ocr)

    extract_images = not args.no_images
    images_dir = None
    if extract_images:
        images_dir = args.images_dir or _default_images_dir(args.pptx, args.output)

    slides = parse_slides(args.slides) if args.slides else None
    md = pptx_to_markdown(
        args.pptx,
        slides=slides,
        include_notes=not args.no_notes,
        images_dir=images_dir,
        extract_images=extract_images,
        ocr=args.ocr,
        lang=args.lang,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Markdown written to: {args.output}")
        if extract_images and images_dir and os.path.isdir(images_dir):
            print(f"Images extracted to: {images_dir}")
    else:
        print(md)


if __name__ == "__main__":
    main()
