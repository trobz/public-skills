---
name: list-users
description: List Odoo users from a live instance, defaulting to active users that currently hold at least one enabled role from the OCA base_user_role module. Use when the user asks to list users, show who has a role, audit who is missing a role, or check active/archived user counts on an Odoo environment. Trigger phrases include "list users on ENV", "list me all users from environment ENV", "who has a role on ENV", "show active users with a role", "list users without a role", "which users are archived on ENV", "who's missing a role on ENV", "show every user on ENV". Generic across every Odoo project - not specific to any one client.
allowed-tools: Bash(python*:*), Bash(uv:*)
---

<!-- markdownlint-disable MD024 -->

# List Users Skill

List Odoo users from a live instance via `odooly`, defaulting to **active users that
currently hold at least one enabled role** from the OCA `base_user_role` module - the
population the roles model actually governs, not every user in the database.

## Mental model

- Two independent filters, on by default, each a plain switch: `active=True` (an
  archived user isn't using anything) and "has a currently-enabled `base_user_role`
  role" (a user with no role isn't managed by the roles model at all). Neither is
  hardcoded - pass `--include-inactive` and/or `--include-no-role` for the fuller
  picture, e.g. auditing exactly who is *missing* a role before a migration.
- "Currently-enabled" is a real distinction, not a synonym for "has a role assigned
  ever": a `res.users.role.line` can carry From/To dates (see the sibling
  `access-rights-groups` skill's playbook docs for how a progressive rollout uses
  this), so a role assigned for a future date, or one that already lapsed, does not
  count as currently held. This script reads the real `is_enabled` computed value per
  record rather than trusting a search domain on it - a domain on `is_enabled`
  silently returns every record, not just the enabled ones (verified firsthand).
- If `base_user_role` isn't installed on the target environment, the script says so
  and stops, rather than silently reporting "0 users" as if that were a real answer
  about the population - pass `--include-no-role` to list users anyway.

## `scripts/list_users.py` - list users, active + role-holders by default

### Usage

```bash
python scripts/list_users.py -c ~/odooly.ini --env ENV [OPTIONS]
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `-c`, `--config` | Odooly config file | `odooly.ini` |
| `--env` | Odooly environment name (required) | - |
| `--include-inactive` | Include archived (`active=False`) users too | off (active only) |
| `--include-no-role` | Include users with no currently-enabled role too | off (role-holders only) |
| `--format` | `table` or `csv` | `table` |
| `--columns` | Comma-separated columns to display | `login,name,roles` |
| `--output` | Write output to a file instead of stdout | - |

**Available columns:** `login`, `name`, `email`, `active`, `roles` (joined with ` \| `
when a user holds more than one enabled role), `groups` (every `res.groups` the user
belongs to, joined with ` \| ` - the actual access, not just the role label).

### How it works

- Reads `res.users.role.line`, keeping only rows whose `is_enabled` is `True` right
  now, and groups the role names by `user_id`.
- `--include-inactive` explicitly disables Odoo's own implicit `active=True` filter
  via `with_context(active_test=False)` - an empty search domain alone does **not**
  disable it, that's an ORM default independent of what domain you pass.
- With neither override flag, the base population is `active=True` users, further
  narrowed to only those present in the enabled-roles map built above.
- If `res.users.role.line` doesn't exist at all (module not installed), the script
  errors out with a clear message unless `--include-no-role` was passed, in which case
  it proceeds with an empty roles map (every user's `roles` column reads blank).
- `groups` only reads and resolves `res.groups` for the users actually being shown
  (after the active/role filtering above), and only when the column is actually
  requested - a user can belong to dozens of groups, no point paying for that
  resolution for a population it'll never be displayed for.

### Examples

```bash
# Active users with a currently-enabled role (default)
python scripts/list_users.py -c ~/odooly.ini --env production

# Everyone active, role or not - e.g. to find who's missing one before a rollout
python scripts/list_users.py -c ~/odooly.ini --env production --include-no-role

# Absolutely everyone, active or archived, role or not
python scripts/list_users.py -c ~/odooly.ini --env production --include-inactive --include-no-role

# CSV with email and active state, written to a file
python scripts/list_users.py -c ~/odooly.ini --env production \
    --format csv --columns login,email,active,roles --output /tmp/users.csv

# CSV including each user's actual res.groups, not just their role
python scripts/list_users.py -c ~/odooly.ini --env production \
    --format csv --columns login,name,roles,groups --output /tmp/users.csv
```

## Workflow

1. If unsure which environments exist, list them first: `odooly -c ~/odooly.ini --list`
2. Plain listing (no flags): active users holding a currently-enabled role - the
   population most requests actually mean by "who has a role".
3. If the request explicitly says **all** users (e.g. "list me all users from
   environment ENV", "show every user on ENV"), that means the full population, not
   the default filtered one - pass both `--include-inactive --include-no-role`. Don't
   silently apply the defaults when the user's own wording already said "all".
4. Auditing gaps before or during a roles rollout (see the sibling
   `access-rights-groups` skill's playbook docs): add `--include-no-role` and diff
   the result against the full active-user list to see who still needs a role
   assigned.
5. Archived-account cleanup or historical audits: add `--include-inactive`.
6. Turning the list into something to hand someone (not a terminal table): `--format csv
   --output users.csv`, then `generate_users_report.py --input users.csv --output
   report.html` - see below. This skill's own report, separate from the sibling
   `odooly` skill's access-rights diff report - different skills, different reports,
   not one bolted onto the other.

## `scripts/generate_users_report.py` - render a list_users.py CSV as a standalone HTML report

A separate script from `list_users.py` on purpose, mirroring the sibling `odooly`
skill's own split between fetching data (`compare_access_rights.py`) and rendering it
(`generate_html_report.py`): one script talks to the live instance, this one only ever
reads a CSV already on disk.

### Usage

```bash
python scripts/list_users.py -c ~/odooly.ini --env ENV --format csv --columns login,name,roles,groups --output /tmp/users.csv
python scripts/generate_users_report.py --input /tmp/users.csv --output /tmp/report.html --env ENV \
    --purposes ../access-rights-groups/scripts/known_groups.yaml
```

### Getting purposes for a project's own custom groups

`known_groups.yaml` only ever tracks native Odoo groups - a project's own custom
groups (an OCA module's or, e.g., a Foodcoop-specific group like "BDM Users / BDM
Lecture") have no source that skill can read, so they'd otherwise show up in the
report as plain chips with no tooltip. The sibling `access-rights-groups` skill's
`write_project_group_purposes.py` fills that gap mechanically, from the same
`ir.model.access` + menu evidence a human would read to write one by hand:

```bash
cd ../access-rights-groups/scripts
python discover_groups.py -c ~/odooly.ini --env ENV --all --evidence --format yaml \
    > /tmp/evidence.yaml
python write_project_group_purposes.py --evidence /tmp/evidence.yaml \
    --known-list /path/to/project_group_purposes.yaml
cd ../../list-users/scripts
python generate_users_report.py --input /tmp/users.csv --output /tmp/report.html --env ENV \
    --purposes ../../access-rights-groups/scripts/known_groups.yaml \
    --purposes /path/to/project_group_purposes.yaml
```

The generated purpose text is a literal bullet list of the models/menus the evidence
found - never an inferred guess about what the group is "for" - and re-running
`write_project_group_purposes.py` never overwrites a purpose someone has since
hand-edited into that file.

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `--input` | CSV produced by `list_users.py --format csv` (required) | - |
| `--output` | Path to write the HTML report to (required) | - |
| `--title` | Report title | `Users Report` |
| `--env` | Environment label shown in the meta line - cosmetic only, doesn't reconnect to anything | - |
| `--purposes` | A `known_groups.yaml`-shaped purposes file. Repeatable - pass once per source to merge | - (chips render without tooltips) |

### How it works

- Renders whatever columns the input CSV happens to have (works with any `--columns`
  `list_users.py` was run with) as a sortable-by-eye table. `roles` renders as chips
  inline. `groups` renders collapsed by default behind a "N groups" toggle in its
  column - clicking it (JS class toggle, not a native `<details>`) reveals a
  **separate, full-width row** directly below that user's row, spanning every column,
  with one chip per group. A user can belong to dozens of groups; squeezing that many
  chips into one narrow table column wraps each chip's own text instead of wrapping
  between chips (confirmed unreadable on real data), and even a column-confined
  `<details>` expansion still overflows/gets cut off next to a narrow column - a
  colspan'd row below is the only layout that gives the group list real width to wrap
  into. The toggle itself is a `▸` that rotates 90° via CSS `transform` when open,
  rather than swapping to a different glyph. When open, the toggle's own table cell
  and the expanded row below share matching background/border and rounded corners
  (top corners on the cell, bottom corners on the row, no border between them) so they
  read as one continuous panel dropping out of the toggle rather than two disconnected
  pieces.
- With one or more `--purposes FILE`, each group chip whose full_name matches an entry
  gets a native `title` tooltip with that group's plain-language purpose (e.g.
  "Enables analytic accounting ...") - this is the thing to give a Foodcoop-style
  admin so they can spot "why does this user have that access" without leaving the
  report. Matching is by reconstructing "category / name" (and each `also_category` x
  `also_named` variant) from the YAML and comparing against the chip's own text - the
  same string Odoo computes for `res.groups.full_name` - so no xml_id plumbing is
  needed in `list_users.py` itself. `--purposes` is repeatable so native and
  project-custom sources merge into one lookup - see the workflow below. A group in
  neither file just renders as a plain chip, no tooltip; that's a coverage gap to fill,
  not an error. This is the one place this skill reads another skill's data file -
  deliberately via a CLI path, not a Python import, so `list-users` still runs
  standalone without it.
- A plain-text filter box (client-side JS, no server, no network call) narrows the
  table by login/name/role/group as you type - meant for a report someone opens once
  and scans, not a live query tool. A match inside a row's group list still counts
  toward showing that row, but filtering never changes a row's expand/collapse
  state either way - it only shows or hides rows.
- Self-contained: inline CSS and JS, no external assets, adapts to light/dark mode.
  Hand the file to anyone, it works standalone.
