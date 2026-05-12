---
name: oca:audit-module
description: Audit an existing Odoo module against version-specific OCA conventions and syntax rules. Use when checking code quality, before PRs, or after upgrading to a new Odoo version.
argument-hint: "<module_path> [--version <16.0|17.0|18.0|19.0>]"
allowed-tools: Read, Grep, Glob, Bash(find:*)
---

# Audit an Odoo module against version-specific conventions

Systematically scan an existing module for deprecated syntax, OCA convention
violations, wrong constraint styles, structural issues, and security patterns.
Uses the shared references in `plugins/oca/references/` as the audit
knowledge base — no hard-coded rules, always load from the reference files.

## Scope — Read-Only

This skill **only reads and reports**. It must never:

- Edit, create, or delete any file
- Run pre-commit, formatters, or any fix command
- Search for Odoo source code on the filesystem (e.g. `~/code/odoo`, `code/odoo`, `/opt/odoo`) — all rules are inline in this SKILL.md

After delivering the full report, you may ask the user:
> "Would you like me to fix any of these? If so, which ones?"

Do **not** take any action until the user explicitly confirms and specifies what to fix.

## Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `<module_path>` | yes | — | Path to the module directory |
| `--version` | no | auto-detect | Odoo version: `16.0`, `17.0`, `18.0`, `19.0` |

## References

Load during the workflow steps where noted:

- [Version Matrix](plugins/oca/references/version-matrix.md) — version-specific syntax differences and deprecations
- [OCA Conventions](plugins/oca/references/oca-conventions.md) — field ordering, noupdate, string quoting, security patterns
- [Manifest Fields](plugins/oca/references/manifest-fields.md) — required fields, load order, feature-specific additions
- [Module Structure](plugins/oca/references/module-structure.md) — directory tree, naming conventions
- [QWeb Templates](plugins/oca/references/qweb-templates.md) — portal/report/OWL template patterns

## Workflow

### 1. Validate and Locate Module

Check the module path:

```bash
find <module_path> -name "__manifest__.py" -maxdepth 1
```

- Module not found (no `__manifest__.py`)? Stop:
  > No `__manifest__.py` found at `<module_path>`. Pass the module's root directory.

### 2. Detect Version

Read `<module_path>/__manifest__.py`. Extract the `version` field:

- Format: `"version": "XX.0.Y.Z.W"` — the Odoo major version is the `XX.0` prefix.
- If `--version` was passed: use that and skip detection.
- If version field missing or unreadable: ask the user which version to audit against.

Use this table to determine which check groups apply. **This table is complete on its own —
do not search Odoo source code or external directories to verify these rules.**

| Feature | v16.0 | v17.0 | v18.0 | v19.0 |
|---|---|---|---|---|
| `constraint_style` | `_sql_constraints` list | `_sql_constraints` list | `_sql_constraints` list | **named class attrs** |
| `list_tag` | `<tree>` | `<tree>` | **`<list>`** | **`<list>`** |
| `chatter_syntax` | full div | full div | **`<chatter/>`** | **`<chatter/>`** |
| `attrs=` / `states=` | valid | **removed** | removed | removed |
| JS `@odoo-module` header | required | required | optional | not needed |
| `name_get()` | deprecated | deprecated | deprecated | deprecated |
| `user_has_groups()` | OK | OK | **→ `has_group()`** | same |
| `check_access_rights()` | OK | OK | **→ `check_access()`** | same |
| `group_operator=` attr | OK | OK | **→ `aggregator=`** | same |
| `self._cr` / `self._uid` | OK | OK | OK | **→ `self.env.cr/uid`** |
| `groups_id` field name | OK | OK | OK | **→ `group_ids`** |
| `read_group()` ORM call | OK | OK | OK | **→ `_read_group()`** |
| `toggle_active()` | OK | OK | OK | **→ `action_archive/unarchive()`** |
| `odoo.osv.expression` | OK | OK | OK | **→ `odoo.fields.Domain`** |

### 3. Collect Module Files

```bash
find <module_path> -type f \( -name "*.py" -o -name "*.xml" -o -name "*.csv" -o -name "*.js" \) | sort
```

Categorize by directory:

- `models/**/*.py`, `wizard/**/*.py` → Python model/wizard files
- `views/**/*.xml`, `wizard/**/*.xml`, `report/**/*.xml` → XML view files
- `security/ir.model.access.csv` → ACL file
- `security/security.xml` → Security groups/rules
- `static/src/**/*.js` → JavaScript files
- `static/src/**/*.xml` → OWL template files
- `__manifest__.py` → Manifest

### 4. Run Checks

Run each check group below using Grep (content search) and Read (full context for ambiguous hits). Record every violation with: **severity**, **file**, **line context**, and **fix hint**.

Severities:

- **Critical** — crashes Odoo, security vulnerability, data loss risk
- **Major** — deprecated syntax that will break in a future version or OCA CI failure
- **Minor** — convention violation, style issue, missing optional best practice

---

#### A. Manifest Checks

Read `__manifest__.py` in full.

| # | Check | Severity | Signal |
|---|---|---|---|
| M1 | `"license"` key absent | **Major** | `"license"` not in manifest content |
| M2 | Version format wrong (must be `X.0.Y.Z.W`, 5 segments) | **Minor** | version string has ≠ 5 dot-separated segments |
| M3 | `"installable"` key absent | **Minor** | `"installable"` not in manifest content |
| M4 | `"summary"` present but doesn't end with `.` | **Minor** | `summary` value without trailing period |
| M5 | `data` load order: any `views/` entry before `security/` entry | **Major** | Security files must load before views |
| M6 | `"demo"` key present but `demo/` directory is empty or missing | **Minor** | cross-check demo entries against filesystem |

**M5 load-order check — how to detect:**
Read the `data` list. Find the index of the first `views/` entry and the last `security/` entry. If `last_security_index > first_views_index`, flag it.

---

#### B. Python Model Checks

Run Grep across all Python model files. Apply only the checks relevant to the detected version.

**All versions:**

| # | Pattern | Severity | Fix |
|---|---|---|---|
| P1 | `def name_get\(` in non-test Python files | **Major** (v17+) | Replace with `_compute_display_name` |
| P2 | `readonly=True` on a field definition inside a non-TransientModel class | **Major** (v17+) | Move `readonly` to the view; model-level readonly breaks Odoo import |
| P3 | `'[^']*'` — single-quoted strings in Python (anywhere) | **Minor** | ruff-format enforces double quotes in OCA repos |

**v17+ checks** (skip if version is 16.0):

| # | Pattern | Severity | Fix |
|---|---|---|---|
| P1 | `def name_get\(` | **Major** | Replace with `_compute_display_name` |
| P2 | `readonly=True` on model field (non-TransientModel) | **Major** | Move `readonly` to view |

**v18+ checks** (skip if version is 16.0 or 17.0):

| # | Pattern | Severity | Fix |
|---|---|---|---|
| P4 | `user_has_groups\(` | **Major** | → `self.env.user.has_group(` |
| P5 | `check_access_rights\(` | **Major** | → `check_access(` |
| P6 | `_filter_access_rules\(` | **Major** | → `_filtered_access(` |
| P7 | `group_operator=` as a field attribute | **Major** | → `aggregator=` |

**v19-only checks** (skip if version is 16.0, 17.0, or 18.0):

| # | Pattern | Severity | Fix |
|---|---|---|---|
| P8 | `_sql_constraints\s*=\s*\[` | **Critical** | → named `models.Constraint` class attrs |
| P9 | `self\._cr\b` | **Major** | → `self.env.cr` |
| P10 | `self\._uid\b` | **Major** | → `self.env.uid` |
| P11 | `\.read_group\(` (ORM call, not `_read_group`) | **Major** | → `_read_group()` or `formatted_read_group()` |
| P12 | `toggle_active\(` | **Major** | → `action_archive()` / `action_unarchive()` |
| P13 | `ormcache_context` | **Major** | → `@ormcache` |
| P14 | `odoo\.osv\.expression` import | **Major** | → `from odoo.fields import Domain` |
| P15 | `groups_id\b` (field name) | **Major** | → `group_ids` |

**How to run Grep for each check:**

```text
Grep pattern: <pattern from table>
Path: <module_path>/models  (and /wizard for relevant checks)
Output: content, with line numbers
```

For P8 (`_sql_constraints` on v19): grep models/ and wizard/. Each hit in a non-TransientModel class is critical.

For P2 (`readonly=True`): grep models/ for `readonly=True`. For each hit, check the surrounding class — if it's `TransientModel`, skip it. Otherwise flag it.

---

#### C. XML View Checks

Grep across all XML files in `views/`, `wizard/`, and `report/`.

**All versions:**

| # | Pattern | Severity | Fix |
|---|---|---|---|
| V1 | `decoration-[a-z]` attribute on `<field` element | **Major** | Move `decoration-*` to the `<list>`/`<tree>` tag; use `widget="badge"` on field |
| V2 | `expand=` attribute on `<group` inside `<search` | **Major** | Remove `expand` — invalid on `<group>` in search views, causes RNG error |
| V3 | `t-esc=` in templates | **Minor** | → `t-out=` (preferred; `t-esc` deprecated) |
| V4 | `t-raw=` in templates | **Critical** | → `t-out=` with `Markup` — `t-raw` is XSS-unsafe |

**v17+ checks** (skip if version is 16.0):

| # | Pattern | Severity | Fix |
|---|---|---|---|
| V5 | `attrs="` in view XML | **Major** | → inline `invisible=`/`required=`/`readonly=` expressions |
| V6 | `states="` attribute on buttons/fields | **Major** | → inline `invisible=` expression |

**v18+ checks** (skip if version ≤ 17.0):

| # | Pattern | Severity | Fix |
|---|---|---|---|
| V7 | `<tree\b` as list view tag (not inside XPath expr targeting an existing view) | **Major** | → `<list` |
| V8 | `class="oe_chatter"` or `<div class="oe_chatter` | **Major** | → `<chatter/>` |

**Disambiguation for V7:** The pattern `<tree` could appear in XPath expressions like `<xpath expr="//tree">` when inheriting an existing view that uses `<tree>`. That is NOT a violation — the XPath must match the parent view's tag. Only flag `<tree` when it appears as the root element of `<field name="arch" type="xml">`.

---

#### D. JavaScript / OWL Template Checks

Grep across `static/src/**/*.js` and `static/src/**/*.xml`.

| # | Version | Pattern | Severity | Fix |
|---|---|---|---|---|
| J1 | v16, v17 | JS file WITHOUT `/** @odoo-module */` header | **Major** | Add `/** @odoo-module */` at the top |
| J2 | v17+ | `owl="1"` on `<templates` tag | **Major** | Remove — `<templates xml:space="preserve">` is sufficient |

**For J1:** Glob all `.js` files in `static/src/`. For each, check if the first 3 lines contain `@odoo-module`. If not, it's a violation (v16/v17 only).

**For J1 on v18+:** The header is optional. Do NOT flag its absence as a violation. Flag its presence as an informational note only (no action required).

---

#### E. Directory Structure Checks

```bash
find <module_path> -type f | sort
```

| # | Check | Severity | Condition |
|---|---|---|---|
| S1 | `tests/` directory missing | **Major** | OCA requires tests |
| S2 | `tests/__init__.py` missing | **Major** | Module won't be discoverable |
| S3 | `security/ir.model.access.csv` missing | **Major** | Any Python model file exists → ACL required |
| S4 | `readme/DESCRIPTION.rst` missing | **Minor** | OCA contribution standard (skip for Trobz internal — check `author` field) |
| S5 | Model file(s) in root directory (not in `models/`) | **Minor** | `*.py` at module root other than `__init__.py` |
| S6 | XML view file in `wizard/` (not a `__init__.py` or Python file) | **Minor** (if using old pattern) | Wizard views should be in `wizard/` — check if they're referenced correctly in manifest |

**For S3:** only flag if Glob finds any `models/*.py` files (excluding `__init__.py`).

**For S4:** Read the manifest `author` field. If it contains `"OCA"` or `"Odoo Community Association"`, this is Major. Otherwise Minor.

---

#### F. Security File Checks

Read `security/ir.model.access.csv` and `security/security.xml` if they exist.

| # | Check | Severity | Signal |
|---|---|---|---|
| A1 | ACL file has no read-only user line (perm_read=1, others=0) | **Major** | Every model should have a base user read-only row |
| A2 | `security.xml` records missing `noupdate="1"` on `<odoo>` tag | **Major** | Security groups must not be overwritten on update |
| A3 | `model_id:id` value uses dot notation instead of underscore | **Major** | `model_my_model` not `model_my.model` |

---

### 5. Compile and Report

Print the full structured report below. **Every violation must appear as an individual numbered item** — do not collapse violations into a count or a vague summary. Stats go at the bottom, after all violations are listed.

```text
## Module Audit: <module_name> (v<version>)

---

### Critical (<N>)

1. **[<ID>] <short title>**
   File: `<relative/path/to/file>` (line <N>: `<matching snippet>`)
   Problem: <one sentence describing what is wrong and why>
   Fix: `<concrete replacement or action>`

2. ...

### Major (<N>)

1. **[<ID>] <short title>**
   File: `<relative/path/to/file>` (line <N>: `<matching snippet>`)
   Problem: <one sentence>
   Fix: `<concrete replacement or action>`

...

### Minor (<N>)

...

---

### Passed

<N> checks passed with no violations in: <comma-separated category names>

---

### Summary

Checked <N> rules · <N> critical · <N> major · <N> minor · <N> passed
```

**If zero violations:**

```text
## Module Audit: <module_name> (v<version>)

All <N> checks passed. Module is compliant with Odoo <version> OCA conventions.
```

**After printing the report, ask:**

> Would you like me to fix any of these? If so, say which ones — e.g. "fix all Critical", "fix P8 and V7", or "fix all". I will not make any changes until you confirm.

Do NOT modify any file before the user replies.

---

## Error Handling

- **Module path does not exist**: Stop immediately with clear message.
- **`__manifest__.py` unreadable**: Stop and report.
- **Version could not be detected and not provided**: Ask the user via `AskUserQuestion`.
- **No model files found**: Skip all model checks, note it in the report.
- **No JS files found**: Skip all JS checks, note it in the report.
- **Grep returns no results**: Record the check as passed.

## Updating Checks

This skill's checks are derived from the reference files in `plugins/oca/references/`.
When Odoo releases a new version:

1. Update `references/version-matrix.md` with new deprecations
2. The checks in this skill automatically apply them — no skill rewrite needed

The one place that needs updating is the version-specific routing tables (v17+, v18+, v19-only)
in Steps 4B–4D above. Add a new version column when a new major version introduces changes.
