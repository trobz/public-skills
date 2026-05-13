# Trobz Public Skills

<!-- markdownlint-disable MD024 -->

A public marketplace of plugins for Claude Code, OpenCode, OpenAI Codex CLI, Cursor, Amp, Google Antigravity, and other code agents.

## Installation

### Claude Code

Add this marketplace to your Claude Code configuration:

```bash
claude plugin marketplace add git@github.com:trobz/public-skills.git
```

Or from a local clone:

```bash
claude plugin marketplace add ~/code/trobz/packages/public-skills
```

### Other Agents (Amp, OpenCode, Codex CLI, Cursor, Antigravity)

All agents that support `SKILL.md`-based skills can be installed via [`npx skills`](https://github.com/vercel-labs/skills):

```bash
# List available skills before installing
npx skills add git@github.com:trobz/public-skills.git --list

# Install all skills globally for your agent
npx skills add git@github.com:trobz/public-skills.git -a <agent> -g

# Install a specific skill globally
npx skills add git@github.com:trobz/public-skills.git --skill odooly -a <agent> -g
npx skills add git@github.com:trobz/public-skills.git --skill pdf -a <agent> -g

# Install to current project only (no -g flag)
npx skills add git@github.com:trobz/public-skills.git -a <agent>

# Update all installed skills to latest version
npx skills update
```

Where `<agent>` is one of: `amp`, `opencode`, `codex`, `cursor`, `antigravity`.

From a local clone:

```bash
npx skills add ~/code/trobz/packages/public-skills -a <agent> -g
```

## Available Plugins

### Odoo

Odoo data inspection and querying toolkit using the `odooly` CLI.

**Installation:**

```bash
claude plugin install odoo
```

**Requirements:**

- `odooly` available in `$PATH`
- Configuration file at `~/odooly.ini`

**Skills:**

| Skill | Description |
|-------|-------------|
| **odooly** | Query and inspect Odoo data using odooly CLI |

**Examples:**

```text
/odoo:odooly search partners named John
/odoo:odooly show sale orders in state done
```

Or ask naturally: "Show me all sale orders from partner Trobz"

### Utilities

General-purpose document and workflow utilities for code agents.

**Installation:**

```bash
claude plugin install utilities
```

**Requirements:**

- `uv` available in `$PATH`
- For OCR: system `tesseract` binary

**Skills:**

| Skill | Description |
|-------|-------------|
| **pdf** | Convert PDFs to clean Markdown, extract OCR text from scanned PDFs, and extract tables |

**Examples:**

```text
/utilities:pdf document.pdf markdown --output document.md
/utilities:pdf scanned.pdf ocr --lang eng
/utilities:pdf report.pdf tables --format csv
```

## Contributing

### Pre-commit hooks

This repo uses [pre-commit](https://pre-commit.com/) to lint Markdown and JSON files.

Install the hooks after cloning:

```bash
pip install pre-commit
pre-commit install
```

Run manually against all files:

```bash
pre-commit run --all-files
```

The CI workflow runs these checks automatically on every push and pull request.

## Development

To add new plugins to this marketplace:

1. Create a new directory in `plugins/`
2. Add `.claude-plugin/plugin.json` with plugin metadata
3. Add your commands/skills
4. Update `.claude-plugin/marketplace.json` to include the new plugin
5. Update this README

## Validation

Validate the marketplace structure:

```bash
claude plugin validate .
```
