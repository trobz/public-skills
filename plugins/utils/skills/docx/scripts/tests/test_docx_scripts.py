#!/usr/bin/env python3
"""Tests for DOCX skill scripts."""

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def load_script(script_name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / script_name)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


docx_to_md = load_script("docx-to-markdown.py", "docx_to_markdown")
extract_images_script = load_script("extract-images.py", "extract_images_script")


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def make_run(text=None, bold=False, italic=False, line_break=False):
    r = etree.Element(f"{{{W}}}r")
    if bold or italic:
        rpr = etree.SubElement(r, f"{{{W}}}rPr")
        if bold:
            etree.SubElement(rpr, f"{{{W}}}b")
        if italic:
            etree.SubElement(rpr, f"{{{W}}}i")
    if text is not None:
        t = etree.SubElement(r, f"{{{W}}}t")
        t.text = text
    if line_break:
        etree.SubElement(r, f"{{{W}}}br")
    return r


def make_para(*runs):
    para = etree.Element(f"{{{W}}}p")
    for run in runs:
        para.append(run)
    return para


def make_para_with_blip(rid: str):
    para = etree.Element(f"{{{W}}}p")
    blip = etree.SubElement(para, f"{{{A}}}blip")
    blip.set(f"{{{R}}}embed", rid)
    return para


class FakeParagraph:
    def __init__(self, *runs):
        self._element = make_para(*runs)


class FakeCell:
    def __init__(self, *paragraphs):
        self.paragraphs = list(paragraphs)


class FakeRow:
    def __init__(self, *cells):
        self.cells = list(cells)


class FakeTable:
    def __init__(self, *rows):
        self.rows = list(rows)


def make_fake_docx(
    media_files: dict[str, bytes] | None = None,
    rels: dict[str, str] | None = None,
) -> bytes:
    """Build an in-memory DOCX-like ZIP. media_files: {filename: content}, rels: {rId: filename}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in (media_files or {}).items():
            z.writestr(f"word/media/{name}", content)
        if rels:
            lines = ['<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
            for rid, filename in rels.items():
                lines.append(
                    f'<Relationship Id="{rid}" Type="image" Target="media/{filename}"/>'
                )
            lines.append("</Relationships>")
            z.writestr("word/_rels/document.xml.rels", "\n".join(lines))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# runs_to_markdown
# ---------------------------------------------------------------------------

class TestRunsToMarkdown:
    def test_plain_text(self):
        para = make_para(make_run("hello"))
        assert docx_to_md.runs_to_markdown(para) == "hello"

    def test_bold(self):
        para = make_para(make_run("hello", bold=True))
        assert docx_to_md.runs_to_markdown(para) == "**hello**"

    def test_italic(self):
        para = make_para(make_run("hello", italic=True))
        assert docx_to_md.runs_to_markdown(para) == "*hello*"

    def test_bold_and_italic(self):
        para = make_para(make_run("hello", bold=True, italic=True))
        assert docx_to_md.runs_to_markdown(para) == "***hello***"

    def test_mixed_runs(self):
        para = make_para(
            make_run("normal "),
            make_run("bold", bold=True),
            make_run(" normal"),
        )
        result = docx_to_md.runs_to_markdown(para)
        assert "**bold**" in result
        assert result.startswith("normal")
        assert result.endswith("normal")

    def test_soft_line_break_preserved(self):
        para = make_para(
            make_run("line one", line_break=True),
            make_run("line two"),
        )
        result = docx_to_md.runs_to_markdown(para)
        assert "\n" in result

    def test_empty_para(self):
        para = make_para()
        assert docx_to_md.runs_to_markdown(para) == ""

    def test_consecutive_runs_same_style_are_merged(self):
        para = make_para(make_run("hel", bold=True), make_run("lo", bold=True))
        assert docx_to_md.runs_to_markdown(para) == "**hello**"


# ---------------------------------------------------------------------------
# escape_leading_list_marker
# ---------------------------------------------------------------------------

class TestEscapeLeadingListMarker:
    def test_escapes_digit_dot_prefix(self):
        result = docx_to_md.escape_leading_list_marker("14. In Jeunes Travailleurs column:")
        assert result == "14\\. In Jeunes Travailleurs column:"

    def test_escapes_digit_paren_prefix(self):
        result = docx_to_md.escape_leading_list_marker("1) First step")
        assert result == "1\\) First step"

    def test_leaves_plain_text_untouched(self):
        text = "In Jeunes Travailleurs column:"
        assert docx_to_md.escape_leading_list_marker(text) == text

    def test_leaves_digit_without_trailing_space_untouched(self):
        text = "14.5kg of flour"
        assert docx_to_md.escape_leading_list_marker(text) == text

    def test_does_not_touch_number_mid_sentence(self):
        text = "See step 14. for details"
        assert docx_to_md.escape_leading_list_marker(text) == text

    def test_produces_top_level_line_that_no_longer_starts_an_ordered_list(self):
        # Regression test: a bare "14. text" line at the top of the document
        # would otherwise be read by CommonMark as the start of a new
        # ordered list instead of a plain paragraph.
        escaped = docx_to_md.escape_leading_list_marker("14. In Jeunes Travailleurs column:")
        assert escaped == "14\\. In Jeunes Travailleurs column:"


# ---------------------------------------------------------------------------
# strip_redundant_list_number
# ---------------------------------------------------------------------------

class TestStripRedundantListNumber:
    def test_strips_digit_dot_prefix(self):
        result = docx_to_md.strip_redundant_list_number("14. In Jeunes Travailleurs column:")
        assert result == "In Jeunes Travailleurs column:"

    def test_strips_digit_paren_prefix(self):
        result = docx_to_md.strip_redundant_list_number("1) First step")
        assert result == "First step"

    def test_leaves_plain_text_untouched(self):
        text = "In Jeunes Travailleurs column:"
        assert docx_to_md.strip_redundant_list_number(text) == text

    def test_leaves_digit_without_trailing_space_untouched(self):
        text = "14.5kg of flour"
        assert docx_to_md.strip_redundant_list_number(text) == text

    def test_does_not_touch_number_mid_sentence(self):
        text = "See step 14. for details"
        assert docx_to_md.strip_redundant_list_number(text) == text

    def test_produces_single_bullet_with_no_redundant_number(self):
        # Regression test: rendering "- 14. text" through a CommonMark parser
        # used to produce <li><ol start="14"><li>text</li></ol></li> (two
        # stacked bullets). Stripping the number yields one clean bullet.
        stripped = docx_to_md.strip_redundant_list_number("14. In Jeunes Travailleurs column:")
        bullet_line = f"- {stripped}"
        assert bullet_line == "- In Jeunes Travailleurs column:"


# ---------------------------------------------------------------------------
# find_images_in_para
# ---------------------------------------------------------------------------

class TestFindImagesInPara:
    def test_finds_image_by_rId(self):
        rId_map = {"rId1": "image1.png"}
        para = make_para_with_blip("rId1")
        assert docx_to_md.find_images_in_para(para, rId_map) == ["image1.png"]

    def test_unknown_rId_is_skipped(self):
        rId_map = {"rId1": "image1.png"}
        para = make_para_with_blip("rId99")
        assert docx_to_md.find_images_in_para(para, rId_map) == []

    def test_para_without_images(self):
        para = make_para(make_run("no image here"))
        assert docx_to_md.find_images_in_para(para, {"rId1": "image1.png"}) == []


# ---------------------------------------------------------------------------
# table_to_markdown
# ---------------------------------------------------------------------------

class TestTableToMarkdown:
    def test_simple_two_column_table(self):
        table = FakeTable(
            FakeRow(
                FakeCell(FakeParagraph(make_run("Name"))),
                FakeCell(FakeParagraph(make_run("Value"))),
            ),
            FakeRow(
                FakeCell(FakeParagraph(make_run("foo"))),
                FakeCell(FakeParagraph(make_run("bar"))),
            ),
        )
        result = docx_to_md.table_to_markdown(table)
        assert "| Name | Value |" in result
        assert "| --- | --- |" in result
        assert "| foo | bar |" in result

    def test_bold_in_cell_is_preserved(self):
        table = FakeTable(
            FakeRow(
                FakeCell(FakeParagraph(make_run("Status"))),
            ),
            FakeRow(
                FakeCell(FakeParagraph(make_run("OK", bold=True))),
            ),
        )
        result = docx_to_md.table_to_markdown(table)
        assert "**OK**" in result

    def test_empty_table_returns_empty_string(self):
        table = FakeTable()
        assert docx_to_md.table_to_markdown(table) == ""


# ---------------------------------------------------------------------------
# heading_level
# ---------------------------------------------------------------------------

class TestHeadingLevel:
    def test_heading1(self):
        assert docx_to_md.heading_level("Heading 1") == 1

    def test_heading3(self):
        assert docx_to_md.heading_level("Heading 3") == 3

    def test_normal_returns_zero(self):
        assert docx_to_md.heading_level("Normal") == 0

    def test_body_text_returns_zero(self):
        assert docx_to_md.heading_level("Body Text") == 0

    def test_case_insensitive(self):
        assert docx_to_md.heading_level("heading 2") == 2


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert docx_to_md._slugify("I. Members") == "i-members"

    def test_spaces_become_dashes(self):
        assert docx_to_md._slugify("Hello World") == "hello-world"

    def test_special_chars_removed(self):
        assert docx_to_md._slugify("I.1. Definitions") == "i1-definitions"

    def test_multiple_spaces_collapsed(self):
        assert docx_to_md._slugify("A  B") == "a-b"


# ---------------------------------------------------------------------------
# extract_images
# ---------------------------------------------------------------------------

class TestExtractImages:
    def test_extracts_media_files_to_output_dir(self, tmp_path):
        docx_bytes = make_fake_docx(
            media_files={"image1.png": b"PNG_DATA", "image2.png": b"PNG_DATA2"},
            rels={"rId1": "image1.png", "rId2": "image2.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)
        output_dir = tmp_path / "imgs"

        rId_map, count = extract_images_script.extract_images(docx_path, output_dir)

        assert count == 2
        assert (output_dir / "image1.png").read_bytes() == b"PNG_DATA"
        assert (output_dir / "image2.png").read_bytes() == b"PNG_DATA2"

    def test_returns_correct_rId_map(self, tmp_path):
        docx_bytes = make_fake_docx(
            media_files={"image1.png": b"x"},
            rels={"rId1": "image1.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        rId_map, _ = extract_images_script.extract_images(docx_path, tmp_path / "imgs")

        assert rId_map == {"rId1": "image1.png"}

    def test_no_rels_file_returns_empty_map(self, tmp_path):
        docx_bytes = make_fake_docx(media_files={"image1.png": b"x"})
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        rId_map, count = extract_images_script.extract_images(docx_path, tmp_path / "imgs")

        assert rId_map == {}
        assert count == 1

    def test_creates_output_dir_if_missing(self, tmp_path):
        docx_bytes = make_fake_docx()
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)
        output_dir = tmp_path / "new" / "nested" / "dir"

        extract_images_script.extract_images(docx_path, output_dir)

        assert output_dir.exists()
