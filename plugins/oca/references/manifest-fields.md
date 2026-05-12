# Odoo Manifest Fields Reference

Complete `__manifest__.py` reference for all supported versions (16.0–19.0).

> **Quoting**: Always use **double quotes** — `ruff-format` (used in OCA pre-commit hooks)
> normalizes all Python strings to double quotes automatically.

---

## Full Manifest Template

```python
{
    # ── Identity ──────────────────────────────────────────────────────────────
    "name": "Human Readable Name",
    # Title case. No "Odoo" prefix. Max ~50 chars for clean display.

    "version": "18.0.1.0.0",
    # Format: {odoo_version}.{major}.{minor}.{patch}
    # New module: always start at x.0.1.0.0

    "category": "Tools",
    # Standard Odoo categories: Accounting, CRM, Discuss, eCommerce, Email
    # Marketing, Employees, Expenses, Field Service, Fleet, HR, Inventory,
    # Invoicing, Lunch, Manufacturing, Marketing, Members, Point of Sale,
    # Project, Purchase, Recruitment, Repairs, Sales, Sign, Timesheets,
    # Technical, Tools, Warehouse, Website, Hidden (internal modules)

    "summary": "One-line description of what this module does.",
    # Ends with period. Shown in Apps list card subtitle.

    # ── Authorship ────────────────────────────────────────────────────────────
    "author": "Trobz",
    # For OCA contributions: "Author Name, Odoo Community Association (OCA)"

    "website": "https://www.trobz.com",
    # For OCA contributions: "https://github.com/OCA/<repo>"

    "license": "LGPL-3",
    # MANDATORY — OCA CI fails without this field.
    # Options: "LGPL-3" (open), "AGPL-3" (copyleft), "OPL-1" (proprietary)

    # ── Dependencies ──────────────────────────────────────────────────────────
    "depends": ["base"],
    # List Odoo module technical names. Keep minimal — only direct deps.
    # Common: "mail", "product", "sale", "account", "stock", "hr", "project"

    "external_dependencies": {
        "python": ["xlrd", "openpyxl"],   # pip packages required at runtime
        "bin": ["gs", "wkhtmltopdf"],     # system binaries required at runtime
    },
    # Both "python" and "bin" are valid keys (confirmed in OCA __manifest__.py template).
    # Only include if truly required. Omit the entire key if none needed.

    # ── Data Files ────────────────────────────────────────────────────────────
    "data": [
        # Load order matters — security before views, data before wizard views
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/<model>_views.xml",
        "views/menus.xml",
        "data/<config_data>.xml",
        "report/<report>.xml",
        "wizard/<wizard>_views.xml",
    ],

    "demo": [
        "demo/demo_data.xml",
    ],
    # Omit "demo" key entirely if --no-demo flag used.

    # ── Assets ────────────────────────────────────────────────────────────────
    "assets": {
        "web.assets_backend": [
            "<module>/static/src/components/**/*.js",
            "<module>/static/src/components/**/*.xml",
            "<module>/static/src/components/**/*.scss",
        ],
        "web.assets_frontend": [
            "<module>/static/src/js/portal.js",
        ],
    },
    # Omit entire "assets" key if no frontend assets.
    # Use glob patterns for component directories, explicit paths for single files.
    # Do NOT use the old XML asset template pattern (removed in v16.0).

    # ── Behavior ──────────────────────────────────────────────────────────────
    "installable": True,
    # Set False to hide from Apps menu (e.g., base modules not meant for direct install)

    "application": False,
    # True for top-level apps that appear in the main Home menu.
    # Only True when module is the entry point for a full functional area.

    "auto_install": False,
    # True to auto-install when all "depends" are installed (bridge/glue modules).

    # ── Hooks ─────────────────────────────────────────────────────────────────
    "pre_init_hook": "pre_init_hook",
    # Function in __init__.py called before module tables are created.
    # Signature v16: (cr) | v17+: (env)
    # Omit if not needed — do NOT add empty hook stubs.

    "post_init_hook": "post_init_hook",
    # Function in __init__.py called after module install completes.
    # Signature v16: (cr, registry) | v17+: (env)
    # Omit if not needed — do NOT add empty hook stubs.

    "uninstall_hook": "uninstall_hook",
    # Function in __init__.py called before module uninstall.
    # Omit if not needed.
}
```

---

## Minimal Manifest (most common case)

```python
{
    "name": "My Module",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "summary": "Short description of what this module does.",
    "author": "Trobz",
    "website": "https://www.trobz.com",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/my_model_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
```

---

## Feature-Specific Additions

### With `--features mail`

```python
"depends": ["base", "mail"],
```

### With `--features sequence`

No extra depends needed (`ir.sequence` is in `base`). Add to `data`:

```python
"data": [
    ...
    "data/sequence_data.xml",
],
```

### With `--features portal`

```python
"depends": ["base", "portal"],
```

### With `--features website`

```python
"depends": ["base", "website"],
```

### With `--app` flag

```python
"application": True,
```

Also add a root category and main menu entry in `views/menus.xml`.

### With frontend OWL components

```python
"assets": {
    "web.assets_backend": [
        "<module>/static/src/components/**/*.js",
        "<module>/static/src/components/**/*.xml",
        "<module>/static/src/components/**/*.scss",
    ],
},
```
