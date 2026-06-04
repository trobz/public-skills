---
name: utils:pptx
description: Convert PPTX decks to agent-ready Markdown (with speaker notes inline), print a slide outline, extract tables, dump embedded images (optionally OCR'd), or render each slide to PNG for vision processing. Use when the user needs to read, summarize, or extract content from a `.pptx` deck.
argument-hint: "<pptx_path> [markdown|outline|tables|images|render] [--slides <range>] [--no-notes] [--images-dir <dir>] [--ocr] [--format csv|text] [--lang <code>] [--dpi <n>] [--output <file>] [--output-dir <dir>]"
allowed-tools: Bash
---

# PPTX Extraction Skill

Five focused operations for PowerPoint deck processing.

## Prerequisites

- **`uv`** — Python package manager (<https://docs.astral.sh/uv/>). Python deps install automatically on first `uv run`.
- **`render` only**: system `libreoffice` (provides `soffice`) and `poppler` (`brew install --cask libreoffice && brew install poppler` / `apt install libreoffice poppler-utils`).
- **`images --ocr` only**: system `tesseract` (`brew install tesseract` / `apt install tesseract-ocr`).
- `${CLAUDE_PLUGIN_ROOT}` must be set to the plugin root.

---

## Decision Tree

- Text-heavy deck → use `markdown` (default).
- Want a quick TOC / decide which slides to drill into → use `outline`.
- Need structured tabular data → use `tables`.
- Need embedded illustrations / screenshot OCR → use `images` (`--ocr` for screenshot-style slides).
- Deck is graphics-heavy / mostly images and you need Vision processing → use `render`.
- Mixed deck (some text slides, some image-only) → run `markdown` first; for slides that come out empty or near-empty, follow up with `render --slides <those slide numbers>`.

---

## Operations

### Markdown — Convert PPTX to Markdown (recommended default)

For each slide, emits a consistent block:

```markdown
<!-- Slide number: N -->
# <title>

- bullet (level 0)
  - sub-bullet (level 1)
    - sub-sub-bullet (level 2)

> [IMAGE: ./imgs/slideN_img1.png — <alt text or "no alt text">]

### Notes:
<speaker notes, or empty>
```

**Format rules the script must follow:**

- **Slide marker**: always `<!-- Slide number: N -->` — gives agents an unambiguous positional anchor.
- **Title**: taken from the slide's title placeholder; falls back to `# Slide N` when absent. Internal line breaks are collapsed to single spaces.
- **Body bullets**: indented by the slide's own outline level (level 0 → `- text`, level 1 → two-space indent, etc.). A paragraph that merely repeats the title is dropped as a duplicate.
- **Skip**: slide-number, date, and footer placeholders (page-number tokens like `‹#›`) are never emitted.
- **Images**: extract every embedded image to `--images-dir` (default: `<deck_name>_imgs/` next to the output file). Emit an inline reference at the position where the image appeared in the slide:

  ```text
  > [IMAGE: ./deck_imgs/slideN_imgM.png — <alt text or "no alt text">]
  ```

  Never silently drop images. Images are extracted by default; with `--no-images` the marker is still emitted as `[not extracted]` so the agent knows content is missing.
- **Notes**: always emit `### Notes:` after body content, even when empty. This keeps structure consistent for agent parsing. Pass `--no-notes` to suppress entirely.
- **Tables**: render inline as GitHub-flavoured Markdown tables.
- **Charts**: render inline as a GFM table with a `**Chart: title**` header row. Category names form the first column; each data series is a column. Unsupported chart types emit `[unsupported chart]`.

**Image handling summary:**

| Situation | What the agent sees in the md |
|-----------|-------------------------------|
| Image extracted (default) | `> [IMAGE: ./imgs/slideN_imgM.png — alt text]` |
| No alt text on image | `> [IMAGE: ./imgs/slideN_imgM.png — no alt text]` |
| `--no-images` set | `> [IMAGE: not extracted — slideN_imgM]` |
| Image is OCR'd (`--ocr`) | `> [IMAGE: ./imgs/slideN_imgM.png — alt text]` followed by a `> OCR: <text>` line |

**Quality check after conversion:**

```bash
# Page-number chrome should be fully stripped — this returns 0 if clean
grep -c '‹#›' out.md

# Every embedded image should be referenced; compare against the deck's image count
grep -c '> \[IMAGE:' out.md
```

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts/pptx-to-markdown.py" <pptx> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--slides 1-3` | Slide range (e.g. `1-3`, `2,4,6`) | All slides |
| `--no-notes` | Skip speaker notes entirely | Notes included |
| `--images-dir ./imgs/` | Extract embedded images to this directory and reference in md | `<deck>_imgs/` next to output |
| `--no-images` | Skip image extraction entirely (emits `[not extracted]` markers) | Images extracted |
| `--ocr` | Run tesseract on each extracted image, embed OCR text inline | Off |
| `--lang eng` | Tesseract language code for OCR | `eng` |
| `--output out.md` | Write result to file instead of stdout | stdout |

**Examples:**

```bash
# Full deck, images extracted to ./deck_imgs/, notes included
python pptx-to-markdown.py deck.pptx --output deck.md

# Slides 1–5 only, custom image dir, no notes
python pptx-to-markdown.py deck.pptx --slides 1-5 --images-dir ./imgs --no-notes --output deck.md

# Full deck with inline OCR text for every image
python pptx-to-markdown.py deck.pptx --ocr --output deck.md

# Skip image extraction (agent will see [not extracted] markers)
python pptx-to-markdown.py deck.pptx --no-images --output deck.md
```

---

### Outline — Slide titles + structure scan

Quick scan of a long deck before extracting more. Useful for agents deciding which slides to drill into. Output includes slide number, title, whether body content is present, image count, and whether speaker notes exist.

**Output format:**

```text
1.  Slide 1                          [no content] [0 images] [no notes]
2.  Introduction: OCA at Trobz?      [content]    [0 images] [no notes]
3.  OCA 101                          [no content] [0 images] [no notes]
4.  OCA 101                          [content]    [2 images] [no notes]
13. More resources                   [content]    [1 image]  [notes]
```

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts/pptx-outline.py" <pptx> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--slides 1-3` | Slide range | All slides |
| `--output out.txt` | Write result to file | stdout |

**Example:**

```bash
python pptx-outline.py deck.pptx
```

---

### Tables — Extract tables from slides

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts/extract-tables.py" <pptx> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--slides 1-3` | Slide range | All slides |
| `--format csv\|text` | Output format | `text` |
| `--output-dir ./out/` | Save each table as `slideN_tableM.csv` | stdout |

**Examples:**

```bash
# Print all tables as text
python extract-tables.py deck.pptx

# Export each table to its own CSV file
python extract-tables.py deck.pptx --output-dir ./tables/
```

---

### Images — Dump embedded images (optionally OCR'd)

Standalone image extraction when you want the images separately from a markdown conversion. For most agent workflows, prefer using `markdown --images-dir` instead, which extracts images and references them inline.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts/extract-images.py" <pptx> --output-dir <dir> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--output-dir ./imgs/` | Directory for extracted images (required) | — |
| `--slides 1-3` | Slide range | All slides |
| `--ocr` | Run tesseract on each image, emit sidecar `.txt` | Off |
| `--lang eng` | Tesseract language code | `eng` |

**Example:**

```bash
# Dump all images, OCR each into a sidecar .txt
python extract-images.py deck.pptx --output-dir ./imgs --ocr --lang fra
```

---

### Render — Slides → PNG (vision pathway)

Converts the deck to PDF via LibreOffice headless, then rasterises each page to PNG. Use this for graphics-heavy decks or as a follow-up for slides that produced empty markdown output.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts/render-slides.py" <pptx> --output-dir <dir> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--output-dir ./png/` | Directory for PNG files (required) | — |
| `--slides 1-3` | Slide range | All slides |
| `--dpi 150` | Render DPI | `150` |

**Example:**

```bash
# Render slides 1–10 at 200 DPI for Claude Vision
python render-slides.py deck.pptx --output-dir ./png --slides 1-10 --dpi 200
```

---

## Workflow

1. **Parse** the user's request — identify operation, PPTX path, and options.
2. **Check prerequisites** — for `render`, confirm `soffice` is on `PATH`; for `--ocr`, confirm `tesseract` is installed.
3. **Run** the appropriate script via `Bash`.
4. **Verify output** — for `markdown`, run the quality check grep commands above and confirm image count matches. For `outline`, confirm slide count matches expectations.
5. **Present results** — for stdout output, show the content inline; for file/directory output, report the paths written. Always report the images directory path if images were extracted.

---

## Error Handling

| Error | Action |
|-------|--------|
| `ModuleNotFoundError` | Run `uv sync --project "${CLAUDE_PLUGIN_ROOT}/skills/pptx/scripts"` and retry |
| `soffice` not found | Tell user to install LibreOffice (`brew install --cask libreoffice` / `apt install libreoffice`) |
| `tesseract` not found | Tell user to install tesseract (`brew install tesseract` / `apt install tesseract-ocr`) |
| `uv: command not found` | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| No tables / images found | Inform user; suggest `markdown` (text) or `render` (graphics-heavy) as alternatives |
| Slide out of range | Report total slide count and re-run with a corrected range |
| Empty slides in markdown output | Run `render --slides <empty slide numbers>` as follow-up for vision processing |
| Images missing from output md | Confirm extraction wasn't disabled (`--no-images`) and the images directory is writable |
