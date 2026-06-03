#!/usr/bin/env python3
"""Print a slide-by-slide structure scan (title, content, images, notes) for a PPTX."""

import argparse
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


def _slide_title(slide) -> str:
    title_shape = slide.shapes.title
    if title_shape is not None and title_shape.has_text_frame:
        text = " ".join(title_shape.text_frame.text.split())
        if text:
            return text
    return ""


def _is_decorative_placeholder(shape) -> bool:
    from pptx.enum.shapes import PP_PLACEHOLDER

    if not shape.is_placeholder:
        return False
    return shape.placeholder_format.type in (
        PP_PLACEHOLDER.SLIDE_NUMBER,
        PP_PLACEHOLDER.DATE,
        PP_PLACEHOLDER.FOOTER,
    )


def _scan_slide(slide, title: str) -> tuple[bool, int]:
    """Return (has_body_content, image_count) for a slide."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    title_shape = slide.shapes.title
    title_id = id(title_shape) if title_shape is not None else None
    skip_key = "".join(title.split()).lower() if title else ""

    has_content = False
    image_count = 0
    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            image_count += 1
            continue
        if id(shape) == title_id or _is_decorative_placeholder(shape):
            continue
        if shape.has_table:
            has_content = True
            continue
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                text = paragraph.text.strip()
                if not text:
                    continue
                if skip_key and "".join(text.split()).lower() == skip_key:
                    continue
                has_content = True
                break
    return has_content, image_count


def outline(pptx_path: str, slides: list[int] | None = None) -> str:
    from pptx import Presentation

    prs = Presentation(pptx_path)
    selected = set(slides) if slides else None

    rows = []
    for index, slide in enumerate(prs.slides, start=1):
        if selected is not None and index not in selected:
            continue
        title = _slide_title(slide) or f"Slide {index}"
        has_content, n_img = _scan_slide(slide, _slide_title(slide))
        content = "content" if has_content else "no content"
        images = f"{n_img} image" if n_img == 1 else f"{n_img} images"
        notes = "notes" if _has_notes(slide) else "no notes"
        rows.append((index, title, content, images, notes))

    if not rows:
        return ""

    num_w = max(len(f"{r[0]}.") for r in rows)
    title_w = max(len(r[1]) for r in rows)
    content_w = max(len(f"[{r[2]}]") for r in rows)
    img_w = max(len(f"[{r[3]}]") for r in rows)

    lines = []
    for index, title, content, images, notes in rows:
        num = f"{index}.".ljust(num_w)
        lines.append(
            f"{num} {title.ljust(title_w)} "
            f"{('[' + content + ']').ljust(content_w)} "
            f"{('[' + images + ']').ljust(img_w)} "
            f"[{notes}]"
        )
    return "\n".join(lines) + "\n"


def _has_notes(slide) -> bool:
    if not slide.has_notes_slide:
        return False
    notes_frame = slide.notes_slide.notes_text_frame
    return bool(notes_frame and notes_frame.text.strip())


def main():
    parser = argparse.ArgumentParser(description="Print a structure scan of a PPTX")
    parser.add_argument("pptx", help="Path to the PPTX file")
    parser.add_argument("--slides", help="Slide range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--output", help="Write output to this file instead of stdout")
    args = parser.parse_args()

    check_deps()

    slides = parse_slides(args.slides) if args.slides else None
    text = outline(args.pptx, slides=slides)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Outline written to: {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
