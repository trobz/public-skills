#!/usr/bin/env python3
"""
Generate a per-user HTML report from a compare_access_rights.py CSV export.

For each user with a changed group membership, the report shows two boxes:
  1. Roles assigned  - OCA `base_user_role` roles enabled for that user in
     env B (the "after" side), taken from the CSV's `roles` rows.
  2. Consequence on groups (diff) - the added/removed `res.groups` computed
     from the CSV's `users` / `groups` rows.

Users that only exist in one of the two environments (missing_in_a /
missing_in_b on the `users` `(record)` rows) are not real group diffs - they
are listed separately in a collapsed "excluded" note instead of being shown
as a fake "N -> 0 groups" change.

Usage:
    python generate_html_report.py --input DIFF.csv --output REPORT.html

Examples:
    # Typical flow: export a full CSV, then render it
    python compare_access_rights.py -c ~/odooly.ini --env-a staging --env-b staging_roles \\
        --format csv --output /tmp/diff.csv
    python generate_html_report.py --input /tmp/diff.csv --output /tmp/report.html \\
        --env-a staging --env-b staging_roles --title "Coop X - Role Migration Diff"

    # With the sibling access-rights-groups skill's known_groups.yaml: adds a
    # purpose tooltip to every group, folds an Odoo-caused rename (source:
    # resolve_renames.py) into one "renamed" entry instead of a fake
    # add+remove pair, and flags groups Odoo itself dropped at a given
    # version (source: detect_removed_groups.py) so they don't read as an
    # unexplained access change.
    python generate_html_report.py --input /tmp/diff.csv --output /tmp/report.html \\
        --known-list ../../access-rights-groups/scripts/known_groups.yaml

Matching prefers each group's xml_id when the CSV has one (compare_access_rights.py
embeds it as "[xml_id] Display Name" per entry) - a real, stable identifier, unlike
display text which can be translated, customized per project, or coincide between two
completely unrelated groups (e.g. a native group's old display name and a project's
own custom group happening to share the same bare name). Falls back to (category,
name) text matching only when no xml_id is available - an older CSV from before this,
or a group with no resolvable xml_id at all.
"""

import csv
import html
import pathlib
import re
from datetime import date

import click
import yaml

# Must match GROUP_LIST_SEP in compare_access_rights.py's fetch_user_groups().
DEFAULT_GROUP_SEP = " | "

# Same sentinel as _known_list.py in the sibling access-rights-groups skill.
# Not imported directly - each skill's scripts/ is self-contained - but the
# string itself is a stable contract of known_groups.yaml's format.
TODO_PURPOSE = "TODO: describe purpose"


class NameFallbackDict(dict):
    """A {(category, name): value} dict whose .get() also tries a
    same-name-different-category fallback when the exact (category, name)
    key misses.

    A live instance's ir.module.category display name can drift from
    known_groups.yaml's cached one - same version-rename or project-custom
    override that already affects res.groups itself (see
    resolve_renames.py) - so "Invoicing / Bookkeeper" in the catalog and
    "Accounting & Finance / Bookkeeper" live are the same group with only
    the category text disagreeing. The fallback is only used when that bare
    name is unambiguous across the WHOLE known list (maps to exactly one
    category) - a name shared by unrelated groups in different categories
    (there are legitimately many named "Administrator", "User"...) is
    deliberately left out rather than guessed at, matching this skill's
    never-infer-from-name-alone rule.
    """

    def __init__(self, data):
        super().__init__(data)
        categories_by_name = {}
        for category, name in data:
            categories_by_name.setdefault(name, set()).add(category)
        self._by_name = {
            name: data[(next(iter(cats)), name)]
            for name, cats in categories_by_name.items()
            if len(cats) == 1
        }

    def get(self, key, default=None):
        value = super().get(key)
        if value is not None:
            return value
        return self._by_name.get(key[1], default)


GROUP_ENTRY_RE = re.compile(r"^\[([^\]]+)\] (.*)$")


def parse_group_entry(raw):
    """Split one compare_access_rights.py group-list entry into
    (xml_id, display_text). New-format entries are "[xml_id] Display Name" -
    xml_id is None for a legacy-format CSV entry (no brackets - predates
    compare_access_rights.py embedding xml_id) or a group with no
    resolvable xml_id at all (rare - missing ir.model.data entry;
    compare_access_rights.py emits the bare display name for those too)."""
    m = GROUP_ENTRY_RE.match(raw)
    if m:
        return m.group(1), m.group(2)
    return None, raw


class GroupLookup:
    """Looks up a value for a group entry, preferring its xml_id (a real,
    stable identifier - never translated, never customized per project,
    never coincides between two unrelated groups) and falling back to
    (category, name) text matching only when no xml_id is available."""

    def __init__(self, by_xmlid, by_name):
        self.by_xmlid = by_xmlid
        self.by_name = by_name  # NameFallbackDict, keyed by (category, name)

    def get(self, xmlid, display_text):
        if xmlid and xmlid in self.by_xmlid:
            return self.by_xmlid[xmlid]
        return self.by_name.get(split_group_name(display_text))


def normalize_category(category):
    """Case/whitespace-insensitive form of a category string, used only to
    build lookup keys - never displayed (the report always renders the raw
    CSV group text, never `category` on its own), so folding it is safe.

    The same category can show up with different casing depending on
    source - e.g. a live instance's res.groups.category_id.name showing
    "Point Of Sale" while known_groups.yaml (extracted from Odoo's own
    source at some point) has "Point of Sale" - both sides of every lookup
    (split_group_name() for the CSV, load_known_index() for the known-list
    files) normalize through this same function, so they always agree."""
    return (category or "").strip().casefold()


def bare_name(name, category):
    """Some project-local group-purpose files (anything not produced by
    _known_list.py's write_known_list()) store `name` as the combined
    "Category / Name" display string rather than the bare name -
    known_groups.yaml's own convention keeps them as two separate fields.
    Strip the category prefix when present so every source normalizes to
    the same (category, name) key, regardless of which convention the file
    that produced it used."""
    prefix = f"{category} / "
    if category and name.startswith(prefix):
        return name[len(prefix):]
    return name


def load_known_index(known_list_paths):
    """Load one or more access-rights-groups-style YAML files (the shared
    known_groups.yaml, and/or a project-local custom-groups purpose file)
    and merge them into the lookups the report needs.

    Every lookup is keyed PRIMARILY by xml_id (a real, stable identifier -
    every entry has one, since it's the file's own top-level key) with a
    (category, name) text-based fallback for CSV entries with no xml_id
    (an older CSV predating compare_access_rights.py embedding it, or a
    group with no resolvable xml_id at all). See GroupLookup.

    known_list_paths: one path, or a list of paths - later files only add
    entries the earlier ones didn't already have (first file wins on
    conflict), so pass the authoritative native known_groups.yaml first and
    a project-local custom-groups file after.

    Returns (purposes, renamed_pairs, renamed_by_xmlid, removed_versions):
      purposes: GroupLookup - purpose text. Entries with no documented
        purpose yet (missing, or still the TODO_PURPOSE sentinel) are left
        out rather than surfaced as noise.
      renamed_pairs: {(category, name) of the OLD group: [((new_category,
        new_name), version), ...]} - name-based fallback for renamed_to
        links, used only when the CSV has no xml_id for the removed side.
      renamed_by_xmlid: {old_xml_id: [(new_xml_id, version), ...]} - the
        precise, preferred form of the same renamed_to data.
      removed_versions: GroupLookup - [version, ...] real deletions
        confirmed by at least one actual upgrade run, not a global
        guarantee.
    """
    if isinstance(known_list_paths, (str, pathlib.Path)):
        known_list_paths = [known_list_paths]

    purposes_by_name = {}
    purposes_by_xmlid = {}
    removed_by_name = {}
    removed_by_xmlid = {}
    renamed_pairs = {}
    renamed_by_xmlid = {}

    for known_list_path in known_list_paths:
        known = yaml.safe_load(pathlib.Path(known_list_path).read_text()) or {}

        xmlid_to_name = {}
        for xml_id, entry in known.items():
            category = entry.get("category") or ""
            key = (normalize_category(category), bare_name(entry.get("name") or "", category))
            xmlid_to_name[xml_id] = key
            purpose = (entry.get("purpose") or "").strip()
            if purpose and not purpose.startswith(TODO_PURPOSE):
                purposes_by_name.setdefault(key, purpose)
                purposes_by_xmlid.setdefault(xml_id, purpose)
            if entry.get("removed_in"):
                removed_by_name.setdefault(key, entry["removed_in"])
                removed_by_xmlid.setdefault(xml_id, entry["removed_in"])
            # A live instance not yet on the Odoo version that last renamed
            # this group's display text (extract_native_groups.py's
            # also_named) still shows the older text - register the same
            # purpose/removed_versions under every historical name too
            # (name-based only; also_named has no xml_id of its own to key
            # on, it's the same xml_id under a different old display name),
            # so it stays matchable regardless of which text a given
            # instance actually shows.
            for old_name in entry.get("also_named") or []:
                old_key = (normalize_category(category), old_name)
                if purpose and not purpose.startswith(TODO_PURPOSE):
                    purposes_by_name.setdefault(old_key, purpose)
                if entry.get("removed_in"):
                    removed_by_name.setdefault(old_key, entry["removed_in"])

        for xml_id, entry in known.items():
            targets = entry.get("renamed_to") or []
            if not targets:
                continue
            renamed_by_xmlid.setdefault(xml_id, [(link["xml_id"], link["version"]) for link in targets])
            resolved = [
                (xmlid_to_name[link["xml_id"]], link["version"])
                for link in targets
                if link["xml_id"] in xmlid_to_name
            ]
            if resolved:
                renamed_pairs.setdefault(xmlid_to_name[xml_id], resolved)

    purposes = GroupLookup(purposes_by_xmlid, NameFallbackDict(purposes_by_name))
    removed_versions = GroupLookup(removed_by_xmlid, NameFallbackDict(removed_by_name))
    return purposes, renamed_pairs, renamed_by_xmlid, removed_versions


def split_group_name(full_name):
    """Split a res.groups full_name ("Category / Name" or bare "Name") into
    (category, name), matching how known_groups.yaml stores the same group.
    Splits on the first " / " only - a group's own name can contain " / "
    further in (rare, but seen in the wild), the category never does.

    The category half is run through normalize_category() so it lines up
    with load_known_index()'s keys regardless of casing differences between
    this live CSV and whatever known_groups.yaml happened to capture."""
    if " / " in full_name:
        category, name = full_name.split(" / ", 1)
        return normalize_category(category), name
    return "", full_name


def load_rows(input_path):
    with open(input_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def split_groups(value, sep):
    """Split a joined group-name field back into individual names.

    The CSV field was built by joining group full_names with `sep`, but a
    group's own name can itself contain that separator (e.g. "View Member
    SmartButton (Account Analytic, Archive)" with sep=", "), which chops it
    into bogus fragments. As a defense (on top of using an unambiguous
    GROUP_LIST_SEP going forward), re-merge consecutive fragments whose
    parentheses don't balance until they do - this reconstructs names like
    the one above even when the source CSV used the old ", " separator.
    """
    if not value:
        return set()
    raw_parts = [p.strip() for p in value.split(sep)]
    raw_parts = [p for p in raw_parts if p]

    merged = []
    buffer = None
    for part in raw_parts:
        buffer = part if buffer is None else f"{buffer}{sep}{part}"
        if buffer.count("(") <= buffer.count(")"):
            merged.append(buffer)
            buffer = None
    if buffer is not None:
        merged.append(buffer)
    return set(merged)


def build_user_diffs(rows, group_sep):
    """Return (users, missing_users, warnings).

    users: {login: {"before": set, "after": set}}, only entries with an
    actual group diff (status == "different").
    missing_users: [(login, "only_in_a" | "only_in_b")]
    warnings: list of str, surfaced on stderr, not in the HTML.
    """
    users = {}
    missing_users = []
    warnings = []

    for row in rows:
        if row.get("type") != "users":
            continue
        login = row["key"]
        field = row["field"]
        status = row["status"]

        if field == "groups":
            if status != "different":
                continue
            users[login] = {
                "before": split_groups(row["value_a"], group_sep),
                "after": split_groups(row["value_b"], group_sep),
            }
        elif field == "(record)":
            if status == "missing_in_b":
                missing_users.append((login, "only_in_a"))
            elif status == "missing_in_a":
                missing_users.append((login, "only_in_b"))
        elif field == "(duplicate)":
            warnings.append(f"duplicate 'users' natural key for {login!r}: {row['value_a'] or row['value_b']}")

    return users, missing_users, warnings


def build_user_roles(rows):
    """Return {login: sorted [role names]} currently assigned in env B."""
    roles = {}
    for row in rows:
        if row.get("type") != "roles":
            continue
        field = row["field"]
        status = row["status"]
        # A role counts as "assigned in B" when it's new-only-in-B
        # (missing_in_a on the (record) field) or present unchanged on both
        # sides (status "same", only emitted when compare was run --full).
        # missing_in_b (role dropped in B) is deliberately excluded.
        assigned_in_b = (field == "(record)" and status == "missing_in_a") or (
            field == "role" and status == "same"
        )
        if not assigned_in_b:
            continue
        login, role = row["key"].rsplit(" / ", 1)
        roles.setdefault(login, set()).add(role)
    return {login: sorted(names) for login, names in roles.items()}


CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --card: #f9fafb; --added: #059669; --added-bg: #ecfdf5;
  --removed: #dc2626; --removed-bg: #fef2f2; --accent: #1f4e79;
  --critical-bg: #fff1f2; --critical-border: #fca5a5;
  --role: #6d28d9; --role-bg: #f5f3ff; --role-border: #ddd6fe;
  --renamed: #b45309; --renamed-bg: #fffbeb; --renamed-border: #fde68a;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --fg: #e5e7eb; --muted: #9ca3af; --border: #2a2e37;
    --card: #171a21; --added: #34d399; --added-bg: #052e22;
    --removed: #f87171; --removed-bg: #2c1315; --accent: #7fa8d0;
    --critical-bg: #2c1315; --critical-border: #7f1d1d;
    --role: #c4b5fd; --role-bg: #211a36; --role-border: #4c3a83;
    --renamed: #fbbf24; --renamed-bg: #2c2210; --renamed-border: #78530f;
  }
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 0; padding: 2rem 1.25rem 4rem; line-height: 1.5;
  overflow-x: hidden;
}
.wrap { max-width: 860px; margin: 0 auto; min-width: 0; }
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; color: var(--accent); }
.meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 1.5rem; }
.summary {
  display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1.5rem;
  padding: 0.9rem 1.1rem; background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; font-size: 0.9rem;
}
.summary b { font-size: 1.1rem; display: block; }
.controls { margin-bottom: 1rem; display: flex; gap: 0.5rem; }
.controls button {
  background: var(--card); color: var(--fg); border: 1px solid var(--border);
  border-radius: 8px; padding: 0.4rem 0.9rem; font-size: 0.85rem; cursor: pointer;
}
.controls button:hover { border-color: var(--accent); }
details.user {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  margin-bottom: 0.6rem; max-width: 100%;
}
details.user.critical { background: var(--critical-bg); border-color: var(--critical-border); }
summary {
  cursor: pointer; padding: 0.7rem 1rem; display: flex; align-items: center;
  flex-wrap: wrap; gap: 0.4rem 0.6rem; font-size: 0.92rem; list-style: none;
  border-radius: 10px;
}
details[open] > summary { border-radius: 10px 10px 0 0; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "\\25b8"; color: var(--muted); font-size: 0.75rem; transition: transform 0.15s; flex: none; }
details[open] > summary::before { transform: rotate(90deg); }
.login {
  font-weight: 600; overflow-wrap: anywhere; word-break: break-word;
  min-width: 0; flex: 1 1 auto;
}
.counts {
  color: var(--muted); font-size: 0.82rem;
  flex: 0 0 auto; white-space: nowrap;
}
.added-count { color: var(--added); font-weight: 600; }
.removed-count { color: var(--removed); font-weight: 600; }
.badge.critical {
  background: var(--removed); color: white; font-size: 0.68rem; font-weight: 700;
  padding: 0.15rem 0.5rem; border-radius: 999px; letter-spacing: 0.02em;
  flex: 0 0 auto; white-space: nowrap;
}
.body { padding: 0 1rem 1rem; border-top: 1px solid var(--border); max-width: 100%; }
.body h4 { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); margin: 0.8rem 0 0.4rem; }
.roles-panel {
  padding: 0.6rem 0.7rem 0.7rem; margin-bottom: 0.7rem;
  background: var(--role-bg); border: 1px solid var(--role-border); border-radius: 8px;
}
.roles-panel h4 { margin-top: 0; color: var(--role); }
ul.rolelist { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 0.35rem; }
ul.rolelist li {
  font-size: 0.82rem; font-weight: 600; color: var(--role); background: var(--bg);
  border: 1px solid var(--role-border); padding: 0.2rem 0.65rem; border-radius: 999px;
}
.renamed-panel {
  padding: 0.6rem 0.7rem 0.7rem; margin-bottom: 0.7rem;
  background: var(--renamed-bg); border: 1px solid var(--renamed-border); border-radius: 8px;
}
.renamed-panel h4 { margin-top: 0; color: var(--renamed); }
ul.renamelist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.3rem; }
ul.renamelist li { font-size: 0.85rem; overflow-wrap: anywhere; }
.g-removed-inline { color: var(--removed); }
.g-added-inline { color: var(--added); font-weight: 600; }
.rename-version { color: var(--muted); font-size: 0.78rem; }
.renamed-count { color: var(--renamed); font-weight: 600; }
.g-explained { opacity: 0.75; }
.explain-badge {
  display: inline-block; font-size: 0.68rem; color: var(--renamed); background: var(--renamed-bg);
  border: 1px solid var(--renamed-border); padding: 0.05rem 0.4rem; border-radius: 999px;
  margin-left: 0.35rem; white-space: nowrap;
}
.groups-panel {
  padding: 0.6rem 0.7rem 0.7rem;
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
}
.groups-panel h4 { margin-top: 0; }
.diffgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 480px) { .diffgrid { grid-template-columns: 1fr; } }
.col { min-width: 0; }
.diffgrid .col h4 { font-size: 0.72rem; margin: 0 0 0.4rem; }
ul.grouplist { list-style: none; margin: 0; padding: 0; }
ul.grouplist li {
  font-size: 0.85rem; padding: 0.2rem 0.5rem; border-radius: 5px; margin-bottom: 2px;
  overflow-wrap: anywhere; word-break: break-word;
}
li.g-added { background: var(--added-bg); color: var(--added); }
li.g-removed { background: var(--removed-bg); color: var(--removed); }
.empty { color: var(--muted); font-size: 0.85rem; font-style: italic; }
.excluded { margin-top: 1.5rem; color: var(--muted); font-size: 0.85rem; }
.excluded summary { cursor: pointer; padding: 0.3rem 0; }
.excluded ul { margin: 0.4rem 0 0; padding-left: 1.2rem; }
footer { margin-top: 2rem; color: var(--muted); font-size: 0.78rem; }
"""


def render_roles_panel(roles):
    if not roles:
        return '<div class="roles-panel"><h4>Roles assigned</h4><div class="empty">none</div></div>'
    chips = "".join(f'<li class="role-chip">{html.escape(r)}</li>' for r in roles)
    return f'<div class="roles-panel"><h4>Roles assigned</h4><ul class="rolelist">{chips}</ul></div>'


def render_group_col(title, items, css_class, purposes, removed_versions=None):
    if not items:
        return f'<div class="col"><h4>{html.escape(title)} (0)</h4><div class="empty">none</div></div>'
    removed_versions = removed_versions or GroupLookup({}, NameFallbackDict({}))
    lis = []
    for raw in items:
        xmlid, display = parse_group_entry(raw)
        purpose = purposes.get(xmlid, display)
        title_attr = f' title="{html.escape(purpose)}"' if purpose else ""
        explained_versions = removed_versions.get(xmlid, display)
        explain_html = ""
        extra_class = ""
        if explained_versions:
            extra_class = " g-explained"
            explain_html = f' <span class="explain-badge">removed by Odoo @ {html.escape(", ".join(explained_versions))}</span>'
        lis.append(f'<li class="{css_class}{extra_class}"{title_attr}>{html.escape(display)}{explain_html}</li>')
    return f'<div class="col"><h4>{html.escape(title)} ({len(items)})</h4><ul class="grouplist">{"".join(lis)}</ul></div>'


def render_renamed_panel(renamed, purposes):
    """renamed: [(old_raw, new_raw, version), ...] - each side still the raw
    CSV entry ("[xml_id] Display Name" or bare "Display Name"), parsed here
    for both display text and purpose lookup. Shown as its own panel,
    separate from added/removed - a rename didn't add or remove any actual
    capability, so folding it into either count would misstate the diff."""
    if not renamed:
        return ""
    items = []
    for old_raw, new_raw, version in renamed:
        _, old_display = parse_group_entry(old_raw)
        new_xmlid, new_display = parse_group_entry(new_raw)
        purpose = purposes.get(new_xmlid, new_display)
        title_attr = f' title="{html.escape(purpose)}"' if purpose else ""
        items.append(
            f'<li{title_attr}><span class="g-removed-inline">{html.escape(old_display)}</span>'
            f" &rarr; <span class=\"g-added-inline\">{html.escape(new_display)}</span>"
            f' <span class="rename-version">(Odoo {html.escape(version)})</span></li>'
        )
    return (
        '<div class="renamed-panel"><h4>Renamed by Odoo, not an access change '
        f'({len(renamed)})</h4><ul class="renamelist">{"".join(items)}</ul></div>'
    )


def find_renames(removed, added, renamed_pairs, renamed_by_xmlid):
    """Split (removed, added) raw-entry sets into (removed, added, renamed) -
    pulling out pairs where a 'removed' group is known to have been renamed
    (by a real Odoo upgrade, per resolve_renames.py) into an 'added' one, so
    the diff doesn't misreport a rename as one access lost + one gained.

    Tries the precise xml_id match first (renamed_by_xmlid - exact, no risk
    of a coincidental name collision), falling back to the (category, name)
    text match (renamed_pairs) only when the removed side has no xml_id."""
    removed, added = set(removed), set(added)

    added_by_xmlid, added_by_display = {}, {}
    for raw in added:
        xmlid, display = parse_group_entry(raw)
        if xmlid:
            added_by_xmlid.setdefault(xmlid, raw)
        added_by_display.setdefault(display, raw)

    renamed = []
    for old_raw in sorted(removed):
        old_xmlid, old_display = parse_group_entry(old_raw)
        match_raw, version = None, None

        if old_xmlid:
            for new_xmlid, v in renamed_by_xmlid.get(old_xmlid, []):
                if new_xmlid in added_by_xmlid:
                    match_raw, version = added_by_xmlid[new_xmlid], v
                    break

        if match_raw is None:
            old_key = split_group_name(old_display)
            for (new_cat, new_name), v in renamed_pairs.get(old_key, []):
                new_full = f"{new_cat} / {new_name}" if new_cat else new_name
                if new_full in added_by_display:
                    match_raw, version = added_by_display[new_full], v
                    break

        if match_raw is not None:
            renamed.append((old_raw, match_raw, version))
            added.discard(match_raw)
            removed.discard(old_raw)
    return removed, added, renamed


def render_user_block(login, before, after, roles, purposes=None, renamed_pairs=None, renamed_by_xmlid=None, removed_versions=None):
    purposes = purposes or GroupLookup({}, NameFallbackDict({}))
    renamed_pairs = renamed_pairs or {}
    renamed_by_xmlid = renamed_by_xmlid or {}
    removed_versions = removed_versions or GroupLookup({}, NameFallbackDict({}))

    removed, added, renamed = find_renames(before - after, after - before, renamed_pairs, renamed_by_xmlid)
    # Sort by display text, not the raw "[xml_id] ..." entry - otherwise
    # entries with an xml_id would sort separately from (and inconsistently
    # with) entries without one, instead of one sensible alphabetical list.
    added = sorted(added, key=lambda raw: parse_group_entry(raw)[1])
    removed = sorted(removed, key=lambda raw: parse_group_entry(raw)[1])

    critical = bool(before) and not after
    css_classes = "user critical" if critical else "user"
    badge = '<span class="badge critical">ALL ACCESS REMOVED</span>' if critical else ""
    roles_panel = render_roles_panel(roles)
    renamed_panel = render_renamed_panel(renamed, purposes)
    added_col = render_group_col("Added", added, "g-added", purposes)
    removed_col = render_group_col("Removed", removed, "g-removed", purposes, removed_versions)

    return f"""    <details class="{css_classes}">
      <summary>
        <span class="login">{html.escape(login)}</span>
        <span class="counts">{len(before)} &rarr; {len(after)} groups &nbsp; <span class="added-count">+{len(added)}</span> <span class="removed-count">-{len(removed)}</span>{f' <span class="renamed-count">&#8644;{len(renamed)}</span>' if renamed else ''}</span>
        {badge}
      </summary>
      <div class="body">
        {roles_panel}
        {renamed_panel}
        <div class="groups-panel">
          <h4>Consequence on groups (diff)</h4>
          <div class="diffgrid">
            {added_col}
            {removed_col}
          </div>
        </div>
      </div>
    </details>
"""


def render_excluded(missing_users):
    if not missing_users:
        return ""
    items = "".join(
        f"<li>{html.escape(login)} &mdash; {'present only in env A' if side == 'only_in_a' else 'present only in env B'}</li>"
        for login, side in sorted(missing_users)
    )
    return f"""
  <details class="excluded">
    <summary>{len(missing_users)} user(s) present in only one environment (excluded from the diff below)</summary>
    <ul>{items}</ul>
  </details>
"""


@click.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="CSV produced by compare_access_rights.py --format csv.")
@click.option("--output", "output_path", required=True, type=click.Path(dir_okay=False),
              help="Path to write the HTML report to.")
@click.option("--title", default=None, help="Report title (default: 'Access Rights Diff').")
@click.option("--env-a", default="env A (before)", help="Label for the first environment.")
@click.option("--env-b", default="env B (after)", help="Label for the second environment.")
@click.option("--group-sep", default=DEFAULT_GROUP_SEP,
              help=f"Separator used to join group names in the 'users' CSV field (default: {DEFAULT_GROUP_SEP!r}).")
@click.option("--known-list", "known_list_paths", multiple=True, type=click.Path(exists=True, dir_okay=False),
              help="access-rights-groups-style YAML (known_groups.yaml, and/or a project-local custom-groups "
                   "purpose file) to annotate the report with - repeatable, pass native known_groups.yaml first "
                   "and a project-local custom-groups file after. Annotates each group with its purpose, folds "
                   "Odoo-caused renames (resolve_renames.py) into a single 'renamed' entry instead of a fake "
                   "add+remove, and flags removed groups that Odoo itself dropped (detect_removed_groups.py).")
def run(input_path, output_path, title, env_a, env_b, group_sep, known_list_paths):
    """Render a compare_access_rights.py CSV export as a per-user HTML report."""
    rows = load_rows(input_path)

    users, missing_users, warnings = build_user_diffs(rows, group_sep)
    roles_by_user = build_user_roles(rows)

    for w in warnings:
        click.echo(f"warning: {w}", err=True)

    purposes, renamed_pairs, renamed_by_xmlid, removed_versions = (
        load_known_index(known_list_paths)
        if known_list_paths
        else (GroupLookup({}, NameFallbackDict({})), {}, {}, GroupLookup({}, NameFallbackDict({})))
    )

    logins = sorted(users)
    critical_count = sum(1 for login in logins if users[login]["before"] and not users[login]["after"])
    partial_count = len(logins) - critical_count

    blocks = "".join(
        render_user_block(
            login, users[login]["before"], users[login]["after"], roles_by_user.get(login, []),
            purposes, renamed_pairs, renamed_by_xmlid, removed_versions,
        )
        for login in logins
    )

    report_title = title or "Access Rights Diff"
    meta = f"{html.escape(env_a)} vs. {html.escape(env_b)} &middot; generated by generate_html_report.py (odooly skill) &middot; data as of {date.today().isoformat()}"

    summary_parts = [f'<div><b>{len(logins)}</b> users with a change</div>']
    if critical_count:
        summary_parts.append(f'<div><b style="color:var(--removed)">{critical_count}</b> lost all access</div>')
        summary_parts.append(f'<div><b>{partial_count}</b> partial change</div>')
    summary = "".join(summary_parts)

    doc = f"""<meta charset="utf-8"/>
<title>{html.escape(report_title)}</title>
<style>{CSS}</style>

<div class="wrap">
  <h1>{html.escape(report_title)}</h1>
  <div class="meta">{meta}</div>

  <div class="summary">
    {summary}
  </div>

  <div class="controls">
    <button onclick="document.querySelectorAll('details.user').forEach(d=>d.open=true)">Expand all</button>
    <button onclick="document.querySelectorAll('details.user').forEach(d=>d.open=false)">Collapse all</button>
  </div>

{blocks}
{render_excluded(missing_users)}
  <footer>Source: {html.escape(pathlib.Path(input_path).name)}</footer>
</div>
"""

    pathlib.Path(output_path).write_text(doc, encoding="utf-8")
    click.echo(f"{len(logins)} users with a change ({critical_count} critical), {len(missing_users)} excluded (only in one env)")
    click.echo(f"Report written to {output_path}")


if __name__ == "__main__":
    run()
