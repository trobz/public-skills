#!/usr/bin/env python3
"""Tests for PDF skill scripts."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def load_script(script_name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / script_name)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


pdf_to_markdown = load_script("pdf-to-markdown.py", "pdf_to_markdown")
ocr_pdf_script = load_script("ocr-pdf.py", "ocr_pdf_script")
extract_tables_script = load_script("extract-tables.py", "extract_tables_script")


class TestPdfToMarkdown:
    """Test Markdown conversion helpers."""

    def test_parse_pages_supports_ranges_and_single_pages(self):
        assert pdf_to_markdown.parse_pages("1-3,5,7-8") == [1, 2, 3, 5, 7, 8]

    def test_clean_footers_removes_page_numbers_and_repeated_footer_lines(self):
        text = "\n\n".join(
            [
                "Intro content",
                "________________________________________________________________ Company | contact@example.com | example.com",
                "1",
                "Main content",
                "> ________________________________________________________________ Company | contact@example.com | example.com",
                "2",
                "Closing content",
                "________________________________________________________________ Company | contact@example.com | example.com",
                "3",
            ]
        )

        cleaned = pdf_to_markdown.clean_footers(text, footer_pattern=None)

        assert "Intro content" in cleaned
        assert "Main content" in cleaned
        assert "Closing content" in cleaned
        assert "Company | contact@example.com" not in cleaned
        assert "\n1\n" not in f"\n{cleaned}\n"
        assert "\n2\n" not in f"\n{cleaned}\n"
        assert "\n3\n" not in f"\n{cleaned}\n"

    def test_pdf_to_markdown_converts_pages_to_zero_based_indices(self, monkeypatch):
        calls = {}

        def fake_to_markdown(pdf_path, **kwargs):
            calls["pdf_path"] = pdf_path
            calls["kwargs"] = kwargs
            return "markdown"

        monkeypatch.setitem(
            sys.modules,
            "pymupdf4llm",
            SimpleNamespace(to_markdown=fake_to_markdown),
        )

        assert pdf_to_markdown.pdf_to_markdown("sample.pdf", pages=[1, 3]) == "markdown"
        assert calls == {"pdf_path": "sample.pdf", "kwargs": {"pages": [0, 2]}}


class TestOcrPdf:
    """Test OCR orchestration without invoking Tesseract."""

    def test_ocr_pdf_uses_requested_page_range_and_language(self, monkeypatch):
        calls = {}

        def fake_convert_from_path(pdf_path, **kwargs):
            calls["convert"] = {"pdf_path": pdf_path, "kwargs": kwargs}
            return ["image-a", "image-b"]

        def fake_image_to_string(image, lang):
            calls.setdefault("ocr", []).append({"image": image, "lang": lang})
            return f"text from {image}"

        monkeypatch.setitem(
            sys.modules,
            "pdf2image",
            SimpleNamespace(convert_from_path=fake_convert_from_path),
        )
        monkeypatch.setitem(
            sys.modules,
            "pytesseract",
            SimpleNamespace(image_to_string=fake_image_to_string),
        )

        text = ocr_pdf_script.ocr_pdf("scan.pdf", pages=[2, 3], lang="deu")

        assert calls["convert"] == {
            "pdf_path": "scan.pdf",
            "kwargs": {"first_page": 2, "last_page": 3},
        }
        assert calls["ocr"] == [
            {"image": "image-a", "lang": "deu"},
            {"image": "image-b", "lang": "deu"},
        ]
        assert "=== Page 2 ===\ntext from image-a" in text
        assert "=== Page 3 ===\ntext from image-b" in text


class TestExtractTables:
    """Test table extraction and formatting."""

    def test_format_as_csv(self):
        csv_text = extract_tables_script.format_as_csv([["Name", "Count"], ["A", 2]])
        assert csv_text == "Name,Count\r\nA,2\r\n"

    def test_format_as_text_aligns_columns(self):
        table_text = extract_tables_script.format_as_text([["Name", "Count"], ["Alice", 2]])
        assert table_text == "Name  | Count\nAlice | 2    "

    def test_extract_tables_reads_selected_pages(self, monkeypatch):
        class FakePage:
            def __init__(self, tables):
                self._tables = tables

            def extract_tables(self):
                return self._tables

        class FakePdf:
            pages = [
                FakePage([[["skip"]]]),
                FakePage([[["Name"], ["Alice"]]]),
                FakePage([]),
            ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        monkeypatch.setitem(
            sys.modules,
            "pdfplumber",
            SimpleNamespace(open=lambda pdf_path: FakePdf()),
        )

        tables = extract_tables_script.extract_tables("tables.pdf", pages=[2, 99])

        assert tables == [{"page": 2, "table": 1, "data": [["Name"], ["Alice"]]}]
