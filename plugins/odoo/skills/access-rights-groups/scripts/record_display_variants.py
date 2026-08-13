#!/usr/bin/env python3
"""
Record alternate display text a known res.groups xml_id has been seen with
in a real live diff - e.g. the same xml_id showing "Point of Sale" as its
category in one environment and "Point Of Sale" in another: a casing drift
in that one database's own ir.module.category record, not something Odoo's
own source ever declares differently across versions (checked: both 12.0's
and 18.0's point_of_sale/__manifest__.py say "Point of Sale", lowercase -
so this can't be caught by extract_native_groups.py scanning source, only
by actually diffing two live environments and noticing the same xml_id
disagrees with itself).

Reads a compare_access_rights.py CSV (--format csv, any two environments or
versions) and looks at every "[xml_id] Category / Name" group entry in its
`users` type rows' `groups` field. For each xml_id already known, any name
or category text seen that differs from what known_groups.yaml currently
has on record gets appended:

  - a different `name`     -> also_named (the same field
                               extract_native_groups.py already uses for
                               name drift found in source)
  - a different `category` -> also_category (this script's own field -
                               extract_native_groups.py has no equivalent,
                               since a live-database-only casing drift like
                               this isn't visible from source)

Only touches xml_ids already present in known_groups.yaml - same principle
as resolve_renames.py and detect_removed_groups.py: this script never
invents a new group entry, it only annotates ones already known.

Usage:
    python record_display_variants.py --csv /tmp/diff.csv --known-list known_groups.yaml
"""

import csv as csv_module
import pathlib
import re
import sys

import click
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _known_list import write_known_list  # noqa: E402

# Must match generate_html_report.py's GROUP_ENTRY_RE (odooly skill) and
# compare_access_rights.py's GROUP_LIST_SEP - this script reads the exact
# same CSV format, kept as its own small copy rather than a cross-skill
# import, matching this skill's self-contained convention.
GROUP_ENTRY_RE = re.compile(r"^\[([^\]]+)\] (.*)$")
GROUP_LIST_SEP = " | "


def parse_group_entry(raw):
    """'[xml_id] Category / Name' -> (xml_id, 'Category / Name'). A bare
    entry with no brackets (an older CSV, or a group with no resolvable
    xml_id) has nothing this script can attribute a variant to - skipped."""
    m = GROUP_ENTRY_RE.match(raw)
    return (m.group(1), m.group(2)) if m else (None, raw)


def split_group_name(full_name):
    """'Category / Name' -> ('Category', 'Name'); bare 'Name' -> ('', 'Name').
    Splits on the first " / " only - a group's own name can rarely contain
    " / " further in, the category never does. Raw text, not normalized -
    this script records exactly what was observed, case and all."""
    if " / " in full_name:
        category, name = full_name.split(" / ", 1)
        return category, name
    return "", full_name


def extract_variants(csv_path):
    """Return {xml_id: {"names": set(...), "categories": set(...)}} from
    every group entry seen in the CSV's per-user group-membership field
    (both the "before" and "after" side, so a variant only present on one
    side of the diff is still caught)."""
    variants = {}
    with open(csv_path, newline="") as f:
        reader = csv_module.DictReader(f)
        for row in reader:
            if row.get("type") != "users" or row.get("field") != "groups":
                continue
            for col in ("value_a", "value_b"):
                value = row.get(col) or ""
                if not value:
                    continue
                for entry in value.split(GROUP_LIST_SEP):
                    entry = entry.strip()
                    if not entry:
                        continue
                    xml_id, display = parse_group_entry(entry)
                    if not xml_id:
                        continue
                    category, name = split_group_name(display)
                    v = variants.setdefault(xml_id, {"names": set(), "categories": set()})
                    v["names"].add(name)
                    if category:
                        v["categories"].add(category)
    return variants


@click.command()
@click.option("--csv", "csv_path", required=True, type=click.Path(exists=True), help="CSV produced by compare_access_rights.py --format csv.")
@click.option("--known-list", required=True, type=click.Path(exists=True), help="known_groups.yaml to annotate.")
@click.option("--dry-run", is_flag=True, default=False, help="Print what would be recorded without writing.")
def run(csv_path, known_list, dry_run):
    """Record alternate name/category text a known xml_id was seen with in a real live diff."""
    variants = extract_variants(csv_path)

    known_path = pathlib.Path(known_list)
    known = yaml.safe_load(known_path.read_text()) or {}

    new_names, new_categories, unknown = [], [], set()
    for xml_id, v in sorted(variants.items()):
        if xml_id not in known:
            unknown.add(xml_id)
            continue
        entry = known[xml_id]
        current_name = entry.get("name")
        current_category = entry.get("category")

        for name in sorted(v["names"]):
            # No current_name at all is an incomplete entry, not a variant
            # to record - out of scope for this script.
            if not current_name or name == current_name:
                continue
            aliases = entry.setdefault("also_named", [])
            if name not in aliases:
                aliases.append(name)
                new_names.append((xml_id, name))

        for category in sorted(v["categories"]):
            if not current_category or category == current_category:
                continue
            aliases = entry.setdefault("also_category", [])
            if category not in aliases:
                aliases.append(category)
                new_categories.append((xml_id, category))

    click.echo(f"xml_ids seen in CSV: {len(variants)}")
    click.echo(f"New also_named entries: {len(new_names)}")
    for xml_id, name in new_names:
        click.echo(f"  - {xml_id}: {name!r}")
    click.echo(f"New also_category entries: {len(new_categories)}")
    for xml_id, category in new_categories:
        click.echo(f"  - {xml_id}: {category!r}")
    if unknown:
        click.echo(f"\n{len(unknown)} xml_id(s) in CSV not in known list (custom/project group, or not yet discovered - skipped)")

    if dry_run:
        click.echo("\n[dry-run] known list not written.")
        return

    write_known_list(known, known_path)
    click.echo(f"\nWrote {known_path}")


if __name__ == "__main__":
    run()
