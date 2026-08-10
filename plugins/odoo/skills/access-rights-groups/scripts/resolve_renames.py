#!/usr/bin/env python3
"""
Detect res.groups xml_id renames across Odoo versions using OCA OpenUpgrade's
migration data, and link the corresponding known_groups.yaml entries.

OpenUpgrade (github.com/OCA/OpenUpgrade) maintains one branch per target
version (e.g. the "16.0" branch holds the scripts that migrate a database
FROM the previous version TO 16.0). Module migration scripts commonly
declare a rename list such as:

    _xmlids_renames = [
        ("sale.group_delivery_invoice_address", "account.group_delivery_invoice_address"),
    ]

    def migrate(env, version):
        openupgrade.rename_xmlids(env.cr, _xmlids_renames)

used by `openupgrade.rename_xmlids()` to preserve customizations (view
inheritance, record rules, other modules' references) across the rename when
migrating a real production database. This is sourced, not inferred - it is
what Odoo/OCA actually run to migrate real databases, so it is authoritative
in a way that heuristics (e.g. matching on name + adjacent versions_seen)
are not: this codebase already has many groups that legitimately share the
same short name ("Administrator", "User", "Manager"...) across unrelated
categories, which would produce false positives under a name-matching
heuristic.

Deliberately does its own repo/version setup: `tlc pull-repos`
(https://github.com/trobz/local.py) already clones and keeps up to date one
OpenUpgrade checkout per target version (`<openupgrade-base>/<version>/openupgrade`,
same as its other OCA repos) - so this script assumes that layout and just
reads whatever is already there, plain filesystem reads, no git subprocess at
all. A version with no local checkout is skipped with a warning rather than
failing the whole run; run `tlc pull-repos` to fetch what's missing.

Only rename pairs where at least one side is already a known res.groups
xml_id in known_groups.yaml are kept - a rename pair where neither side is a
known group almost always belongs to some other model (a view, a report, a
menu item, ...), not a group.

Each link records the OpenUpgrade target-version branch the rename was found
in (e.g. a rename found on the "16.0" branch happened going into 16.0):

    renamed_to:
      - xml_id: account.group_delivery_invoice_address
        version: "16.0"

Usage:
    python resolve_renames.py \
        --refs 12.0,13.0,14.0,15.0,16.0,17.0,18.0,19.0 \
        --known-list known_groups.yaml
    # --openupgrade-base defaults to tlc's own layout (~/code/oca) - override
    # only if yours differs:
    python resolve_renames.py \
        --openupgrade-base ~/code/oca \
        --refs 12.0,13.0,14.0,15.0,16.0,17.0,18.0,19.0 --known-list known_groups.yaml
"""

import ast
import pathlib
import sys

import click
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _known_list import write_known_list  # noqa: E402


DEFAULT_OPENUPGRADE_BASE = "~/code/oca"


def list_migration_files(root):
    """Plain filesystem walk: every *.py file under this version's OpenUpgrade
    checkout that mentions a rename call. `root` is a real, dedicated checkout
    (tlc resets it on every pull), so a plain read is fine - no git needed."""
    matches = []
    for path in sorted(root.rglob("*.py")):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if "rename_xmlid" in text:
            matches.append(path)
    return matches


def extract_rename_pairs(text):
    """Best-effort extraction of (old_xmlid, new_xmlid) pairs from a
    migration script: both the common `_xmlids_renames = [(...), ...]`
    variable pattern (name varies: xmlid(s)_renames, case-insensitive) and
    direct `rename_xmlid(cr, "old", "new")` / `rename_xmlids(cr, [(...)])`
    calls with literal arguments."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    pairs = []

    def is_rename_var_name(name):
        name = name.lower()
        return "xmlid" in name and "renam" in name

    def add_pair_literal(value):
        if isinstance(value, (tuple, list)) and len(value) == 2 and all(isinstance(v, str) for v in value):
            pairs.append((value[0], value[1]))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and is_rename_var_name(target.id):
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(value, (list, tuple)):
                        for item in value:
                            add_pair_literal(item)
        elif isinstance(node, ast.Call):
            func_name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if func_name == "rename_xmlid" and len(node.args) >= 3:
                try:
                    old, new = ast.literal_eval(node.args[-2]), ast.literal_eval(node.args[-1])
                except (ValueError, SyntaxError):
                    continue
                add_pair_literal((old, new))
            elif func_name == "rename_xmlids" and node.args:
                last_arg = node.args[-1]
                if isinstance(last_arg, ast.List):
                    try:
                        value = ast.literal_eval(last_arg)
                    except (ValueError, SyntaxError):
                        continue
                    for item in value:
                        add_pair_literal(item)
    return pairs


def scan_dir_for_renames(root, version):
    """Return the deduplicated list of (old_xmlid, new_xmlid, version) found
    in this version's OpenUpgrade checkout."""
    found = []
    seen = set()
    for path in list_migration_files(root):
        text = path.read_text(errors="ignore")
        for old, new in extract_rename_pairs(text):
            key = (old, new)
            if key in seen:
                continue
            seen.add(key)
            found.append((old, new, version))
    return found


@click.command()
@click.option("--openupgrade-base", default=DEFAULT_OPENUPGRADE_BASE, type=click.Path(), help=f"Base directory holding one OCA/OpenUpgrade checkout per target version (<openupgrade-base>/<version>/openupgrade) - the layout `tlc pull-repos` (github.com/trobz/local.py) creates and keeps up to date. Default: {DEFAULT_OPENUPGRADE_BASE}")
@click.option("--refs", default="12.0,13.0,14.0,15.0,16.0,17.0,18.0,19.0", help="Comma-separated OpenUpgrade target-version branches to scan. Should cover at least every version known_groups.yaml itself covers, plus one - a rename found INTO version X lives on OpenUpgrade's \"X.0\" branch, so catching a rename into the oldest version known_groups.yaml has requires scanning one branch older than that.")
@click.option("--known-list", required=True, type=click.Path(exists=True), help="known_groups.yaml to link renames in.")
@click.option("--dry-run", is_flag=True, default=False, help="Print what would be linked without writing.")
def run(openupgrade_base, refs, known_list, dry_run):
    """Detect res.groups renames via local OpenUpgrade checkouts and link known_groups.yaml entries."""
    versions = [v.strip() for v in refs.split(",") if v.strip()]
    openupgrade_base = pathlib.Path(openupgrade_base).expanduser()

    known_path = pathlib.Path(known_list)
    known = yaml.safe_load(known_path.read_text()) or {}

    version_dirs = []
    skipped_versions = []
    for version in versions:
        version_dir = openupgrade_base / version / "openupgrade"
        if version_dir.is_dir():
            version_dirs.append((version, version_dir))
        else:
            skipped_versions.append(version)

    if skipped_versions:
        click.echo(
            f"Skipping {len(skipped_versions)} version(s) with no local checkout under {openupgrade_base}: "
            f"{', '.join(skipped_versions)} - run `tlc pull-repos` (https://github.com/trobz/local.py) "
            f"to fetch them, or pass --openupgrade-base.",
            err=True,
        )
    if not version_dirs:
        click.echo("No requested version has a local checkout - nothing to scan.", err=True)
        sys.exit(1)
    scanned_versions = [v for v, _ in version_dirs]

    all_renames = []
    for version, version_dir in version_dirs:
        all_renames.extend(scan_dir_for_renames(version_dir, version))
    click.echo(f"Scanned versions: {', '.join(scanned_versions)}")
    click.echo(f"Rename pairs found in OpenUpgrade migration scripts: {len(all_renames)}")

    group_renames = [(old, new, v) for old, new, v in all_renames if old in known or new in known]
    click.echo(f"Of those, involving a known res.groups xml_id: {len(group_renames)}")

    linked, both_sides_missing_one = 0, []
    for old, new, version in group_renames:
        if old not in known:
            both_sides_missing_one.append((old, new, version, "old"))
            continue
        if new not in known:
            both_sides_missing_one.append((old, new, version, "new"))
            continue
        old_entry, new_entry = known[old], known[new]
        old_entry.setdefault("renamed_to", [])
        new_entry.setdefault("renamed_from", [])
        if not any(link["xml_id"] == new for link in old_entry["renamed_to"]):
            old_entry["renamed_to"].append({"xml_id": new, "version": version})
            linked += 1
        if not any(link["xml_id"] == old for link in new_entry["renamed_from"]):
            new_entry["renamed_from"].append({"xml_id": old, "version": version})

    click.echo(f"New rename links added: {linked}")
    if both_sides_missing_one:
        click.echo(f"\n{len(both_sides_missing_one)} rename pairs skipped (only one side is a known group - the other may be a different model, or a group not yet discovered):")
        for old, new, version, missing_side in both_sides_missing_one[:30]:
            click.echo(f"  - [{version}] {old} -> {new}  ({missing_side} side not in known list)")
        if len(both_sides_missing_one) > 30:
            click.echo(f"  ... and {len(both_sides_missing_one) - 30} more")

    if dry_run:
        click.echo("\n[dry-run] known list not written.")
        return

    write_known_list(known, known_path)
    click.echo(f"\nWrote {known_path}")


if __name__ == "__main__":
    run()
