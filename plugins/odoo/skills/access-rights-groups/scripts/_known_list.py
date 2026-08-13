"""Shared known_groups.yaml formatting, used by the scripts in this skill
that write to it (extract_native_groups.py, discover_groups.py,
resolve_renames.py). Not a general-purpose library - lives only inside this
skill's scripts/ directory, matching the sibling `odooly` skill's convention
of each skill being self-contained.

A group's `purpose` defaults to this exact sentinel when nothing else is
known (Odoo's own `comment` field, when set, is used instead). This string
is checked verbatim by generate_roles_doc.py to decide whether to show a
group's real purpose or "(purpose not documented yet)" - keep the producers
(this constant) and that check in sync if either ever changes.
"""

import yaml

TODO_PURPOSE = "TODO: describe purpose"

KEY_ORDER = [
    "name",
    "also_named",
    "category",
    "also_category",
    "module",
    "ce_or_ee",
    "purpose",
    "renamed_from",
    "renamed_to",
    "removed_in",
    "versions_seen",
]


def bare_name(name, category):
    """A res.groups full_name is "Category / Name" when categorized, bare
    "Name" otherwise - but known_groups.yaml stores `name` and `category`
    as two separate fields, never the combined string. Strip the category
    prefix when present so a value read straight off a live full_name (or
    off any file that used the combined convention) normalizes to this
    skill's own convention before being written."""
    prefix = f"{category} / "
    if category and name.startswith(prefix):
        return name[len(prefix):]
    return name


def write_known_list(known, path):
    """Reorder each entry's keys for readable diffs, sort the top-level
    mapping by xml_id, and write it to `path`."""
    ordered = {}
    for xml_id in sorted(known):
        entry = known[xml_id]
        ordered[xml_id] = {k: entry[k] for k in KEY_ORDER if k in entry}
        for k, v in entry.items():
            if k not in ordered[xml_id]:
                ordered[xml_id][k] = v
    path.write_text(yaml.dump(ordered, sort_keys=False, allow_unicode=True, width=100))
    return ordered
