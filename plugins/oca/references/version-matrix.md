# Odoo Version Matrix for Module Scaffolding

Reference for version-specific syntax differences when scaffolding modules.
Load the section matching the target version during file generation.

> **String quoting**: All Python code examples use **double quotes**. OCA repos
> enforce this via `ruff-format` in their pre-commit hooks (not stated explicitly
> in the style guide but applied automatically).

---

## v16.0 Baseline

### Views (v16.0)

- List view tag: `<tree>`
- Chatter: `<div class="oe_chatter"><field name="message_follower_ids"/><field name="activity_ids"/><field name="message_ids"/></div>`
- Conditional visibility: both old `attrs` **and** new `invisible="..."` are valid in 16.0

  ```xml
  <!-- attrs style — still valid in 16.0 -->
  <field name="partner_id" attrs="{'invisible': [('state', '=', 'done')]}"/>
  <!-- new inline style — also valid, preferred for new code -->
  <field name="partner_id" invisible="state == 'done'"/>
  ```

- Assets: use `"assets"` dict in manifest (NOT old XML `<template inherit_id="web.assets_backend">`)
- QWeb expressions: `t-out` preferred; `t-esc` deprecated but still works; `t-raw` deprecated

### Models (v16.0)

- `create()`: always decorate with `@api.model_create_multi`
- `name_get()`: still works but deprecated — prefer `_compute_display_name`
- `_sql_constraints`: OK
- `self._cr`, `self._uid`: OK
- `groups_id`: OK

### JavaScript (v16.0)

- Module header: `/** @odoo-module */` **required** at top of each JS file

### Manifest (v16.0)

```python
"version": "16.0.1.0.0",
"license": "LGPL-3",
```

### Hooks (`__init__.py`) (v16.0)

```python
def pre_init_hook(cr):
    pass

def post_init_hook(cr, registry):
    pass
```

---

## v17.0 Differences from v16.0

### Views (v17.0)

- `attrs` and `states` attributes **removed** (OCA migration note references PR #104741):

  ```xml
  <!-- WRONG in v17+ -->
  <field name="partner_id" attrs="{'invisible': [('state', '=', 'done')]}"/>
  <!-- CORRECT in v17+ — direct Python expression -->
  <field name="partner_id" invisible="state == 'done'"/>
  ```

  Supported direct attributes: `invisible`, `required`, `readonly`, `column_invisible`

- **`decoration-*` only valid on `<list>`/`<tree>` element, never on `<field>`** — row-level decoration goes on the list tag; individual field decoration is not supported by the RNG schema:

  ```xml
  <!-- CORRECT: row-level decoration on <list> -->
  <list decoration-muted="state == 'cancelled'" decoration-success="state == 'done'">

  <!-- CORRECT: badge widget without decoration attributes -->
  <field name="state" widget="badge"/>

  <!-- WRONG: decoration-* on <field> — fails RNG validation -->
  <!-- <field name="state" widget="badge" decoration-secondary="state == 'draft'"/> -->
  ```

- **`column_invisible` replaces static `invisible="1"` on list/tree columns** — In v17+, hiding an entire column in a `<tree>`/`<list>` view uses `column_invisible` instead of `invisible="1"`:

  ```xml
  <!-- WRONG in v17+ for hiding a full column -->
  <field name="partner_id" invisible="1"/>

  <!-- CORRECT in v17+ -->
  <field name="partner_id" column_invisible="1"/>
  ```

  In XML view attributes, `"1"` and `"True"` are interchangeable for boolean-true; `"0"` and `"False"` for boolean-false. Both forms are valid across all versions.

  `column_invisible` is evaluated at **view/column level**, not per-row. It supports:
  - Static values: `column_invisible="1"` / `column_invisible="True"` (both equivalent)
  - **`context`**: `column_invisible="context.get('default_res_model') != 'hr.employee'"`
  - **`parent`** (for One2many line columns): `column_invisible="parent.move_type == 'entry' or parent.state != 'posted'"`

  It does **not** support per-row record field expressions (those belong in `invisible`).

- **`readonly=True` on model fields: avoid** — `readonly=True` at model level blocks Odoo's import tool. Define `readonly` on views instead.

  ```python
  # WRONG for regular models — breaks import
  state = fields.Selection(..., readonly=True)

  # CORRECT — set readonly on the view field
  # <field name="state" readonly="state == 'done'"/>
  ```

  Exception: `TransientModel` (wizard) fields may keep `readonly=True` at model level since wizards are not importable.

### Models (v17.0)

- `name_get()`: deprecated — use `_compute_display_name`:

  ```python
  def _compute_display_name(self):
      for record in self:
          record.display_name = record.name
  ```

### JavaScript (v17.0)

- Module header: `/** @odoo-module */` **still required** in 17.0
- OWL component `owl="1"` attribute removed from templates

### Manifest (v17.0)

```python
"version": "17.0.1.0.0",
```

### Hooks (`__init__.py`) (v17.0)

```python
def pre_init_hook(env):
    pass

def post_init_hook(env):
    pass
```

---

## v18.0 Differences from v17.0

### Views (v18.0)

- List view tag: **`<list>`** (NOT `<tree>`)
- Chatter: **`<chatter/>`** (NOT the full div block)

  ```xml
  <!-- v18+ -->
  <chatter/>
  ```

### Models (v18.0)

- `user_has_groups("module.group")` → **`self.env.user.has_group("module.group")`**
- `check_access_rights("read")` → **`check_access("read")`**
- `_filter_access_rules(records, "read")` → **`records._filtered_access("read")`**
- Field attribute `group_operator="sum"` → **`aggregator="sum"`**
- Non-stored computed field `search` method must return a `Domain` object (not a list)

### JavaScript (v18.0)

- `/** @odoo-module */` header can be **removed** (PR #142858 — ES module auto-detection)

### Manifest (v18.0)

```python
"version": "18.0.1.0.0",
```

### Hooks (v18.0) — same signature as v17.0: `(env)`

---

## v19.0 Differences from v18.0

### Views (v19.0)

- List view tag: `<list>` (same as 18.0)
- Chatter: `<chatter/>` (same as 18.0)

### Models (v19.0)

- `groups_id` field → **`group_ids`**:

  ```python
  # v19
  group_ids = fields.Many2many("res.groups")
  ```

- `_sql_constraints` → **named class-level attributes** using `models.Constraint` or `models.Index`:

  ```python
  # v19 — each constraint/index is a named class attribute (format: _<fields>_<rule>)
  _name_company_uniq = models.Constraint("UNIQUE(name, company_id)", "Name must be unique per company.")
  _score_positive_check = models.Constraint("CHECK(score >= 0)", "Score must be non-negative.")
  _partner_model_idx = models.Index("(partner_id, res_model)")
  _name_active_uniq = models.UniqueIndex("(name) WHERE active IS TRUE")

  # WRONG — _constraints list is the old @api.constrains mechanism, raises warning:
  # _constraints = [models.Constraint(...)]
  ```

  Note: `models.Index` replaces multi-column/conditional indexes that were previously defined
  in `_sql_constraints` or `_auto_init`/`init` methods. It does **not** replace the simple
  `index=True` attribute on individual fields — that remains a valid separate mechanism.
- `self._cr` → **`self.env.cr`**
- `self._uid` → **`self.env.uid`**
- `name_search(name, args, operator, limit)` → **`name_search(name, domain, operator, limit)`**
- `toggle_active()` → **`action_archive()` / `action_unarchive()`**
- `@ormcache_context` → **`@ormcache`**
- `odoo.osv.expression` → **`odoo.fields.Domain`**
- `read_group()` → **`_read_group()` or `formatted_read_group()`**

### Controllers (v19.0)

- Route `type="json"` → **`type="jsonrpc"`** (HTTP routes keep `type="http"`):

  ```python
  @http.route("/my/route", type="jsonrpc", auth="user")
  ```

### Manifest (v19.0)

```python
"version": "19.0.1.0.0",
```

### Hooks (v19.0) — same signature as v17.0/v18.0: `(env)`

---

## Quick Comparison Table

| Feature | v16.0 | v17.0 | v18.0 | v19.0 |
|---|---|---|---|---|
| List view tag | `<tree>` | `<tree>` | `<list>` | `<list>` |
| Chatter | full div | full div | `<chatter/>` | `<chatter/>` |
| `attrs` / `states` on views | valid | **removed** | removed | removed |
| `decoration-*` on `<field>` | invalid | invalid | invalid | invalid |
| `decoration-*` on `<list>`/`<tree>` | OK | OK | OK | OK |
| `expand` attr on `<group>` in search | **invalid** | **invalid** | **invalid** | **invalid** |
| `invisible="1"` on list column | OK | → `column_invisible="1"` | same | same |
| `readonly=True` on model field | OK | **avoid** (breaks import) | same | same |
| `readonly=True` on TransientModel | OK | OK | OK | OK |
| JS `@odoo-module` header | required | required | **can remove** | not needed |
| `name_get()` | deprecated → prefer `_compute_display_name` | same | same | same |
| `_sql_constraints` | OK | OK | OK | → `models.Constraint` |
| `self._cr` / `self._uid` | OK | OK | OK | → `self.env.cr/uid` |
| `groups_id` | OK | OK | OK | → `group_ids` |
| `user_has_groups()` | OK | OK | → `env.user.has_group()` | same |
| `check_access_rights()` | OK | OK | → `check_access()` | same |
| `group_operator` attr | OK | OK | → `aggregator` | same |
| Route `type="json"` | OK | OK | OK | → `type="jsonrpc"` |
| Hook signature | `(cr)` / `(cr, registry)` | `(env)` | `(env)` | `(env)` |
| `toggle_active()` | OK | OK | OK | → `action_archive/unarchive` |
| `read_group()` | OK | OK | OK | → `_read_group()` |
| `odoo.osv.expression` | OK | OK | OK | → `odoo.fields.Domain` |
| `@ormcache_context` | OK | OK | OK | → `@ormcache` |
| OWL `owl="1"` template attr | OK | **removed** | removed | removed |
