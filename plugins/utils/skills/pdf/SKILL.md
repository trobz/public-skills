---
name: utils:pdf
description: Convert PDFs to agent-ready Markdown with automatic footer cleanup, extract text from scanned PDFs (OCR), and extract tables. Use when the user needs to convert a PDF to clean Markdown for LLM/agent consumption, read text from a scanned PDF, or pull structured table data from a PDF.
argument-hint: "<pdf_path> [markdown|ocr|tables] [--pages <range>] [--lang <code>] [--format csv|text] [--output <file>] [--output-dir <dir>] [--footer-pattern <regex>]"
allowed-tools: Bash
---

# PDF Extraction Skill

Three focused operations for PDF document processing.

## Prerequisites

- **`uv`** — Python package manager (<https://docs.astral.sh/uv/>). Python deps install automatically on first `uv run`.
- **OCR only**: system `tesseract` binary (`apt install tesseract-ocr` / `brew install tesseract`).
- **Non-English OCR**: install the matching tessdata (e.g. `apt install tesseract-ocr-vie`) and pass `--lang`. Without it, Tesseract silently falls back to English and mangles non-Latin/diacritic text (e.g. Vietnamese `hoặc` → `hodc`) instead of erroring.
- `${CLAUDE_PLUGIN_ROOT}` must be set to the plugin root.

---

## Operations

### Markdown — Convert PDF to Markdown (recommended default)

Use for text-layer PDFs to get agent-ready Markdown with heading detection. Falls back to OCR for scanned PDFs (headings flatten to `##`). Post-conversion cleanup is required for agent input; the script removes standalone page numbers and repeated footer-like lines by default.

**Decision tree:**

- PDF has selectable text → use `markdown`
- PDF is scanned + heading hierarchy doesn't matter → use `markdown` (OCR fallback)
- PDF is scanned + heading hierarchy critical → use `ocr` + Claude Vision post-processing
- Need table data → use `tables`
- PDF is scanned/rasterized in a non-English language → use `markdown` with `--lang` set to that language (see Options below), otherwise OCR runs in English and silently mangles the text

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pdf/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pdf/scripts/pdf-to-markdown.py" <pdf> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--pages 1-3` | Page range (e.g. `1-3`, `2,4,6`) | All pages |
| `--lang vie` | Tesseract language code(s) for the OCR fallback on scanned/rasterized content. Use `+` to combine, e.g. `eng+vie` for bilingual documents. Requires matching tessdata installed. | `eng` |
| `--footer-pattern <regex>` | Regex to strip complex footer noise after automatic cleanup | None |
| `--no-clean` | Skip automatic page-number and repeated-footer cleanup | Off |
| `--output out.md` | Write result to file instead of stdout | stdout |

**Examples:**

```bash
# Full document to stdout
python pdf-to-markdown.py document.pdf

# Pages 1–5, save to file
python pdf-to-markdown.py document.pdf --pages 1-5 --output doc.md

# Scanned/bilingual Vietnamese-English document
python pdf-to-markdown.py document.pdf --lang eng+vie --output doc.md

# Strip custom footer pattern (e.g. separator + company name)
python pdf-to-markdown.py document.pdf --footer-pattern "_{10,}.*?Trobz.*?\n"
```

**Rasterized tables (embedded as images, not native PDF text):** some PDFs (e.g. Excel/InDesign exports flattened to images) embed tables as pictures rather than selectable text or vector grid lines. In these cases OCR extracts raw text from the picture region without any row/column structure, so the resulting Markdown table can be scrambled (columns interleaved, cells merged) even with the correct `--lang`. Signs this is happening: frequent `picture [...] intentionally omitted` / `Start of picture text` markers around garbled tables. There is no reliable automated fix for this — cross-check any figures pulled from such tables against the original PDF (or a rendered page image) rather than trusting the Markdown output verbatim.

**Footer cleanup workflow:**

1. Convert once with the default cleanup.
2. Verify no repeated footer remains: `grep -c 'distinctive footer text' out.md` should return `0`.
3. If a multi-line footer remains, rerun with `--footer-pattern '<regex>'`.
4. Use `--no-clean` only when debugging raw PDF extraction output.

---

### OCR — Extract Text from Scanned PDFs

Use when the PDF contains scanned images (not selectable text).

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pdf/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pdf/scripts/ocr-pdf.py" <pdf> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--pages 1-3` | Page range (e.g. `1-3`, `2,4,6`) | All pages |
| `--lang eng` | Tesseract language code | `eng` |
| `--output out.txt` | Write result to file instead of stdout | stdout |

**Examples:**

```bash
# Full document
python ocr-pdf.py scanned.pdf

# Pages 1–3, French document, save to file
python ocr-pdf.py scanned.pdf --pages 1-3 --lang fra --output extracted.txt
```

---

### Tables — Extract Tables from PDFs

Use when the PDF contains structured tables (native PDF or scanned with detectable grid lines).

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pdf/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pdf/scripts/extract-tables.py" <pdf> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--pages 1-3` | Page range (e.g. `1-3`, `2,4,6`) | All pages |
| `--format csv\|text` | Output format | `text` |
| `--output-dir ./out/` | Save each table as a separate CSV file | stdout |

**Examples:**

```bash
# Print all tables as text
python extract-tables.py report.pdf

# Export all tables to CSV files
python extract-tables.py report.pdf --output-dir ./tables/

# Pages 2–4, CSV format to stdout
python extract-tables.py report.pdf --pages 2-4 --format csv
```

---

## Workflow

1. **Parse** the user's request — identify operation (markdown, ocr, or tables), PDF path, and options.
2. **Check prerequisites** — if packages are missing, install them or instruct the user.
3. **Run** the appropriate script via `Bash`.
4. **Present results** — for stdout output, show the content inline; for file output, report the path.

---

## Error Handling

| Error | Action |
|-------|--------|
| `ModuleNotFoundError` | Run `uv sync --project "${CLAUDE_PLUGIN_ROOT}/skills/pdf/scripts"` and retry |
| `tesseract not found` | Tell user to install tesseract at OS level (`apt install tesseract-ocr` / `brew install tesseract`) |
| No tables found | Inform user; suggest the PDF may be scanned (use OCR instead) |
| `uv: command not found` | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Page out of range | Report valid page count and re-run with corrected range |
