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
| **pptx** | Convert PPTX decks to Markdown (with speaker notes), print a slide outline, extract tables/images, or render each slide to PNG for vision processing |

## Requirements

- `uv` available in `$PATH`
- For PDF OCR or `pptx images --ocr`: system `tesseract` binary
- For `pptx render`: system `libreoffice` (`soffice`) and `poppler`

## Usage

```text
/utils:pdf document.pdf markdown --output document.md
/utils:pdf scanned.pdf ocr --lang eng
/utils:pdf report.pdf tables --format csv

/utils:pptx deck.pptx markdown --output deck.md
/utils:pptx deck.pptx outline
/utils:pptx deck.pptx tables --output-dir ./tables
/utils:pptx deck.pptx images --output-dir ./imgs --ocr
/utils:pptx deck.pptx render --output-dir ./png --dpi 200
```
