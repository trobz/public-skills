---
name: access-rights-groups
description: Generate an exhaustive, purpose-documented list of Odoo Access Rights groups (res.groups). Use when the user asks to list/document/catalog Odoo security groups, access rights groups, or roles; to explain what a group grants; to compare a project's groups against the native Odoo catalog; or to produce a roles/permissions page for a minisite or client documentation. Trigger phrases include "list all access rights groups", "document Odoo security groups", "generate a roles page", "what does group X do", "catalog of Odoo permissions/roles", "sync known groups against instance X", "which native groups exist in Odoo 18". This skill is generic across ALL Odoo projects - a specific client's roles page (e.g. Foodcoop) is just one downstream consumer of its output, not its scope.
allowed-tools: Bash(python*:*), Bash(uv:*), Bash(git:*)
---

<!-- markdownlint-disable MD024 -->

# Access Rights Groups Skill

Generate and maintain an exhaustive catalog of Odoo `res.groups` ("Access Rights
groups" - the role concept, not `ir.model.access` ACL rows) with a plain-language
purpose for each, reusable across every Odoo project. There is no official Odoo or
OCA list of all native groups - Odoo defines them as data scattered across every
module, so this skill builds and maintains one.

## Files

| File | Role |
|------|------|
| `scripts/known_groups.yaml` | The maintained "known list": every native group discovered so far, keyed by XML ID, with purpose text and which Odoo series confirmed it (`versions_seen`). Version-controlled in this repo - it accumulates across every project/version this skill is ever run against. |
| `scripts/extract_native_groups.py` | Refreshes the known list from local Odoo Community/Enterprise **source** (read-only, across any git branch) - the exhaustive, version-aware pass. |
| `scripts/discover_groups.py` | Queries `res.groups` on **one live instance** via `odooly` - the ground-truth pass for what a specific project actually has installed. |
| `scripts/resolve_renames.py` | Links known-list entries that are actually the same group renamed across versions, sourced from OCA OpenUpgrade's migration data (never guessed from name similarity). |
| `scripts/detect_removed_groups.py` | Marks known-list entries confirmed removed (not renamed) by a real Odoo upgrade log, from any project. |
| `scripts/write_project_group_purposes.py` | Writes purpose text for a project's own custom/OCA groups from `discover_groups.py --evidence` output - mechanically summarized facts only, never overwrites a purpose already set. |
| `scripts/generate_roles_doc.py` | Renders the known list (or a live project's groups) into CSV / Markdown / Excel. |

## Mental model

- `known_groups.yaml` is a **purpose dictionary** that grows over time ("enrich
  through the years") - it is never the source of truth for "does this group exist on
  my project". It only answers "what does this group generally do".
- "Which groups actually exist" is always answered by a live query
  (`discover_groups.py`) or, for the exhaustive native catalog, by reading Odoo source
  directly (`extract_native_groups.py`) - never by assuming the known list is complete
  or version-correct for any one instance.
- `versions_seen` on each entry records which Odoo series confirmed that group, so the
  list stays honest about groups that don't exist in every version.
- `removed_in` records versions where a real upgrade log confirmed the group was
  deleted (not renamed) - this is empirical evidence from one real run, not a global
  fact, so it's a list you add to over time as more real logs are checked, never a
  claim that the group is gone everywhere.
- The known list only ever grows (`--sync-known-list` adds/flags, never deletes or
  overwrites a hand-written purpose) - each run against a new project/version adds
  value for every future user of this skill.

## Workflow

1. **(Occasional maintenance) Refresh the native catalog from source** - run this when
   a new Odoo version ships, or the known list feels stale. Requires local CE/EE
   checkouts, one per version, kept up to date by `tlc pull-repos`
   ([trobz/local.py](https://github.com/trobz/local.py)) - this skill only reads them.
2. **(Per project) Discover what's actually installed** - run `discover_groups.py`
   against the project's `odooly`-configured environment, optionally with
   `--sync-known-list` to feed newly-seen native groups back into the known list.
3. **(Opportunistic) Link renames and removals when a real upgrade happens** - a
   project's own version upgrade is a good moment to run `resolve_renames.py` (once)
   and, if you have the upgrade's server log handy, `detect_removed_groups.py` against
   it - both only add evidence, never required before generating a doc.
4. **Fill in `TODO: describe purpose` entries** - hand-write or ask Claude to draft
   plain-language purposes for groups the known list doesn't have one for yet. Never
   required before generating a doc (missing purposes just render as
   "(purpose not documented yet)" for a live project, or "TODO..." in the raw known
   list) but doing this is the actual "enrichment".
5. **Generate the doc** - `generate_roles_doc.py`, in whichever format the destination
   needs (CSV for a spreadsheet, Markdown to paste into a Hugo minisite page such as
   `features/roles/`, Excel for a client deliverable).
6. **Commit `known_groups.yaml` back to this repo** (`public-skills`) - this is what
   turns a one-off run into "enrich through the years": every project/version anyone
   runs this skill against compounds into the same shared file.

## `scripts/extract_native_groups.py` - refresh the native catalog from source

### Usage

```bash
python scripts/extract_native_groups.py \
    --refs 12.0,13.0,14.0,15.0,16.0,17.0,18.0,19.0 \
    --known-list scripts/known_groups.yaml
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `--ce-base` | Base directory holding one Odoo Community checkout per version (`<ce-base>/<version>`) | `~/code/odoo/odoo` |
| `--ee-base` | Base directory holding one Odoo Enterprise checkout per version (`<ee-base>/<version>`) - optional, skipped silently per-version (or entirely) if missing | `~/code/odoo/enterprise` |
| `--refs` | Comma-separated Odoo series to scan, each resolved as `<base>/<version>` | `18.0` |
| `--known-list` | `known_groups.yaml` to merge results into (created if missing) | - |
| `--dry-run` | Print the diff summary without writing | off |

**Deliberately does no cloning of its own.** `tlc pull-repos`
([trobz/local.py](https://github.com/trobz/local.py)) already clones and keeps one
checkout per version up to date at exactly this layout (`~/code/odoo/odoo/<version>`,
`~/code/odoo/enterprise/<version>`), including re-fetching on every run - reimplementing
that here would just be a second, redundant cloning mechanism. So this script assumes
the checkout is already there and reads it directly (plain filesystem reads, no git
subprocess at all): a version whose directory doesn't exist under `--ce-base` is
skipped with a warning (pointing at `tlc pull-repos`) rather than failing the whole
run; a missing `--ee-base`/`<version>` (Enterprise access is optional/private) is
skipped silently. Verified: scanning a real local `18.0` checkout finds exactly the
177 groups already on record for that series in `known_groups.yaml`, in ~3s.

### How it works

- Plain filesystem walk (`pathlib.rglob`) over each version's checkout - no git
  involved, since `tlc` already keeps that checkout current and dedicated to this
  purpose (reset on every pull, not shared with other work).
- Parses `<record model="res.groups">` blocks across all matching XML files, merging
  fields across the (often multiple) blocks that progressively define the same
  group's `id` - this is how Odoo's own data files are structured.
- Classifies each group `community` vs `enterprise` by which repo's addon directory
  actually owns its module (not by which repo happened to touch it - Enterprise demo
  data commonly extends Community's `base` groups).
- Resolves `category_id` first via static `ir.module.category` XML records, falling
  back to reading the owning module's `__manifest__.py` `category` field (e.g.
  `"Sales/Sales"`, `"Inventory/Purchase"`) for the many categories Odoo creates at
  runtime rather than declaring in XML.
- Skips `test_*` modules (Odoo's own test-suite fixtures, never installed on a real
  database).
- `comment` (Odoo's own group description field, when set) seeds `purpose`
  automatically; it's frequently empty on core groups, so most entries still need
  manual enrichment.
- `name` reflects the **last** version in `--refs` (pass versions ascending so it's
  actually the latest wording). When a group's own display name changes across
  versions - independent of its xml_id, e.g. Odoo 19.0 renamed `base.group_user`'s
  `name` field itself to `"Role / User"` - the older text is preserved in
  `also_named` rather than silently overwritten; `generate_html_report.py` (sibling
  `odooly` skill) matches against every name in `also_named` too, so an instance not
  yet on that version still resolves to the right purpose.
- Only ever **adds** entries, **appends** to `versions_seen`/`also_named`, or updates
  `name` to the latest-scanned text; never deletes a known entry or overwrites an
  existing `purpose`.

## `scripts/discover_groups.py` - live discovery on one project

### Usage

```bash
python scripts/discover_groups.py -c ~/odooly.ini --env ENV [--all] [--format table|csv|yaml]
python scripts/discover_groups.py -c ~/odooly.ini --env ENV --sync-known-list scripts/known_groups.yaml [--dry-run]
python scripts/discover_groups.py -c ~/odooly.ini --env ENV --all --evidence --format yaml
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `-c`, `--config` | Odooly config file | `odooly.ini` |
| `--env` | Odooly environment name (required) | - |
| `--all` | Include custom/OCA groups too | native CE/EE only |
| `--format` | `table`, `csv`, or `yaml` | `table` |
| `--sync-known-list` | Merge discovered native groups into this `known_groups.yaml` | - |
| `--dry-run` | With `--sync-known-list`, print the diff without writing | off |
| `--evidence` | Also fetch `ir.model.access` (which models, which permissions) and menu entries gated by each group | off |

### Workflow

1. If unsure which environments exist, list them first: `odooly -c ~/odooly.ini --list`
2. Plain discovery (no sync): shows what's on that instance, tagged
   community/enterprise/custom via the same `manifestoo_core` classification
   `compare_access_rights.py` (in the sibling `odooly` skill) already uses.
3. With `--sync-known-list`: merges native groups into the known list (adds new ones,
   appends the instance's Odoo series to `versions_seen`), and prints which known-list
   entries were **not** found live - usually just "module not installed here", not
   evidence the group was removed from Odoo.
4. With `--evidence` (usually combined with `--all --format yaml`): for a project's own
   custom/OCA groups - which have no source this skill can read the way
   `extract_native_groups.py` reads Odoo core - this is the only way to find out what a
   group actually grants. It lists the models each group has ACL entries on (with
   read/write/create/unlink flags) and which menus it gates, giving enough to write an
   accurate purpose for a project-specific group. This does not write a purpose itself,
   and project-specific groups never go into `known_groups.yaml` (that file is native
   groups only) - write their purposes into a project-local file instead.

## `scripts/resolve_renames.py` - link renamed groups across versions

Odoo occasionally renames a group's XML ID across versions (e.g.
`sale.group_delivery_invoice_address` became `account.group_delivery_invoice_address`
in 16.0). Without linking, a rename just looks like two unrelated entries whose
`versions_seen` happen to be adjacent and non-overlapping - which is also true of
plenty of *unrelated* groups (this known list has many groups that legitimately
share a short name like "Administrator" or "User" across different categories), so
guessing renames from name-matching would produce false positives.

Instead this reads [OCA OpenUpgrade](https://github.com/OCA/OpenUpgrade)'s actual
migration scripts - the code Odoo/OCA run to migrate real production databases,
which explicitly declares rename pairs (commonly a `_xmlids_renames = [(old, new),
...]` list feeding `openupgrade.rename_xmlids()`) so that a database's own
customizations keep working across the rename. That's sourced fact, not inference.

### Usage

```bash
python scripts/resolve_renames.py \
    --refs 12.0,13.0,14.0,15.0,16.0,17.0,18.0,19.0 \
    --known-list scripts/known_groups.yaml [--dry-run]
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `--openupgrade-base` | Base directory holding one OCA/OpenUpgrade checkout per target version (`<openupgrade-base>/<version>/openupgrade`) | `~/code/oca` |
| `--refs` | Comma-separated OpenUpgrade **target-version** branches to scan (OpenUpgrade branches migrations *to* that version) | `12.0,13.0,14.0,15.0,16.0,17.0,18.0,19.0` |
| `--known-list` | `known_groups.yaml` to link renames in (required) | - |
| `--dry-run` | Print what would be linked without writing | off |

**Deliberately does no cloning of its own** - same reasoning as `extract_native_groups.py`
above: `tlc pull-repos` ([trobz/local.py](https://github.com/trobz/local.py)) already
clones and keeps every version's OpenUpgrade checkout up to date at exactly this layout,
so reimplementing that here would just be a second, redundant cloning mechanism. This
script assumes the checkout is already there and reads it directly - plain filesystem
reads, no git subprocess at all. A version with no local checkout is skipped with a
warning (pointing at `tlc pull-repos`) rather than failing the whole run. Verified
against a real checkout: same 29 rename pairs found (1 involving a known group) as the
previous git-based implementation.

### How it works

- Plain filesystem walk (`pathlib.rglob`) over each version's checkout - no git
  involved, since `tlc` already keeps that checkout current and dedicated to this
  purpose.
- Parses every migration script mentioning a rename call - both the common
  `_xmlids_renames = [...]` variable pattern (name varies across authors, matched
  loosely) and direct `rename_xmlid(s)(...)` calls with literal arguments.
- Keeps only pairs where **at least one side is already a known `res.groups` xml_id**
  in `known_groups.yaml` - a rename pair where neither side is a known group almost
  certainly belongs to some other model (a view, a report, a menu item, ...).
- Adds `renamed_to` / `renamed_from` on the linked entries - lists of
  `{xml_id, version}` (never bare xml_id strings), since a group can be renamed more
  than once across the version range, and the version it happened at matters (e.g.
  `product.group_discount_per_so_line` and `sale.group_discount_per_so_line` were
  renamed into each other twice, at 13.0 and again at 18.0 - meaningless without the
  version on each link). `version` is the OpenUpgrade target-version branch the rename
  was found on (a rename found on branch "16.0" happened going into 16.0). Never
  removes an entry or overwrites its `purpose`.
- If only one side of a pair is a known group, it's reported but skipped rather than
  guessed at - the missing side may be a different model, or a native group this
  skill hasn't discovered yet (run `extract_native_groups.py` again with a wider
  `--refs` first).

## `scripts/detect_removed_groups.py` - mark groups confirmed removed by a real upgrade

Odoo's own module-update/upgrade process (independent of OpenUpgrade) logs every
`res.groups` record it deletes because the newer version no longer declares it, in the
standard form:

```text
odoo.addons.base.models.ir_model: Deleting <id>@res.groups (<xml_id>)
```

This is a genuine removal, not a rename - the group's function is gone in the newer
version, not renamed to something else. Point this script at a local copy of any real
Odoo upgrade log (any project, any version - nothing here depends on how one specific
project's infrastructure is set up) to extract those lines and mark the matching
known-list entries.

### Usage

```bash
python scripts/detect_removed_groups.py \
    --log ~/logs/upgrade_17.0.log --version 17.0 \
    --known-list scripts/known_groups.yaml [--dry-run]
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `--log` | Local Odoo upgrade/update log file to scan (required) | - |
| `--version` | Odoo series this log run upgraded **into** (required) | - |
| `--known-list` | `known_groups.yaml` to annotate (required) | - |
| `--dry-run` | Print what would be marked without writing | off |
| `--force` | Proceed even if `--version` disagrees with the log's own version hints (default: abort) | off |

### How it works

- Regex-extracts every `Deleting <id>@res.groups (<xml_id>)` line - `xml_id` only, the
  numeric id alone is useless for matching against the known list.
- Only annotates `xml_id`s **already present** in `known_groups.yaml` - same principle
  as `resolve_renames.py`: this never invents a new group entry from a log line alone,
  since a log by itself gives no purpose, category, or module classification to work
  with. A deleted `xml_id` not yet in the known list is reported, not guessed at.
- Appends to `removed_in` (never overwrites or removes an existing entry) - a group can
  be confirmed removed by more than one project's log over time.
- Unlike `resolve_renames.py`'s OpenUpgrade source (authoritative - what module authors
  declared should happen everywhere), a log is **empirical evidence from one real run**:
  a genuine deletion on that run, but not proof the group is gone for every
  installation (the same log pattern would also appear if a module simply wasn't
  installed there). Treat `removed_in` as "confirmed removed by at least one real run",
  not "removed for everyone".
- `--version` is trusted input (no single log field reliably names "the version this run
  upgraded into"), but cross-checked on a best-effort basis against two hints when
  present: Odoo's own startup banner (`Odoo version X`, printed by every real Odoo
  server) and a `NN.0`-shaped substring in the log filename. Absence of a hint is never
  treated as a mismatch - but when a hint IS there and disagrees, the run **aborts**
  before touching `known_groups.yaml` (exit code 1), since silently writing `removed_in`
  under the wrong version is exactly the kind of mistake this check exists to catch.
  Pass `--force` to proceed anyway once you've confirmed by hand which version is
  actually right.

## `scripts/write_project_group_purposes.py` - write purposes for a project's custom groups

`discover_groups.py --evidence` gets you the raw ACL/menu evidence for a project's own
custom/OCA groups (they have no source to read, unlike native groups). This script takes
that evidence and mechanically writes a purpose sentence from it directly - every
sentence only states real model/menu names the evidence actually contains, never an
inferred guess about what the group is "for" in plain language. An entry that already
has a `purpose` is left untouched, so re-running after a later `--evidence` refresh
never overwrites something already there (hand-edited or previously written).

### Usage

```bash
python scripts/discover_groups.py -c ~/odooly.ini --env ENV --all --evidence \
    --format yaml > /tmp/evidence.yaml
python scripts/write_project_group_purposes.py \
    --evidence /tmp/evidence.yaml --known-list project_groups.yaml
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `--evidence` | YAML from `discover_groups.py --all --evidence --format yaml` (required) | - |
| `--known-list` | Project-local known_groups.yaml-shaped file to write purposes into (created if missing, merged if it exists) | - |
| `--only-custom` | Only write for `origin: custom` groups - native groups belong in `known_groups.yaml`, sourced from CE/EE instead | on |

### How it works

- Groups access evidence by permission level (`rwcu`, `r`, ...) and lists the models under
  each, plus any menus the group gates - the same summary a human would build by hand
  before writing a purpose.
- Uses the **same schema as `known_groups.yaml`** (`name`/`category` as separate fields,
  never combined) - deliberately, so the output can be pointed at directly by
  `generate_html_report.py`'s `--known-list` (in the sibling `odooly` skill) without an
  adapter.
- Re-running never overwrites an entry that already has a `purpose` - safe to re-run
  after every `--evidence` refresh.
- A group with no access rows and no menus at all is still recorded (name/category/module),
  just with no `purpose` - nothing to summarize from.
- Project-local output only - **never** written into the shared `known_groups.yaml` (that
  file is native groups only, same rule as everywhere else in this skill).

## `scripts/generate_roles_doc.py` - render the final doc

### Usage

```bash
# Reference doc from the known list alone (no live instance needed):
python scripts/generate_roles_doc.py --known-list scripts/known_groups.yaml --output roles.csv
python scripts/generate_roles_doc.py --known-list scripts/known_groups.yaml --format md --output roles.md
python scripts/generate_roles_doc.py --known-list scripts/known_groups.yaml --format table --output roles.xlsx

# Doc for one real project (live groups, purposes looked up from the known list):
python scripts/generate_roles_doc.py --known-list scripts/known_groups.yaml \
    -c ~/odooly.ini --env ENV --include-project-groups --format md --output roles.md
```

### Options

| Flag | Purpose | Default |
|------|---------|---------|
| `--known-list` | `known_groups.yaml` to render (required) | - |
| `-c`, `--config` | Odooly config file (only used with `--env`) | `odooly.ini` |
| `--env` | Render this project's live groups instead of the raw known list | - |
| `--include-project-groups` | With `--env`, also include the project's own custom/OCA groups | native only |
| `--odoo-series` | Without `--env`, only include entries seen in this series (e.g. `18.0`) | all |
| `--format` | `csv` (default), `md` (Markdown table), `table` (`.xlsx`) | `csv` |
| `--output` | Output file. Required for `--format table`; stdout otherwise for csv/md | - |

### Two source modes

- **With `--env`** (recommended for a real deliverable, e.g. Foodcoop's roles page):
  output = exactly the groups live on that project (correct for its Odoo version and
  installed modules). The known list is only consulted for purpose text; a live group
  without a documented purpose yet shows `(purpose not documented yet)` instead of
  being silently dropped.
- **Without `--env`** (generic reference / "what native groups exist at all"): output =
  the full known list, with a `versions_seen` column so readers see which Odoo series
  confirmed each group. Narrow with `--odoo-series`.

Always grouped by category. `--format table` requires the `openpyxl` dependency
(already declared in `scripts/pyproject.toml`).

## Example: building Foodcoop's roles page

```bash
python scripts/discover_groups.py -c ~/odooly.ini --env foodcoop_production --sync-known-list scripts/known_groups.yaml
# ... fill in any new TODO purposes surfaced above ...
python scripts/generate_roles_doc.py --known-list scripts/known_groups.yaml \
    -c ~/odooly.ini --env foodcoop_production --include-project-groups \
    --format md --output foodcoop_roles.md
# paste foodcoop_roles.md into the foodcoop minisite's features/roles/ page
```

Nothing here is Foodcoop-specific - the same commands work for any project, just with
a different `--env`.
