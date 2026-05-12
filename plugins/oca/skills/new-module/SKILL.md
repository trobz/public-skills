---
name: oca:new-module
description: Scaffold a new OCA-compliant Odoo module. Use when creating a new module, initializing an addon, generating module boilerplate, or starting a new Odoo addon from scratch.
argument-hint: "<module_name> [--version <16.0|17.0|18.0|19.0>] [--path <dir>] [--app] [--no-demo] [--features <mail,sequence,portal,wizard,website>]"
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Bash(mkdir:*), Bash(ls:*), Bash(find:*), Bash(pre-commit:*), Bash(test:*)
---

# Scaffold a new OCA-compliant Odoo module

Scaffold a new Odoo module with OCA-compliant structure, version-correct syntax, and correct manifest fields. Supports versions 16.0, 17.0, 18.0, and 19.0.

## Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `<module_name>` | yes | — | Snake_case module name (e.g. `sale_custom_approval`) |
| `--version` | no | `18.0` | Odoo version: `16.0`, `17.0`, `18.0`, `19.0` |
| `--path` | no | `.` | Target directory where module folder will be created |
| `--app` | no | off | Mark as application (`application: True`), add root menu + manager group |
| `--no-demo` | no | off | Skip `demo/` directory and `demo` key in manifest |
| `--features` | no | none | Comma-separated: `mail`, `sequence`, `portal`, `wizard`, `website` |

## References

Load these during the workflow steps where noted:

- [Module Structure](plugins/oca/references/module-structure.md) — directory tree, file order, naming conventions
- [Version Matrix](plugins/oca/references/version-matrix.md) — version-specific syntax differences
- [OCA Conventions](plugins/oca/references/oca-conventions.md) — manifest rules, security patterns, model order
- [Manifest Fields](plugins/oca/references/manifest-fields.md) — complete manifest reference
- [QWeb Templates](plugins/oca/references/qweb-templates.md) — PDF report, portal, OWL component templates

## Workflow

### 1. Parse and Validate Arguments

Extract from the user's input:

- `module_name` — required
- `version` — default `18.0`
- `target_path` — default `.`
- flags: `--app`, `--no-demo`
- `features` list from `--features` value (split on `,`)

**No `module_name` provided?** Stop:
> `module_name` is required. Usage: `/odoo-dev:new-module <module_name> [--version 18.0] [--path .] [--app] [--no-demo] [--features mail,sequence]`

**Invalid module name** (not matching `^[a-z][a-z0-9_]+$`)? Stop:
> Module name `<name>` is invalid. Use snake_case only (lowercase letters, digits, underscores; must start with a letter). Example: `sale_custom_approval`.

**Invalid version** (not in `16.0`, `17.0`, `18.0`, `19.0`)? Stop:
> Version `<v>` is not supported. Supported versions: `16.0`, `17.0`, `18.0`, `19.0`.

**Invalid feature** (not in `mail`, `sequence`, `portal`, `wizard`, `website`)? Stop:
> Unknown feature `<f>`. Supported features: `mail`, `sequence`, `portal`, `wizard`, `website`.

**Target path does not exist?** Stop:
> Path `<path>` does not exist. Create it first or use a different `--path`.

**Module directory already exists?** Stop:
> Directory `<path>/<module_name>` already exists. Aborting to avoid overwriting existing code.

### 2. Load References

Load version-specific syntax rules and conventions:

- Load: `plugins/oca/references/version-matrix.md` — select the section for `version`
- Load: `plugins/oca/references/oca-conventions.md` — for manifest, security, model field ordering
- Load: `plugins/oca/references/manifest-fields.md` — for feature-specific manifest additions
- Load: `plugins/oca/references/module-structure.md` — for directory tree and file naming

Set these variables and apply them in every subsequent generation step — do not guess, always check version first:

| Variable | v16.0 | v17.0 | v18.0 | v19.0 |
|---|---|---|---|---|
| `list_tag` | `tree` | `tree` | **`list`** | **`list`** |
| `chatter_syntax` | full div | full div | **`<chatter/>`** | **`<chatter/>`** |
| `hook_signature` | `(cr)` / `(cr, registry)` | **`(env)`** | `(env)` | `(env)` |
| `attrs_allowed` | yes | **no** | no | no |
| `constraint_style` | `_sql_constraints` list | `_sql_constraints` list | `_sql_constraints` list | **named class attrs** |
| `cr_access` | `self._cr` | `self._cr` | `self._cr` | **`self.env.cr`** |

> **If version is 19.0**: `constraint_style = named class attrs`. This means zero use of `_sql_constraints`. Every SQL constraint must be a standalone class attribute: `_<name> = models.Constraint(...)`. Generating `_sql_constraints = [...]` for v19 is WRONG.
>
> **For ALL versions**: `decoration-*` attributes are NEVER placed on `<field>` elements. They belong only on `<list>`/`<tree>` for row-level decoration. Use `widget="badge"` alone on selection fields.
>
> **Search view `<group>` element**: NEVER add `expand="0"` or any other attribute to `<group>` inside `<search>`. The `expand` attribute is invalid on `<group>` in search views for ALL Odoo versions and will cause an RNG validation error. Always write plain `<group string="Group By">` with no extra attributes.

### 3. Show Plan and Confirm

Display a summary before creating anything:

```text
Scaffolding Odoo module: <module_name>
Scaffolding Odoo module: <module_name>
  Version:  <version>
  Path:     <target_path>/<module_name>/
  Features: <features or "none">
  App:      <yes/no>
  Demo:     <yes/no>

Files to create:
  __manifest__.py
  __init__.py
  models/__init__.py
  models/<module_name>.py
  security/security.xml
  security/ir.model.access.csv
  views/<module_name>_views.xml
  views/menus.xml
  tests/__init__.py
  tests/test_<module_name>.py
  [demo/demo_data.xml]                     ← unless --no-demo
  [data/sequence_data.xml]                 ← if sequence feature
  [wizard/<module_name>_wizard.py]         ← if wizard feature
  [views/<module_name>_wizard_views.xml]   ← if wizard feature
  [controllers/__init__.py + main.py]      ← if portal/website feature
  [views/<module_name>_portal_templates.xml] ← if portal feature
  readme/DESCRIPTION.rst
  readme/CONTRIBUTORS.rst
  static/description/index.html

Proceed? (yes/no)
```

Wait for user confirmation. If user says no or cancel, stop.

### 4. Create Directory Structure

```bash
mkdir -p <target_path>/<module_name>/models
mkdir -p <target_path>/<module_name>/views
mkdir -p <target_path>/<module_name>/security
mkdir -p <target_path>/<module_name>/tests
mkdir -p <target_path>/<module_name>/i18n
mkdir -p <target_path>/<module_name>/static/description
mkdir -p <target_path>/<module_name>/readme
```

If `--no-demo` not set: `mkdir -p <target_path>/<module_name>/demo`
If `sequence` feature: `mkdir -p <target_path>/<module_name>/data`
If `wizard` feature: `mkdir -p <target_path>/<module_name>/wizard`
If `portal` or `website` feature: `mkdir -p <target_path>/<module_name>/controllers`

### 5. Generate `__manifest__.py`

Use `plugins/oca/references/manifest-fields.md` to compose manifest. Apply version and feature rules:

**`depends` list:**

- Base: `["base"]`
- Add `"mail"` if `mail` feature
- Add `"portal"` if `portal` feature
- Add `"website"` if `website` feature

**`data` list** — always in load order (security before views, data before wizard views):

```python
"data": [
    "security/security.xml",
    "security/ir.model.access.csv",
    "views/<module_name>_views.xml",
    "views/menus.xml",
],
```

If `sequence` feature: append `"data/sequence_data.xml"` after the menus line.
If `wizard` feature: append `"views/<module_name>_wizard_views.xml"` at the end.
If `portal` feature: append `"views/<module_name>_portal_templates.xml"` at the end.

**`demo` key:** omit entirely if `--no-demo`.

**`application`:** `True` if `--app`, else `False`.

**`assets`:** omit unless `website` or `portal` features add frontend assets.

### 6. Generate `__init__.py` (root)

```python
from . import models
# from . import controllers  ← if portal/website feature
# from . import wizard        ← if wizard feature
```

If hooks needed (only add if user's module specifically requires init logic — do NOT add empty hooks):

```python
# v16 hook signature:
def post_init_hook(cr, registry):
    pass

# v17+ hook signature:
def post_init_hook(env):
    pass
```

Do NOT add empty hooks by default. Only add if user explicitly requested hooks via `--features` that require them.

### 7. Generate `models/__init__.py`

```python
from . import <module_name>
```

### 8. Generate `models/<module_name>.py`

Apply version-specific syntax from the version matrix.

**`readonly` rule (v17+):** Never set `readonly=True` on regular model fields — it breaks Odoo's import tool. Set `readonly` only in the view. Exception: `TransientModel` (wizard) fields.

- System-set fields (e.g., a date stamped by an action): define them without `readonly`, then set `readonly="True"` on the `<field>` in the form view.
- Computed stored fields (`compute=..., store=True`) are implicitly readonly — no need to declare it.

**Base model (all versions):**

```python
from odoo import api, fields, models


class <ModelClass>(models.Model):
    _name = "<dot.notation.name>"
    _description = "<Human Readable Description>"
    _order = "name"

    name = fields.Char(string="Name", required=True)
    active = fields.Boolean(default=True)
    note = fields.Text(string="Notes")

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)
```

**With `mail` feature:** add to class:

```python
    _inherit = ["mail.thread", "mail.activity.mixin"]
    # Add tracking to key fields:
    name = fields.Char(string="Name", required=True, tracking=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("done", "Done"),
        ("cancelled", "Cancelled"),
    ], default="draft", tracking=True)
```

**With `sequence` feature:** add to class:

```python
    reference = fields.Char(string="Reference", copy=False, default="New")
    # readonly is set in the view, not here — model-level readonly breaks Odoo import

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = self.env["ir.sequence"].next_by_code(
                    "<module_name>.sequence"
                ) or "New"
        return super().create(vals_list)
```

**Constraint naming:** format `_<fields>_<rule>` — derive names from the actual columns involved, not from examples.

- `uniq` suffix → UNIQUE constraint. `check` suffix → CHECK constraint.
- Derive from real fields: `_name_uniq`, `_name_company_uniq`, `_score_positive_check`, `_date_start_end_check`.

**Check `constraint_style` variable from Step 2, then apply exactly one of the two patterns below:**

**If `constraint_style` is `_sql_constraints` (v16/17/18):**

```python
    _sql_constraints = [
        ("name_company_uniq", "UNIQUE(name, company_id)", "Name must be unique per company."),
        ("score_positive_check", "CHECK(score >= 0)", "Score must be non-negative."),
    ]
```

**If `constraint_style` is `named class attrs` (v19 ONLY):** write each constraint as an independent class attribute — no list, no `_sql_constraints`:

```python
    _name_company_uniq = models.Constraint("UNIQUE(name, company_id)", "Name must be unique per company.")
    _score_positive_check = models.Constraint("CHECK(score >= 0)", "Score must be non-negative.")
```

Writing `_sql_constraints = [...]` when `constraint_style` is `named class attrs` is an error that will crash Odoo with a registry warning.

**`_compute_display_name` (v17+, replaces name_get):**

```python
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.name
```

### 9. Generate `security/security.xml`

Derive security group names from module name. Use `noupdate="1"`.

**Without `--app`:** minimal group (manager only):

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="group_<module_name>_manager" model="res.groups">
        <field name="name">Manager</field>
        <!-- base.module_category_hidden hides the group from Settings > Users UI -->
        <field name="category_id" ref="base.module_category_hidden"/>
        <field name="users" eval="[(4, ref('base.user_root')), (4, ref('base.user_admin'))]"/>
    </record>
</odoo>
```

**With `--app`:** full category + user + manager hierarchy:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="module_category_<module_name>" model="ir.module.category">
        <field name="name"><ModuleName></field>
        <field name="sequence">100</field>
    </record>

    <record id="group_<module_name>_user" model="res.groups">
        <field name="name">User</field>
        <field name="category_id" ref="module_category_<module_name>"/>
        <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
    </record>

    <record id="group_<module_name>_manager" model="res.groups">
        <field name="name">Manager</field>
        <field name="category_id" ref="module_category_<module_name>"/>
        <field name="implied_ids" eval="[(4, ref('group_<module_name>_user'))]"/>
        <field name="users" eval="[(4, ref('base.user_root')), (4, ref('base.user_admin'))]"/>
    </record>
</odoo>
```

### 10. Generate `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_<module_model>_user,<module_name>.model user,model_<module_model>,base.group_user,1,0,0,0
access_<module_model>_manager,<module_name>.model manager,model_<module_model>,<module_name>.group_<module_name>_manager,1,1,1,1
```

Where `<module_model>` = module `_name` with dots replaced by underscores.

### 11. Generate Views

#### `views/<module_name>_views.xml`

Apply version-specific tags (list_tag, chatter_syntax from step 2).

**Visibility/conditions:**

- v16.0: `attrs="{'invisible': [('state', '=', 'done')]}"` is still valid, but write new code using the inline style
- v17.0+: `attrs` is removed — use `invisible="state == 'done'"` directly

Always use the inline style for new scaffolded code regardless of version (pre-commit will validate).

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Form View -->
    <record id="view_<module_model>_form" model="ir.ui.view">
        <field name="name"><module_name>.form</field>
        <field name="model"><dot.notation.name></field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <!-- state buttons here if mail feature -->
                    <!-- Example: <button name="action_confirm" string="Confirm"
                                          type="object" class="btn-primary"
                                          invisible="state != 'draft'"/> -->
                </header>
                <sheet>
                    <div class="oe_title">
                        <h1>
                            <field name="name" placeholder="Name..."/>
                        </h1>
                    </div>
                    <group>
                        <group>
                            <!-- left column fields -->
                        </group>
                        <group>
                            <!-- right column fields -->
                        </group>
                    </group>
                </sheet>
                <!-- CHATTER:
                     v16/17: <div class="oe_chatter">
                                 <field name="message_follower_ids"/>
                                 <field name="activity_ids"/>
                                 <field name="message_ids"/>
                             </div>
                     v18/19: <chatter/>
                -->
                <!-- [insert chatter_syntax here] -->
            </form>
        </field>
    </record>

**List view rules — apply before writing the XML:**
- Tag: use `<list_tag>` variable from Step 2 (`tree` for v16/17, `list` for v18/19)
- `decoration-*` attributes (e.g. `decoration-success`, `decoration-muted`) go ONLY on the `<list>`/`<tree>` opening tag for row-level styling. They are NEVER valid on individual `<field>` elements — Odoo RNG will reject the view.
- For `state` or selection fields: use `widget="badge"` with NO `decoration-*` on the field.

```xml
    <!-- List View -->
    <record id="view_<module_model>_list" model="ir.ui.view">
        <field name="name"><module_name>.list</field>
        <field name="model"><dot.notation.name></field>
        <field name="arch" type="xml">
            <<list_tag> decoration-muted="active == False">
                <field name="name"/>
                <field name="state" widget="badge"/>
            </<list_tag>>
        </field>
    </record>
</record>

```xml
<!-- Search View -->
<record id="view_<module_model>_search" model="ir.ui.view">
    <field name="name"><module_name>.search</field>
    <field name="model"><dot.notation.name></field>
    <field name="arch" type="xml">
        <search>
            <field name="name"/>
            <separator/>
            <filter name="active" string="Active" domain="[('active', '=', True)]"/>
            <group string="Group By">
                <filter name="group_by_state" string="State" context="{'group_by': 'state'}"/>
            </group>
        </search>
    </field>
</record>
```

```xml
<!-- Action — view_mode uses "tree" for v16/17, "list" for v18/19 -->

<record id="action_<module_model>" model="ir.actions.act_window">
    <field name="name"><ModelName></field>
    <field name="res_model"><dot.notation.name></field>
    <field name="view_mode"><list_tag>,form</field>
</record>
</odoo>
```

#### `views/menus.xml`

**Without `--app`:** submenu only (user must adapt parent):

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem
        id="menu_<module_model>_list"
        name="<ModelName>"
        action="action_<module_model>"
        parent="PARENT_MENU_ID"
        sequence="10"/>
</odoo>
```

**With `--app`:** full menu hierarchy:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem
        id="menu_<module_name>_root"
        name="<ModuleName>"
        sequence="100"
        groups="<module_name>.group_<module_name>_user"/>

    <menuitem
        id="menu_<module_name>_main"
        name="<ModuleName>"
        parent="menu_<module_name>_root"
        sequence="10"/>

    <menuitem
        id="menu_<module_model>_list"
        name="<ModelName>"
        parent="menu_<module_name>_main"
        action="action_<module_model>"
        sequence="10"/>
</odoo>
```

### 12. Generate `tests/`

#### `tests/__init__.py`

```python
from . import test_<module_name>
```

#### `tests/test_<module_name>.py`

```python
from odoo.tests.common import TransactionCase


class Test<ModelClass>(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = cls.env["<dot.notation.name>"]

    def test_create(self):
        record = self.model.create({"name": "Test Record"})
        self.assertTrue(record.id)
        self.assertEqual(record.name, "Test Record")

    def test_active_default(self):
        record = self.model.create({"name": "Active Test"})
        self.assertTrue(record.active)
```

### 13. Generate Optional Feature Files

#### If `sequence` feature — `data/sequence_data.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="sequence_<module_name>" model="ir.sequence">
        <field name="name"><ModuleName> Reference</field>
        <field name="code"><module_name>.sequence</field>
        <field name="prefix">MOD/%(year)s/</field>
        <field name="padding">4</field>
        <field name="company_id" eval="False"/>
    </record>
</odoo>
```

#### If `wizard` feature — `wizard/__init__.py` + `wizard/<module_name>_wizard.py`

`wizard/__init__.py`:

```python
from . import <module_name>_wizard
```

`wizard/<module_name>_wizard.py`:

```python
from odoo import fields, models


class <ModelClass>Wizard(models.TransientModel):
    _name = "<dot.notation.name>.wizard"
    _description = "<ModelClass> Wizard"

    <module_name>_id = fields.Many2one("<dot.notation.name>", string="<ModelName>", required=True)
    note = fields.Text(string="Notes")

    def action_confirm(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window_close"}
```

Also create `views/<module_name>_wizard_views.xml` (always in `views/`, not in `wizard/`):

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_<module_model>_wizard_form" model="ir.ui.view">
        <field name="name"><module_name>.wizard.form</field>
        <field name="model"><dot.notation.name>.wizard</field>
        <field name="arch" type="xml">
            <form>
                <group>
                    <field name="<module_name>_id"/>
                    <field name="note"/>
                </group>
                <footer>
                    <button name="action_confirm" string="Confirm" type="object" class="btn-primary"/>
                    <button string="Cancel" class="btn-secondary" special="cancel"/>
                </footer>
            </form>
        </field>
    </record>
</odoo>
```

#### If `portal` or `website` feature — `controllers/__init__.py` + `controllers/main.py`

`controllers/__init__.py`:

```python
from . import main
```

For `portal` and `website` features: **load `plugins/oca/references/qweb-templates.md`** and use the templates defined there:

- `portal` feature → use the **"Portal Template"** section (controller + list template + portal home counter)
- `website` feature → use the **"OWL Component / website controller"** section

The portal controller must subclass `CustomerPortal` (not `http.Controller`) and include `_prepare_home_portal_values` for the portal home page count. Create both the controller and the `views/<module_name>_portal_templates.xml` template file.

Note for v19: JSON routes use `type="jsonrpc"` instead of `type="json"`. HTTP routes always stay `type="http"`.

#### If `demo` enabled — `demo/demo_data.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="demo_<module_model>_1" model="<dot.notation.name>">
        <field name="name">Demo Record 1</field>
    </record>
    <record id="demo_<module_model>_2" model="<dot.notation.name>">
        <field name="name">Demo Record 2</field>
    </record>
</odoo>
```

### 14. Generate `readme/` Files

#### `readme/DESCRIPTION.rst`

```rst
<ModuleName>
============

This module provides [description of what the module does].

Features:
- [Key feature 1]
- [Key feature 2]
```

#### `readme/CONTRIBUTORS.rst`

```rst
Contributors
============

* [Author Name] <email@example.com>
```

#### `static/description/index.html` (stub)

```html
<section class="oe_container">
    <div class="oe_row oe_spaced">
        <h2 class="oe_slogan"><MODULE_NAME></h2>
        <h3 class="oe_slogan">Short description of this module.</h3>
    </div>
</section>
```

### 15. Pre-commit Check

Check if `.pre-commit-config.yaml` exists in the project root or parent directories:

```bash
find . -maxdepth 3 -name ".pre-commit-config.yaml" -type f
```

If found, run pre-commit on all generated files:

```bash
pre-commit run --files $(find <target_path>/<module_name> -type f | tr '\n' ' ')
```

Fix any formatting issues raised by pre-commit before reporting completion.

### 16. Report Results

Display the final directory tree using `find` or `ls -R`, then show next steps:

```text
Module `<module_name>` created at `<target_path>/<module_name>/`

  <module_name>/
  ├── __manifest__.py
  ├── __init__.py
  ├── models/
  │   ├── __init__.py
  │   └── <module_name>.py
  ├── security/
  │   ├── security.xml
  │   └── ir.model.access.csv
  ├── views/
  │   ├── <module_name>_views.xml
  │   └── menus.xml
  ├── tests/
  │   ├── __init__.py
  │   └── test_<module_name>.py
  └── readme/
      ├── DESCRIPTION.rst
      └── CONTRIBUTORS.rst

Next steps:
  1. Review `views/menus.xml` — set the correct parent menu ID
  2. Plan features: /odoo-dev:plan "describe your feature" (if using plans)
  3. Install: odoo-v{major} -d <db> -i <module_name> --stop-after-init
  4. Test: odoo-v{major} -d <db> --test-tags /<module_name> --stop-after-init

Adding features to this module? The planning and code skills automatically
use the same Odoo references (version-matrix, oca-conventions, qweb-templates)
so version-correct syntax is applied consistently across scaffold → plan → code.
Examples:
  - Add a SQL constraint:   /odoo-dev:plan "add uniqueness constraint on name+company to <module_name>"
  - Add a custom widget:    /odoo-dev:plan "add custom OWL badge component for score field in <module_name>"
  - Add a portal page:      /odoo-dev:plan "expose <module_name> records to portal users"
```

## Error Handling

- **Directory already exists**: Stop immediately. Never overwrite existing code.
- **Invalid module name**: Stop with validation message before creating anything.
- **`pre-commit` not found**: Warn that pre-commit is not installed, but do not fail the scaffold.
- **Pre-commit failures**: Show the errors and fix them automatically if they are formatting-only (black, isort, prettier). Warn about pylint/flake8 issues and leave them for the user.
- **Permission denied on target path**: Stop and tell user to check directory permissions.

## Updating Reference Docs

The references in this skill may become outdated as new Odoo versions are released. To update:

- OCA conventions and migration notes: use `/odoo-docs:update-migration-docs` if available
- For manual updates, fetch from:
  - OCA contributing: <https://github.com/OCA/odoo-community.org/blob/master/website/Contribution/CONTRIBUTING.rst>
  - OCA migration notes: <https://github.com/OCA/maintainer-tools/wiki/Migration-to-version-{version}>
  - Odoo coding guidelines: <https://www.odoo.com/documentation/{version}/contributing/development/coding_guidelines.html>
