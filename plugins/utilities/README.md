# Utilities Plugin

General-purpose document and workflow utilities for code agents.

## Installation

```bash
claude plugin install utilities
```

## Skills

| Skill | Description |
|-------|-------------|
| **pdf** | Convert PDFs to Markdown, extract OCR text from scanned PDFs, and extract tables |

## Requirements

- `uv` available in `$PATH`
- For OCR: system `tesseract` binary

## Usage

```text
/utilities:pdf document.pdf markdown --output document.md
/utilities:pdf scanned.pdf ocr --lang eng
/utilities:pdf report.pdf tables --format csv
```
