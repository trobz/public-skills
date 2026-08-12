---
name: odooly
description: Inspect and query data on Odoo objects using the odooly CLI. Use when the user mentions odooly explicitly, asks to connect to an Odoo instance/environment, or asks to query, inspect, search, read, list, or fetch data from an Odoo database. Also use when the user asks to copy product images between Odoo instances, to list installed/available modules from an instance or environment, to compare access rights/permissions/security groups between two Odoo instances, or to turn an access rights diff into an HTML report. Trigger phrases include "connect to instance X", "in instance X list/show/find ...", "on ENV check ...", "query ENV for ...", "copy product images between X and Y", "sync images from X to Y", "list modules on ENV", "show installed modules in X", "which modules are installed on Y", "list modules from instance Z", "compare access rights between X and Y", "diff ACLs/permissions between X and Y", "what group permissions changed between env A and env B", "check if roles are consistent across instances", "generate an HTML report of the access rights diff", "make this diff into a report per user", "show roles assigned and group changes per user".
allowed-tools: Bash(odooly:*), Bash(python*:*), Question
---

<!-- markdownlint-disable MD024 -->

# Odooly Skill

Query and inspect data on Odoo objects using the `odooly` CLI.

## Command Usage

```text
/odoo:odooly [query description or model name]
```

**Parameters:**

- `$ARGUMENTS`: Free-text description of what to query, or a model name directly.

## Configuration

- `odooly` must be available in `$PATH`
- Configuration file: `~/odooly.ini`
- Use `--env` to select a specific environment section from the config

### List available environments

```bash
odooly -c ~/odooly.ini --list
```

### odooly.ini Configuration File Format

The `~/odooly.ini` file uses INI format with one section per Odoo instance/environment. Each section defines the connection parameters for that environment.

**Example `~/odooly.ini`:**

```ini
[staging]
scheme = https
host = HTTP_AUTH_USER:HTTP_AUTH_PASSWORD@project-staging.trobz.com
port = 443
username = admin
password = ADMIN_PASSWORD
database = project_staging
protocol = jsonrpc

[production]
scheme = https
host = HTTP_AUTH_USER:HTTP_AUTH_PASSWORD@project-production.trobz.com
port = 443
username = admin
password = ADMIN_PASSWORD
database = project_production
protocol = jsonrpc
```

**Configuration Parameters:**

| Parameter | Description | Example |
|-----------|-------------|---------|
| `scheme` | Connection protocol | `https` or `http` |
| `host` | Odoo server hostname (may include HTTP auth) | `user:pass@odoo.example.com` |
| `port` | Server port | `443` (HTTPS), `8069` (local Odoo) |
| `username` | Odoo username | `admin` |
| `password` | Odoo user password or API key | `your_password` |
| `database` | Database name | `company_production` |
| `protocol` | Odoo RPC protocol | `jsonrpc` (standard) |

**Notes:**

- The section name (e.g., `[staging]`, `[production]`) is the environment name used with `--env`
- For Odoo.sh or instances with HTTP authentication, include credentials in the `host` field
- Keep `~/odooly.ini` secure as it contains sensitive credentials

## Workflow

### 1. Understand the Request

- If `$ARGUMENTS` is provided, parse it to determine the target model, fields, and search criteria.
- Otherwise, ask the user what they want to query using the `Question` tool.

### 2. Determine the Environment

The user may refer to an environment/instance using various phrasings:

- "connect to **production** and list partners"
- "in instance **staging** show sale orders"
- "on **demo** find products"
- "query **prod** for invoices"

Extract the environment name from these patterns and use `--env <section>`.

- If the user specifies an environment/instance name, use `--env <section>`.
- If unsure which environments exist or the name doesn't match, list them first:

  ```bash
  odooly -c ~/odooly.ini --list
  ```

- If only one environment exists or the user doesn't specify, omit `--env`.

### 3. Build the Odooly Command

Construct the command using these parameters:

| Flag | Purpose | Example |
|------|---------|---------|
| `-c ~/odooly.ini` | Config file | Always include |
| `--env ENV` | Environment section | `--env production` |
| `-m MODEL` | Odoo model to query | `-m res.partner` |
| `-f FIELD` | Fields to return (repeatable) | `-f name -f email` |
| `-v` | Verbose output | Add when user wants details |

**Search terms and domains** are passed as positional arguments after the options.

### 4. Command Patterns

**Search by term:**

```bash
odooly -c ~/odooly.ini -m res.partner -f name -f email "John"
```

**Search by ID:**

```bash
odooly -c ~/odooly.ini -m res.partner -f name -f email 42
```

**Search by domain (Odoo domain syntax):**

```bash
odooly -c ~/odooly.ini -m sale.order -f name -f state -f partner_id "state=sale"
```

**Multiple search terms:**

```bash
odooly -c ~/odooly.ini -m res.partner -f name "is_company=True" "country_id.code=VN"
```

**List all fields of a model (verbose, no filter):**

```bash
odooly -c ~/odooly.ini -m res.partner -v
```

**Query a specific instance/environment:**

```bash
# "connect to production and list partners"
odooly -c ~/odooly.ini --env production -m res.partner -f name -f email

# "in instance staging show sale orders in state done"
odooly -c ~/odooly.ini --env staging -m sale.order -f name -f state "state=done"
```

**Interactive session:**

```bash
# Running odooly with no query positional args drops into an interactive REPL
odooly -c ~/odooly.ini --env production
```

### 5. Execute and Report

- Run the constructed command.
- Present the results to the user in a readable format.
- If the command fails, check:
  - Is `odooly` installed? (`which odooly`)
  - Does `~/odooly.ini` exist?
  - Is the environment section valid? (`odooly -c ~/odooly.ini --list`)

## Model Name Mapping

When the user refers to Odoo concepts in natural language, map them to the correct model:

| User says | Model |
|-----------|-------|
| partners, contacts, customers | `res.partner` |
| users | `res.users` |
| products | `product.product` |
| product templates | `product.template` |
| sale orders, sales, quotations | `sale.order` |
| sale order lines | `sale.order.line` |
| purchase orders | `purchase.order` |
| invoices, bills | `account.move` |
| invoice lines | `account.move.line` |
| employees | `hr.employee` |
| leads, opportunities | `crm.lead` |
| projects | `project.project` |
| tasks | `project.task` |
| stock moves | `stock.move` |
| pickings, transfers | `stock.picking` |
| companies | `res.company` |
| currencies | `res.currency` |
| countries | `res.country` |

## Important Guidelines

- Always include `-c ~/odooly.ini` in every command.
- Use `-f` to restrict output to relevant fields only; avoid dumping all fields unless the user asks for it.
- When the user asks for a specific record by name, pass the name as a positional search term.
- When the user asks for records matching conditions, translate to Odoo domain syntax as positional arguments (e.g. `"state=done"` `"partner_id.name=Trobz"`).
- For numeric IDs, pass them directly as positional arguments.
- Present command to the user before executing so they can confirm or adjust.

## List Modules from an Instance

When the user asks to list modules from an Odoo instance or environment (e.g. "list installed modules on production", "which modules are on staging", "show me the modules from instance X"), use the bundled script at `scripts/list_modules.py` (relative to this skill's directory). **Do not use plain `odooly` commands for this — always use `list_modules.py`.**

### Usage

```bash
python scripts/list_modules.py -c ~/odooly.ini --env ENV [OPTIONS]
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `-c`, `--config` | Config file path | `odooly.ini` |
| `--env` | Environment name (required) | — |
| `--installed` / `--no-installed` | Filter installed modules only | `--installed` |
| `--include-core` | Include core CE/EE modules | `False` |
| `--format table\|csv` | Output format | `table` |
| `--columns` | Comma-separated columns to display | `module,state,repo,description` |
| `--project-dir` | Local project dir for repo detection and CLOC | — |

**Available columns:** `module`, `state`, `repo`, `description`, `version`, `author`, `website`, `cloc`

### Workflow

1. Extract the environment name from the user's request.
2. If unsure which environments exist, list them first: `odooly -c ~/odooly.ini --list`
3. Run the script with sensible defaults (installed non-core modules in table format).
4. If the user wants core modules too, add `--include-core`.
5. If the user wants CSV output or specific columns, adjust `--format` and `--columns`.
6. If the user provides a local project directory, pass `--project-dir` to get repo detection and CLOC counts.

### Examples

```bash
# List installed non-core modules (default)
python scripts/list_modules.py -c ~/odooly.ini --env production

# Include core Odoo CE/EE modules
python scripts/list_modules.py -c ~/odooly.ini --env staging --include-core

# All modules regardless of install state
python scripts/list_modules.py -c ~/odooly.ini --env production --no-installed

# CSV output with version info
python scripts/list_modules.py -c ~/odooly.ini --env production --format csv --columns module,version,state

# With repo detection and CLOC from local project
python scripts/list_modules.py -c ~/odooly.ini --env production --project-dir ~/code/myproject --format csv --columns repo,module,version,cloc
```

## Compare Access Rights Between Two Instances

When the user asks to compare access rights, permissions, or security configuration between two Odoo instances (e.g. "compare access rights between 2 envs", "diff ACLs between X and Y", "what group permissions changed between env A and env B", "check if roles are consistent across instances"), use the bundled script at `scripts/compare_access_rights.py` (relative to this skill's directory). **Do not use plain `odooly` commands for this — always use `compare_access_rights.py`.**

The script compares 5 kinds of access-rights data between two environments:

- `access` — `ir.model.access` (ACL: read/write/create/unlink per model+group)
- `rule` — `ir.rule` (record rules / domains)
- `groups` — `res.groups` (the groups themselves: name, category)
- `users` — `res.users.groups_id` (which internal, non-share user belongs to which groups)
- `roles` — `res.users.role.line` (OCA `base_user_role`, if installed; silently skipped if the model doesn't exist on an environment)

Records are matched between the two environments by **XML ID** first (falling back to a natural key — e.g. group `full_name`, user `login` — when no XML ID exists on either side), never by raw database `id`, since the two environments are normally independent databases where numeric ids don't correspond to the same record.

The `users` type's `groups` field lists each group as `[xml_id] Display Name` (bare `Display Name` when no xml_id resolves) rather than just the display text - `generate_html_report.py`'s `--known-list` matching relies on this to look up a purpose by the group's real, stable xml_id instead of by display text alone (see its docs below for why that matters).

### Usage

```bash
python scripts/compare_access_rights.py -c ~/odooly.ini --env-a ENV_A --env-b ENV_B [OPTIONS]
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `-c`, `--config` | Config file path | `odooly.ini` |
| `--env-a` | First environment (required) | — |
| `--env-b` | Second environment (required) | — |
| `--types` | Comma-separated subset: `access,rule,groups,users,roles` | all 5 |
| `--model` | Restrict `access`/`rule` comparison to one model (technical name) | — |
| `--include-core` | Include ACL/rules belonging to core CE/EE modules | excluded by default |
| `--format table\|csv` | Output format | `table` |
| `--full` | Also show fields that are identical, not just differences | differences only |
| `--output` | Write output to a file instead of stdout | — |

### Workflow

1. Extract the two environment names from the user's request.
2. If unsure which environments exist, list them first: `odooly -c ~/odooly.ini --list`
3. Run with sensible defaults (all 5 types, core modules excluded, differences only).
4. If the user only cares about one kind (e.g. "just compare the groups"), narrow with `--types`.
5. If the user wants to include Odoo's own core ACL/rules (rare — usually noise when the two environments run different Odoo versions), add `--include-core`.
6. For large result sets, suggest `--format csv --output <file>` so the user can filter/sort in a spreadsheet.

### Examples

```bash
# Compare everything between two environments (differences only)
python scripts/compare_access_rights.py -c ~/odooly.ini --env-a ENV_A --env-b ENV_B

# Only compare groups
python scripts/compare_access_rights.py -c ~/odooly.ini --env-a ENV_A --env-b ENV_B --types groups

# Only ACL and record rules for one model
python scripts/compare_access_rights.py -c ~/odooly.ini --env-a ENV_A --env-b ENV_B \
  --types access,rule --model sale.order

# Full CSV export (including identical fields) for offline review
python scripts/compare_access_rights.py -c ~/odooly.ini --env-a ENV_A --env-b ENV_B \
  --format csv --full --output /tmp/access_rights_diff.csv
```

## Generate an HTML Report from an Access Rights Diff

When the user asks for a visual/HTML report of an access rights comparison (e.g. "make this into an HTML report", "generate a report I can send to the coop", "show the diff per user with roles and groups"), use the bundled script at `scripts/generate_html_report.py` (relative to this skill's directory) on the CSV produced by `compare_access_rights.py`. **Do not hand-roll HTML from the CSV — always use `generate_html_report.py`.**

The report shows, per user with a changed group membership, two boxes:

- **Roles assigned** — OCA `base_user_role` roles (`res.users.role.line`) enabled for that user in env B (the "after" side), from the CSV's `roles` rows.
- **Consequence on groups (diff)** — the added/removed `res.groups`, from the CSV's `users`/`groups` rows.
- **Groups unchanged** — every group present on both sides, listed below the diff in its own collapsed panel (closed by default, since it's usually much longer than the diff itself) so a reviewer validating the full access picture doesn't have to cross-reference env A and env B by hand.

Users that exist in only one of the two environments (`missing_in_a`/`missing_in_b` on the `users` `(record)` rows — e.g. an account created or archived between the two envs) are **not** shown as a fake "N → 0 groups" change; they're listed separately in a collapsed "excluded" note, since that's an account-lifecycle fact, not a role/group diff.

**Pass `--known-list` (repeatable) whenever the diff spans different Odoo versions, or when the project has its own custom/OCA groups** — e.g. comparing a v12 instance against its v18 migration target, which is exactly the case that makes a plain add/remove diff misleading. Pass the sibling `access-rights-groups` skill's `known_groups.yaml` (native groups) and, if the project has one, a project-local custom-groups purpose file (e.g. Foodcoop's `data/access-rights-groups.yaml`, drafted via `access-rights-groups`' `write_project_group_purposes.py`) - both at once, `--known-list a.yaml --known-list b.yaml`. With it, the report:

- Adds a purpose tooltip to every group shown, sourced from whichever file(s) documented it.
- Folds a group Odoo itself renamed across versions (sourced from `resolve_renames.py`'s OpenUpgrade data) into a single "Renamed by Odoo, not an access change" entry, instead of showing it as one group lost + one unrelated group gained.
- Flags a removed group that Odoo itself dropped at a given version (sourced from `detect_removed_groups.py`'s `removed_in`) with a small badge, so it doesn't read as an unexplained access change.

Matching prefers each group's **xml_id** when the CSV has one - `compare_access_rights.py` embeds it as `[xml_id] Display Name` per group entry (falls back to bare `Display Name` for a group with no resolvable xml_id, or when reading an older CSV from before this). xml_id is a real, stable identifier - unlike display text, which can be translated, customized per project, or coincide between two completely unrelated groups (a native group's historical display name and a project's own custom group happening to share the same bare name - a real case: Superquinquin's own `Accountant` role group collided with `account.group_account_manager`'s old display text). Only when no xml_id is available does it fall back to (category, name) text matching: each file's `name`/`category` fields are normalized the same way regardless of which convention produced them (split, like `known_groups.yaml`, or combined "Category / Name", like some older project-local files) - see `bare_name()` - and `category` is matched case/whitespace-insensitively (see `normalize_category()`). On a group documented in more than one file, the first `--known-list` that has it wins - pass the native catalog first, project-local files after.

Without `--known-list` the report renders exactly as before - this is additive, never required.

### Usage

```bash
# 1. Export the diff as CSV
python scripts/compare_access_rights.py -c ~/odooly.ini --env-a ENV_A --env-b ENV_B \
  --format csv --output /tmp/diff.csv

# 2. Render it as HTML
python scripts/generate_html_report.py --input /tmp/diff.csv --output /tmp/report.html \
  --env-a ENV_A --env-b ENV_B --title "Coop Name - Role Migration Diff"

# 2b. Same, but annotated with purposes/renames/removals from the shared known-group catalog
# (use when ENV_A and ENV_B are different Odoo versions)
python scripts/generate_html_report.py --input /tmp/diff.csv --output /tmp/report.html \
  --env-a ENV_A --env-b ENV_B --title "Coop Name - v12 to v18 Diff" \
  --known-list ../../access-rights-groups/scripts/known_groups.yaml

# 2c. Also annotate the project's own custom/OCA groups (repeat --known-list)
python scripts/generate_html_report.py --input /tmp/diff.csv --output /tmp/report.html \
  --env-a ENV_A --env-b ENV_B --title "Coop Name - v12 to v18 Diff" \
  --known-list ../../access-rights-groups/scripts/known_groups.yaml \
  --known-list /path/to/project/data/access-rights-groups.yaml
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `--input` | CSV produced by `compare_access_rights.py --format csv` (required) | — |
| `--output` | Path to write the HTML report to (required) | — |
| `--title` | Report title | `Access Rights Diff` |
| `--env-a` / `--env-b` | Labels for the two environments shown in the meta line | `env A (before)` / `env B (after)` |
| `--group-sep` | Separator used to split the `users`/`groups` CSV field back into a list | `" \| "` (must match `GROUP_LIST_SEP` in `compare_access_rights.py`) |
| `--known-list` | Access-rights-groups-style YAML to annotate with - **repeatable**, merges purpose tooltips, renames, and removed-group badges from every file passed | off (report renders unannotated) |

### Workflow

1. Run `compare_access_rights.py` with `--format csv --output <file>` to get the raw diff (all 5 types, so both `users`/`groups` and `roles` rows are present — narrowing `--types` to exclude `users` or `roles` will leave one of the two report boxes empty).
2. Run `generate_html_report.py` on that CSV with `--env-a`/`--env-b`/`--title` set to something meaningful for the coop/instance pair being compared. Add `--known-list` (repeatable) when the two environments are on different Odoo versions or the project has its own documented custom groups.
3. Open the resulting HTML file (or hand it to the user) — it's self-contained (inline CSS, no external assets) and adapts to light/dark mode.
4. If the terminal output mentions excluded users (present in only one environment), mention this to the user — it usually means an account was created or archived between the two environments, not a role change; those users can be reviewed/deactivated manually if needed.

## Copy Product Images Between Instances

When the user asks to copy product images between two Odoo instances (e.g. "copy product images between instance X and instance Y"), use the bundled script at `scripts/copy_product_images.py` (relative to this skill's directory).

### Usage

```bash
python scripts/copy_product_images.py -c ~/odooly.ini --env-from SOURCE_ENV --env-to DEST_ENV [OPTIONS]
```

### Options

| Flag | Purpose | Example |
|------|---------|---------|
| `-c`, `--config` | Config file path (default: odooly.ini) | `-c ~/odooly.ini` |
| `--env-from` | Source environment (required) | `--env-from production` |
| `--env-to` | Destination environment (required) | `--env-to staging` |
| `--product-template-id` | Copy a single product by ID | `--product-template-id 42` |
| `--domain` | Custom domain filter as JSON | `--domain '[["categ_id.name", "=", "Furniture"]]'` |
| `--dry-run` | Preview what would be copied | `--dry-run` |

### Workflow

1. Extract the source and destination environment names from the user's request.
2. If unsure which environments exist, list them first: `odooly -c ~/odooly.ini --list`
3. Always run with `--dry-run` first and show the summary to the user.
4. After user confirmation, run without `--dry-run` to perform the actual copy.

### Examples

```bash
# Dry-run: preview copying all images from production to staging
python scripts/copy_product_images.py -c ~/odooly.ini --env-from production --env-to staging --dry-run

# Copy all product images
python scripts/copy_product_images.py -c ~/odooly.ini --env-from production --env-to staging

# Copy a single product image
python scripts/copy_product_images.py -c ~/odooly.ini --env-from production --env-to staging --product-template-id 42

# Copy with a custom domain filter
python scripts/copy_product_images.py -c ~/odooly.ini --env-from production --env-to staging --domain '[["categ_id.name", "=", "Furniture"]]'
```
