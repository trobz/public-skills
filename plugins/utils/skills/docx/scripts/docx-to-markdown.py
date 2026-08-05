#!/usr/bin/env python3
"""Convert a DOCX file to clean Markdown."""

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path


def check_deps():
    try:
        from docx import Document  # noqa: F401
        from lxml import etree  # noqa: F401
    except ImportError as e:
        print(f"Missing package: {e.name}", file=sys.stderr)
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

    DOCX files exported from Google Docs re-serialize word/document.xml and
    every image relationship from scratch on each export, so Word-internal
    names like "image1339.png" are arbitrary and shift for the whole document
    even when only one paragraph changed. Hashing the actual image bytes
    keeps the same picture mapped to the same filename across re-exports, so
    re-running the conversion after a small edit only touches what changed.
    """
    ext = Path(original_name).suffix.lower()
    return f"{content_hash(data)}{ext}"


def build_existing_hash_index(existing_dir: "Path | None") -> dict[str, str]:
    """Map content hash → filename for files already in existing_dir (top-level only).

    Used to reuse whatever name an unchanged image already has on disk (even a
    pre-migration Word-assigned name like "image238.png") instead of renaming
    it to a fresh content-hash name — so a resync only touches images that
    actually changed. Not recursive: existing_dir is expected to be the same
    directory new images will be written into, so basenames stay valid against
    a single --image-prefix.
    """
    index: dict[str, str] = {}
    if not existing_dir or not existing_dir.is_dir():
        return index
    for f in existing_dir.iterdir():
        if f.is_file():
            index[content_hash(f.read_bytes())] = f.name
    return index


def _extract_rId_map(
    docx_path: Path, existing_index: dict[str, str] | None = None
) -> dict[str, str]:
    """Parse document.xml.rels → {rId: image filename}.

    Reuses an existing file's name when its content hash matches (see
    build_existing_hash_index); otherwise falls back to a fresh
    content-addressed filename.
    """
    from lxml import etree

    existing_index = existing_index or {}
    rId_map: dict[str, str] = {}
    with zipfile.ZipFile(docx_path) as z:
        try:
            with z.open("word/_rels/document.xml.rels") as f:
                tree = etree.parse(f)
        except KeyError:
            return rId_map
        for rel in tree.getroot():
            rid = rel.get("Id")
            target = rel.get("Target", "")
            if "media/" not in target:
                continue
            media_path = f"word/{target}"
            try:
                data = z.read(media_path)
            except KeyError:
                continue
            h = content_hash(data)
            rId_map[rid] = existing_index.get(h) or content_hash_filename(data, target)
    return rId_map


_LEADING_LIST_MARKER_RE = re.compile(r"^(\d{1,9})([.)])(\s)")


def escape_leading_list_marker(text: str) -> str:
    """Escape a leading '1.' / '1)' so CommonMark doesn't parse it as a nested list.

    Word authors sometimes type manual numbering ("14. Some column:") inside a
    plain paragraph. Emitting that text as-is at the start of a line lets
    CommonMark read it as the start of a *new* ordered list rather than plain
    text, so we escape the punctuation to keep it literal.
    """
    return _LEADING_LIST_MARKER_RE.sub(r"\1\\\2\3", text)


def strip_redundant_list_number(text: str) -> str:
    """Drop a manually-typed '14. ' / '14) ' prefix from a bullet item's text.

    Word authors sometimes type manual numbering inside a paragraph that
    already carries Word list (bullet) formatting. Rendered as markdown, the
    "- " bullet already conveys enumeration, so the leading number is
    redundant — and worse, "- 14. text" makes CommonMark read the bullet's
    sole content as a *new* nested ordered list, producing two stacked
    markers instead of one bullet. Stripping the number sidesteps both.
    """
    return _LEADING_LIST_MARKER_RE.sub("", text)


def runs_to_markdown(para_elem) -> str:
    """Convert paragraph runs to markdown (bold, italic). Preserves soft line breaks."""
    from docx.oxml.ns import qn

    def _is_on(rpr, tag: str) -> bool:
        """True if property is present and not explicitly disabled via w:val='0'."""
        if rpr is None:
            return False
        elem = rpr.find(tag)
        if elem is None:
            return False
        val = elem.get(qn("w:val"), "1")
        return val.lower() not in ("0", "false", "off")

    segments: list[tuple[bool, bool, str]] = []
    for run in para_elem.findall(f".//{qn('w:r')}"):
        rpr = run.find(qn("w:rPr"))
        is_bold = _is_on(rpr, qn("w:b"))
        is_italic = _is_on(rpr, qn("w:i"))
        for child in run:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "t":
                text = child.text or ""
                if not text:
                    continue
                if (
                    segments
                    and segments[-1][0] == is_bold
                    and segments[-1][1] == is_italic
                    and segments[-1][2] != "\n"
                ):
                    segments[-1] = (is_bold, is_italic, segments[-1][2] + text)
                else:
                    segments.append((is_bold, is_italic, text))
            elif tag == "br":
                segments.append((False, False, "\n"))

    # Normalize punctuation-only segments: adopt formatting of adjacent content segment.
    # Word often gives quotes/parens a different bold/italic than the surrounding word,
    # producing malformed markers like ***"****text*. Fix by inheriting neighbor's format.
    _PUNCT = frozenset('"""\'\'\'(),.:;!?–—*_`~')
    if len(segments) > 1:
        normalized = list(segments)
        for _ in range(2):  # two passes to handle edges
            for i, (b, it, txt) in enumerate(normalized):
                if txt == "\n":
                    continue
                if all(c in _PUNCT or c.isspace() for c in txt):
                    left = normalized[i - 1] if i > 0 and normalized[i - 1][2] != "\n" else None
                    right = normalized[i + 1] if i < len(normalized) - 1 and normalized[i + 1][2] != "\n" else None
                    neighbor = right or left
                    if neighbor and (neighbor[0] != b or neighbor[1] != it):
                        normalized[i] = (neighbor[0], neighbor[1], txt)
        # Re-merge adjacent segments with same formatting
        merged: list[tuple[bool, bool, str]] = []
        for seg in normalized:
            if merged and merged[-1][0] == seg[0] and merged[-1][1] == seg[1] and merged[-1][2] != "\n" and seg[2] != "\n":
                merged[-1] = (seg[0], seg[1], merged[-1][2] + seg[2])
            else:
                merged.append(seg)
        segments = merged

    parts = []
    for is_bold, is_italic, text in segments:
        if text == "\n":
            parts.append("\n")
            continue
        stripped = text.strip()
        if not stripped:
            parts.append(text)
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        if is_bold and is_italic:
            parts.append(f"{lead}***{stripped}***{trail}")
        elif is_bold:
            parts.append(f"{lead}**{stripped}**{trail}")
        elif is_italic:
            parts.append(f"{lead}*{stripped}*{trail}")
        else:
            parts.append(text)
    return "".join(parts).strip()


def find_images_in_para(para_elem, rId_map: dict) -> list[str]:
    """Return image filenames referenced in this paragraph."""
    images = []
    for blip in para_elem.iter(
        "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    ):
        rid = blip.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
        )
        if rid and rid in rId_map:
            images.append(rId_map[rid])
    return images


def _cell_to_md(cell) -> str:
    """Convert a table cell to markdown, preserving bold/italic formatting."""
    parts = [runs_to_markdown(p._element) for p in cell.paragraphs]
    return " ".join(p for p in parts if p)


def table_to_markdown(table) -> str:
    """Convert a docx table to a markdown pipe table."""
    rows = table.rows
    if not rows:
        return ""
    lines = []
    for i, row in enumerate(rows):
        cells = [_cell_to_md(cell).replace("\n", " ") for cell in row.cells]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)


def heading_level(style_name: str) -> int:
    """Return heading level (1–4) or 0 for non-headings."""
    m = re.match(r"[Hh]eading\s*(\d)", style_name)
    return int(m.group(1)) if m else 0


def _slugify(text: str) -> str:
    """Convert heading text to a URL-friendly anchor slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def convert(
    docx_path: Path,
    image_prefix: str = "images/",
    toc: bool = False,
    existing_images_dir: Path | None = None,
) -> str:
    """Convert a DOCX file to a single Markdown string."""
    from docx import Document

    existing_index = build_existing_hash_index(existing_images_dir)
    rId_map = _extract_rId_map(docx_path, existing_index)
    doc = Document(docx_path)
    body = doc.element.body

    table_map = {id(tbl._tbl): tbl for tbl in doc.tables}
    para_map = {id(para._element): para for para in doc.paragraphs}

    items: list[dict] = []

    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            para = para_map.get(id(child))
            if para is None:
                continue
            style = para.style.name if para.style else "normal"
            level = heading_level(style)
            images_in_para = find_images_in_para(child, rId_map)

            if level:
                text = para.text.strip()
                if text:
                    items.append({"kind": f"h{level}", "text": text, "level": level})
            else:
                md_text = runs_to_markdown(child)
                for img in images_in_para:
                    items.append({"kind": "image", "filename": img})
                if md_text:
                    has_numpr = (
                        child.find(
                            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr"
                        )
                        is not None
                    )
                    indent_emu = para.paragraph_format.left_indent or 0
                    list_level = 0
                    if has_numpr and indent_emu:
                        list_level = max(1, round(indent_emu / 457200))
                    lines = [s.strip() for s in md_text.split("\n") if s.strip()]
                    for i, sub in enumerate(lines):
                        items.append(
                            {
                                "kind": "text",
                                "text": sub,
                                "list_level": list_level,
                                "new_para": i == 0,
                            }
                        )

        elif tag == "tbl":
            tbl = table_map.get(id(child))
            if tbl:
                items.append({"kind": "table", "table": tbl})

    return items_to_markdown(items, image_prefix=image_prefix, toc=toc)


def items_to_markdown(
    items: list[dict],
    image_prefix: str = "images/",
    toc: bool = False,
) -> str:
    """Assemble the intermediate item list (headings/text/images/tables) into markdown."""
    output: list[str] = []

    if toc:
        headings = [it for it in items if it["kind"].startswith("h")]
        if headings:
            output.append("## Table of Contents\n")
            for h in headings:
                indent = "  " * (h["level"] - 1)
                slug = _slugify(h["text"])
                output.append(f"{indent}- [{h['text']}](#{slug})")
            output.append("")

    prev_was_plain_para = False
    for item in items:
        if item["kind"].startswith("h"):
            prefix = "#" * item["level"]
            output.append(f"\n{prefix} {item['text']}\n")
            prev_was_plain_para = False
        elif item["kind"] == "text":
            lvl = item.get("list_level", 0)
            if lvl > 0:
                text = strip_redundant_list_number(item["text"])
                output.append("  " * (lvl - 1) + f"- {text}")
                prev_was_plain_para = False
            else:
                text = escape_leading_list_marker(item["text"])
                if item.get("new_para", True):
                    # A new Word paragraph: separate it from the previous one
                    # with a blank line, otherwise CommonMark treats the single
                    # "\n" between them as a soft break (rendered as a mere
                    # space) instead of starting a new paragraph.
                    if prev_was_plain_para:
                        output.append("")
                elif output:
                    # Continuation of the same Word paragraph via a soft line
                    # break (<w:br/>): force a real line break instead of
                    # letting CommonMark collapse the "\n" into a space.
                    output[-1] = output[-1] + " \\"
                output.append(text)
                prev_was_plain_para = True
        elif item["kind"] == "image":
            alt = Path(item["filename"]).stem
            output.append(f"\n![{alt}]({image_prefix}{item['filename']})\n")
            prev_was_plain_para = False
        elif item["kind"] == "table":
            md = table_to_markdown(item["table"])
            if md:
                output.append(f"\n{md}\n")
            prev_was_plain_para = False

    result = "\n".join(output)
    result = re.sub(r"\n{4,}", "\n\n\n", result)
    # Reduce blank lines between consecutive images to a single newline
    result = re.sub(
        r"(!\[[^\]]*\]\([^)]*\))\n\n+(!\[[^\]]*\]\([^)]*\))",
        r"\1\n\2",
        result,
    )
    return result.strip()


def main():
    parser = argparse.ArgumentParser(description="Convert DOCX to Markdown")
    parser.add_argument("docx", help="Path to the DOCX file")
    parser.add_argument(
        "--image-prefix",
        default="images/",
        metavar="PREFIX",
        help="Prefix for image references (default: images/)",
    )
    parser.add_argument(
        "--toc",
        action="store_true",
        help="Prepend a Markdown table of contents",
    )
    parser.add_argument(
        "--output",
        help="Write output to this file instead of stdout",
    )
    parser.add_argument(
        "--existing-images-dir",
        metavar="DIR",
        help=(
            "Directory to check for already-present images (matched by content "
            "hash) before naming a new one. Reuses that file's existing name in "
            "the generated refs instead of renaming it — pass the same directory "
            "you'll pass to extract-images.py's --output-dir so refs stay valid."
        ),
    )
    args = parser.parse_args()

    check_deps()

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"Error: file not found: {docx_path}", file=sys.stderr)
        sys.exit(1)

    existing_images_dir = Path(args.existing_images_dir) if args.existing_images_dir else None
    md = convert(
        docx_path,
        image_prefix=args.image_prefix,
        toc=args.toc,
        existing_images_dir=existing_images_dir,
    )

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"Markdown written to: {args.output}")
    else:
        print(md)


if __name__ == "__main__":
    main()
