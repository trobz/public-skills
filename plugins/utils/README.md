# Utils Plugin

General-purpose document and workflow utilities for code agents.

## Installation

```bash
claude plugin install utils
```

## Skills

| Skill | Description |
|-------|-------------|
| **pdf** | Convert PDFs to clean Markdown, extract OCR text from scanned PDFs, and extract tables |

## Requirements

- `uv` available in `$PATH`
- For OCR: system `tesseract` binary

## Usage

```text
/utils:pdf document.pdf markdown --output document.md
/utils:pdf scanned.pdf ocr --lang eng
/utils:pdf report.pdf tables --format csv
```
