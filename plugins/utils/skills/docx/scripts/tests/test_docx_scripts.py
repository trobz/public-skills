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

        rId_map, count, reused = extract_images_script.extract_images(docx_path, output_dir)

        assert count == 2
        assert reused == 0
        name1 = extract_images_script.content_hash_filename(b"PNG_DATA", "image1.png")
        name2 = extract_images_script.content_hash_filename(b"PNG_DATA2", "image2.png")
        assert (output_dir / name1).read_bytes() == b"PNG_DATA"
        assert (output_dir / name2).read_bytes() == b"PNG_DATA2"

    def test_returns_correct_rId_map(self, tmp_path):
        docx_bytes = make_fake_docx(
            media_files={"image1.png": b"x"},
            rels={"rId1": "image1.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        rId_map, _, _ = extract_images_script.extract_images(docx_path, tmp_path / "imgs")

        expected_name = extract_images_script.content_hash_filename(b"x", "image1.png")
        assert rId_map == {"rId1": expected_name}

    def test_no_rels_file_returns_empty_map(self, tmp_path):
        docx_bytes = make_fake_docx(media_files={"image1.png": b"x"})
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        rId_map, count, reused = extract_images_script.extract_images(docx_path, tmp_path / "imgs")

        assert rId_map == {}
        assert count == 1
        assert reused == 0

    def test_creates_output_dir_if_missing(self, tmp_path):
        docx_bytes = make_fake_docx()
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)
        output_dir = tmp_path / "new" / "nested" / "dir"

        extract_images_script.extract_images(docx_path, output_dir)

        assert output_dir.exists()


# ---------------------------------------------------------------------------
# content_hash_filename
# ---------------------------------------------------------------------------

class TestContentHashFilename:
    def test_same_bytes_same_extension_produce_same_filename(self):
        a = docx_to_md.content_hash_filename(b"picture-bytes", "image1.png")
        b = docx_to_md.content_hash_filename(b"picture-bytes", "image47.png")
        assert a == b

    def test_different_bytes_produce_different_filenames(self):
        a = docx_to_md.content_hash_filename(b"picture-one", "image1.png")
        b = docx_to_md.content_hash_filename(b"picture-two", "image1.png")
        assert a != b

    def test_preserves_and_lowercases_extension(self):
        result = docx_to_md.content_hash_filename(b"data", "media/image1.JPG")
        assert result.endswith(".jpg")

    def test_stable_regardless_of_word_assigned_name(self):
        # The whole point: the same picture re-exported under a different
        # Word/Google-assigned rId name still maps to the same filename.
        first_export = docx_to_md.content_hash_filename(b"same-picture", "image42.png")
        second_export = docx_to_md.content_hash_filename(b"same-picture", "image1908.png")
        assert first_export == second_export

    def test_matches_extract_images_script_implementation(self):
        # docx-to-markdown.py generates the ![alt](path) refs and
        # extract-images.py generates the actual files — they must agree on
        # a filename for the same bytes or the refs point nowhere.
        data = b"some image bytes"
        name = "image1339.png"
        assert docx_to_md.content_hash_filename(data, name) == (
            extract_images_script.content_hash_filename(data, name)
        )


# ---------------------------------------------------------------------------
# _extract_rId_map
# ---------------------------------------------------------------------------

class TestExtractRIdMap:
    def test_maps_rid_to_content_hash_filename(self, tmp_path):
        docx_bytes = make_fake_docx(
            media_files={"image1.png": b"PNG_DATA"},
            rels={"rId1": "image1.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        rId_map = docx_to_md._extract_rId_map(docx_path)

        expected_name = docx_to_md.content_hash_filename(b"PNG_DATA", "image1.png")
        assert rId_map == {"rId1": expected_name}

    def test_agrees_with_extract_images_for_the_same_docx(self, tmp_path):
        # docx-to-markdown.py's refs and extract-images.py's output files
        # must reference the exact same filename for a given rId.
        docx_bytes = make_fake_docx(
            media_files={"image1.png": b"PNG_DATA", "image2.png": b"OTHER"},
            rels={"rId1": "image1.png", "rId2": "image2.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        from_convert_script = docx_to_md._extract_rId_map(docx_path)
        from_extract_script, _, _ = extract_images_script.extract_images(docx_path, tmp_path / "imgs")

        assert from_convert_script == from_extract_script


# ---------------------------------------------------------------------------
# build_existing_hash_index / reuse-existing-images
# ---------------------------------------------------------------------------

class TestReuseExistingImages:
    def test_build_existing_hash_index_maps_hash_to_filename(self, tmp_path):
        (tmp_path / "image238.png").write_bytes(b"PNG_DATA")
        (tmp_path / "image404.png").write_bytes(b"OTHER_DATA")

        index = docx_to_md.build_existing_hash_index(tmp_path)

        assert index[docx_to_md.content_hash(b"PNG_DATA")] == "image238.png"
        assert index[docx_to_md.content_hash(b"OTHER_DATA")] == "image404.png"

    def test_missing_dir_returns_empty_index(self, tmp_path):
        assert docx_to_md.build_existing_hash_index(tmp_path / "nope") == {}

    def test_none_dir_returns_empty_index(self):
        assert docx_to_md.build_existing_hash_index(None) == {}

    def test_extract_rId_map_reuses_pre_migration_name_for_unchanged_image(self, tmp_path):
        # The core scenario: an image untouched since before the switch to
        # content-hash naming still carries an old Word-assigned name like
        # "image238.png" on disk. A resync must keep that name, not rename it.
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        (existing_dir / "image238.png").write_bytes(b"UNCHANGED_PICTURE")

        docx_bytes = make_fake_docx(
            media_files={"image1339.png": b"UNCHANGED_PICTURE"},
            rels={"rId1": "image1339.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        existing_index = docx_to_md.build_existing_hash_index(existing_dir)
        rId_map = docx_to_md._extract_rId_map(docx_path, existing_index)

        assert rId_map == {"rId1": "image238.png"}

    def test_extract_rId_map_falls_back_to_hash_name_for_new_image(self, tmp_path):
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        (existing_dir / "image238.png").write_bytes(b"SOME_OTHER_PICTURE")

        docx_bytes = make_fake_docx(
            media_files={"image1339.png": b"BRAND_NEW_PICTURE"},
            rels={"rId1": "image1339.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        existing_index = docx_to_md.build_existing_hash_index(existing_dir)
        rId_map = docx_to_md._extract_rId_map(docx_path, existing_index)

        expected = docx_to_md.content_hash_filename(b"BRAND_NEW_PICTURE", "image1339.png")
        assert rId_map == {"rId1": expected}

    def test_extract_images_skips_writing_reused_file(self, tmp_path):
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        (existing_dir / "image238.png").write_bytes(b"UNCHANGED_PICTURE")

        docx_bytes = make_fake_docx(
            media_files={
                "image1339.png": b"UNCHANGED_PICTURE",
                "image1904.png": b"BRAND_NEW_PICTURE",
            },
            rels={"rId1": "image1339.png", "rId2": "image1904.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        rId_map, count, reused = extract_images_script.extract_images(
            docx_path, existing_dir, existing_images_dir=existing_dir
        )

        assert count == 2
        assert reused == 1
        assert rId_map["rId1"] == "image238.png"
        new_name = extract_images_script.content_hash_filename(b"BRAND_NEW_PICTURE", "image1904.png")
        assert rId_map["rId2"] == new_name
        assert (existing_dir / new_name).read_bytes() == b"BRAND_NEW_PICTURE"
        # The reused file must be untouched, not duplicated under a new name.
        assert sorted(p.name for p in existing_dir.iterdir()) == sorted(["image238.png", new_name])

    def test_convert_and_extract_scripts_agree_when_reusing(self, tmp_path):
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        (existing_dir / "image238.png").write_bytes(b"UNCHANGED_PICTURE")

        docx_bytes = make_fake_docx(
            media_files={"image1339.png": b"UNCHANGED_PICTURE"},
            rels={"rId1": "image1339.png"},
        )
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(docx_bytes)

        existing_index = docx_to_md.build_existing_hash_index(existing_dir)
        from_convert_script = docx_to_md._extract_rId_map(docx_path, existing_index)
        from_extract_script, _, _ = extract_images_script.extract_images(
            docx_path, existing_dir, existing_images_dir=existing_dir
        )

        assert from_convert_script == from_extract_script
