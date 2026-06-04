#!/usr/bin/env python3
"""Extract embedded images from a PPTX deck, optionally OCR-ing each one."""

import argparse
import os
import sys


def check_deps(ocr: bool):
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


def _iter_picture_shapes(slide):
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            yield shape


def extract_images(
    pptx_path: str,
    output_dir: str,
    slides: list[int] | None = None,
    ocr: bool = False,
    lang: str = "eng",
) -> list[str]:
    from pptx import Presentation

    os.makedirs(output_dir, exist_ok=True)
    prs = Presentation(pptx_path)
    selected = set(slides) if slides else None

    written: list[str] = []
    for index, slide in enumerate(prs.slides, start=1):
        if selected is not None and index not in selected:
            continue
        pic_idx = 0
        for shape in _iter_picture_shapes(slide):
            pic_idx += 1
            image = shape.image
            ext = image.ext or "bin"
            filename = f"slide{index}_image{pic_idx}.{ext}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image.blob)
            written.append(filepath)

            if ocr:
                import pytesseract
                from PIL import Image
                import io

                try:
                    pil_img = Image.open(io.BytesIO(image.blob))
                    text = pytesseract.image_to_string(pil_img, lang=lang).strip()
                except Exception as exc:
                    text = f"[OCR failed: {exc}]"
                sidecar = filepath.rsplit(".", 1)[0] + ".txt"
                with open(sidecar, "w", encoding="utf-8") as f:
                    f.write(text)
                written.append(sidecar)

    return written


def main():
    parser = argparse.ArgumentParser(description="Extract embedded images from a PPTX")
    parser.add_argument("pptx", help="Path to the PPTX file")
    parser.add_argument("--output-dir", required=True, help="Directory to write extracted images")
    parser.add_argument("--slides", help="Slide range, e.g. 1-3 or 2,4,6")
    parser.add_argument("--ocr", action="store_true", help="Run tesseract OCR on each image, emit sidecar .txt")
    parser.add_argument("--lang", default="eng", help="Tesseract language code (default: eng)")
    args = parser.parse_args()

    check_deps(ocr=args.ocr)

    slides = parse_slides(args.slides) if args.slides else None
    written = extract_images(
        args.pptx,
        args.output_dir,
        slides=slides,
        ocr=args.ocr,
        lang=args.lang,
    )

    if not written:
        print("No images found.")
        return

    for path in written:
        print(f"Wrote: {path}")


if __name__ == "__main__":
    main()
