# OCA Module Conventions

Authoritative source: <https://github.com/OCA/odoo-community.org/blob/master/website/Contribution/CONTRIBUTING.rst>

---

## Python String Quoting

OCA repos use **double quotes** for Python strings. This is enforced automatically
by `ruff-format` in the pre-commit stack (not stated explicitly in the style guide
but applied across all OCA repos on 17.0+). Write all Python code examples with
double quotes — `ruff-format` will fail on single quotes.

```python
# Correct
"name": "My Module"
"license": "LGPL-3"

# Wrong — ruff-format will rewrite these
'name': 'My Module'
'license': 'LGPL-3'
```

---

## Mandatory Manifest Fields

Every OCA module **must** include:

```python
{
    "name": "Human Readable Name",          # Title case, no "Odoo" prefix
    "version": "{odoo}.1.0.0",              # {odoo_version}.{major}.{minor}.{patch}
    "category": "Tools",                    # standard Odoo category
    "summary": "One-line description.",     # ends with period
    "author": "Author Name, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/<repo>",
    "license": "LGPL-3",                    # MANDATORY — never omit
    "depends": ["base"],
    "data": [...],
    "installable": True,
    "application": False,
    "auto_install": False,
}
```

**`license` is mandatory.** Missing license = OCA CI failure.

Accepted licenses: `LGPL-3`, `AGPL-3`, `OPL-1` (proprietary).

---

## Version Numbering

Format: `{odoo_version}.{major}.{minor}.{patch}`

- `{odoo_version}`: `16.0`, `17.0`, `18.0`, `19.0`
- Start new modules at `x.0.1.0.0`
- Breaking changes bump `major`
- New features bump `minor`
- Bug fixes bump `patch`

---

## `readme/` Directory (OCA Standard)

OCA does not maintain `README.rst` manually — it is auto-generated from `readme/` by `oca-gen-addons-table`.

Required files:

- `readme/DESCRIPTION.rst` — what the module does (2–5 sentences)
- `readme/CONTRIBUTORS.rst` — contributor names and emails

Optional files:

- `readme/INSTALL.rst` — extra installation steps (e.g., pip deps)
- `readme/CONFIGURE.rst` — post-install configuration
- `readme/USAGE.rst` — how to use the module
- `readme/ROADMAP.rst` — known limitations, future work

**For internal Trobz modules**, `readme/` is optional but `static/description/index.html` is recommended.

---

## Security File Conventions

### `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.model user,model_my_model,base.group_user,1,0,0,0
access_my_model_manager,my.model manager,model_my_model,module.group_module_manager,1,1,1,1
```

Rules:

- `id` format: `access_{model_snake}_{role}`
- `model_id:id` format: `model_{model_with_underscores}` (dots become underscores)
- Always include a base user line (read-only) and a manager line (full access)
- `perm_unlink` for users is usually `0` unless the use case requires it

### `security/security.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="module_category" model="ir.module.category">
        <field name="name">Module Category</field>
    </record>

    <record id="group_module_user" model="res.groups">
        <field name="name">User</field>
        <field name="category_id" ref="module_category"/>
    </record>

    <record id="group_module_manager" model="res.groups">
        <field name="name">Manager</field>
        <field name="category_id" ref="module_category"/>
        <field name="implied_ids" eval="[(4, ref('group_module_user'))]"/>
        <field name="users" eval="[(4, ref('base.user_root')), (4, ref('base.user_admin'))]"/>
    </record>
</odoo>
```

Use `noupdate="1"` on security records so they are not overwritten on module update.

---

## Model Conventions

### Class Structure Order

```python
class MyModel(models.Model):
    _name = "my.model"
    _description = "Human Readable Description"   # REQUIRED — no empty _description
    _inherit = []                                  # optional
    _order = "name"                               # default sort

    # Fields — in this order:
    # 1. Key fields (name, active, sequence)
    name = fields.Char(string="Name", required=True)
    active = fields.Boolean(default=True)
    # 2. Relational fields
    # 3. Computed/related fields
    # 4. State fields

    # Constraints
    # v16/17/18:
    _sql_constraints = [("name_uniq", "UNIQUE(name)", "Name must be unique.")]
    # v19:
    # _name_uniq = models.Constraint("UNIQUE(name)", "Name must be unique.")

    # CRUD overrides
    @api.model_create_multi
    def create(self, vals_list):
        ...
        return super().create(vals_list)

    def write(self, vals):
        ...
        return super().write(vals)

    # Compute methods
    @api.depends(...)
    def _compute_field(self):
        ...

    # Onchange methods
    @api.onchange(...)
    def _onchange_field(self):
        ...

    # Action methods (name starts with action_)
    def action_confirm(self):
        ...

    # Private helper methods (name starts with _)
    def _compute_something(self):
        ...
```

### Required Model Attributes

- `_name`: always set (do not rely on class name)
- `_description`: always set, non-empty
- `name` field: almost always present (used for display)

---

## XML View Conventions

### XML ID Naming

```xml
<!-- Form view -->
<record id="view_my_model_form" model="ir.ui.view">
<!-- List view -->
<record id="view_my_model_list" model="ir.ui.view">
<!-- Search view -->
<record id="view_my_model_search" model="ir.ui.view">
<!-- Action -->
<record id="action_my_model" model="ir.actions.act_window">
<!-- Menu -->
<menuitem id="menu_my_model" .../>
```

### `noupdate` Usage

- `noupdate="1"` for security records, configuration data
- `noupdate="0"` (default) for views, menus, actions

### String Translation

All `string=` attributes in XML must be in English.

---

## Pre-commit Checks (OCA standard)

OCA repos use `.pre-commit-config.yaml` with these checks:

- `prettier` — XML/JSON formatting
- `pylint-odoo` — Odoo-specific linting
- `flake8` — Python style
- `black` — Python formatting
- `isort` — Import ordering

Run after generating files if `.pre-commit-config.yaml` exists:

```bash
pre-commit run --files path/to/new/files
```
