---
name: utils:docx
description: Convert DOCX files to clean Markdown with proper heading hierarchy, bold/italic formatting, pipe tables, and image references. Use when the user needs to convert a Word document to Markdown for LLM/agent consumption, documentation websites, or RAG pipelines.
argument-hint: "<docx_path> [markdown|images] [--image-prefix <prefix>] [--toc] [--output <file>] [--output-dir <dir>]"
allowed-tools: Bash
---

# DOCX Extraction Skill

Two focused operations for Word document processing.

## Prerequisites

- **`uv`** — Python package manager (<https://docs.astral.sh/uv/>). Python deps install automatically on first `uv run`.
- `${CLAUDE_PLUGIN_ROOT}` must be set to the plugin root.

---

## Operations

### Markdown — Convert DOCX to Markdown

Converts a DOCX file to a single clean Markdown stream: real heading hierarchy,
bold/italic formatting, pipe tables (with cell formatting preserved), and image
references by filename. No base64 embedding. No chapter splitting — that is the
caller's concern.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/docx/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/docx/scripts/docx-to-markdown.py" <docx> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--image-prefix <prefix>` | Prefix prepended to every image filename in refs | `images/` |
| `--toc` | Prepend a Markdown table of contents | Off |
| `--output <file>` | Write result to file instead of stdout | stdout |

**Examples:**

```bash
# Full document to stdout
python docx-to-markdown.py document.docx

# Save to file with custom image prefix
python docx-to-markdown.py document.docx --image-prefix /docs/images/ --output doc.md

# Include a table of contents
python docx-to-markdown.py document.docx --toc --output doc.md
```

---

### Images — Extract Embedded Images

Extracts all embedded images to a directory and prints the `rId → filename` map
to stdout. Useful when the caller needs to know which image file corresponds to
which `rId` in the document relationships.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}/skills/docx/scripts" python "${CLAUDE_PLUGIN_ROOT}/skills/docx/scripts/extract-images.py" <docx> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--output-dir <dir>` | Directory to extract images into | `./images` |

**Examples:**

```bash
# Extract to default ./images/
python extract-images.py document.docx

# Extract to a specific directory
python extract-images.py document.docx --output-dir /tmp/imgs
```

---

## Workflow

1. **Parse** the user's request — identify operation (`markdown` or `images`), DOCX path, and options.
2. **Run** the appropriate script via `Bash`.
3. **Present results** — for stdout output, show inline; for file output, report the path.

---

## Error Handling

| Error | Action |
|-------|--------|
| `ModuleNotFoundError` | Run `uv sync --project "${CLAUDE_PLUGIN_ROOT}/skills/docx/scripts"` and retry |
| `uv: command not found` | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| File not found | Report the path and ask the user to confirm the location |
