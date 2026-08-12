#!/usr/bin/env python3
"""
Extract the real `res.groups` (and `ir.module.category`) records from local
Odoo Community and Enterprise checkouts, across one or more Odoo version
directories, and merge them into known_groups.yaml.

Deliberately does its own repo/version setup: `tlc pull-repos`
(https://github.com/trobz/local.py) already clones and keeps up to date one
checkout per version (`<ce-base>/<version>`, `<ee-base>/<version>`) - so this
script assumes that layout and just reads whatever is already there, plain
filesystem reads, no git subprocess at all. A version with no local checkout
under --ce-base is skipped with a warning rather than failing the whole run
(Enterprise access is optional, so a missing --ee-base/<version> is skipped
silently); run `tlc pull-repos` to fetch what's missing.

Usage:
    python extract_native_groups.py \
        --refs 16.0,17.0,18.0,19.0 \
        --known-list known_groups.yaml
    # --ce-base/--ee-base default to tlc's own layout (~/code/odoo/odoo,
    # ~/code/odoo/enterprise) - override only if yours differs:
    python extract_native_groups.py \
        --ce-base ~/code/odoo/odoo --ee-base ~/code/odoo/enterprise \
        --refs 16.0,17.0,18.0,19.0 --known-list known_groups.yaml

What this script CAN extract reliably from source: xml_id, name, category,
comment, module, community-vs-enterprise, and which of the requested
versions each group is present in (versions_seen).

`name` always reflects the latest version actually scanned (pass versions in
ascending order so it reflects the actually-latest wording). When a later
version's scan finds a different name text for an xml_id already known,
the previous text is preserved in `also_named` rather than discarded - a
group's display name can drift across versions independently of its
xml_id (e.g. Odoo 19.0 renamed base.group_user's own name field to "Role /
User"), and an instance not yet on that version still shows the older
text, which needs to stay matchable.

What it CANNOT reliably extract: a plain-language "purpose". `comment` is
used as a purpose hint when Odoo happens to set it (it's frequently empty on
core groups), but writing good purposes for new groups is still a manual /
AI-assisted enrichment step - this script only ever fills a group's
`purpose` when it doesn't already have one, and never overwrites existing
purpose text.
"""

import ast
import pathlib
import sys
import xml.etree.ElementTree as ET

import click
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _known_list import TODO_PURPOSE, write_known_list  # noqa: E402


DEFAULT_CE_BASE = "~/code/odoo/odoo"
DEFAULT_EE_BASE = "~/code/odoo/enterprise"


def module_from_path(rel_path, layout):
    """layout: 'ce' -> addons/<module>/... or odoo/addons/<module>/...
    'ee' -> <module>/... at the checkout root."""
    parts = rel_path.parts
    if layout == "ce":
        if parts[0] == "addons":
            module = parts[1]
        elif parts[0] == "odoo" and parts[1] == "addons":
            module = parts[2]
        else:
            return None
    else:
        module = parts[0]
    # test_* modules only exist to drive Odoo's own test suite - they're never
    # installed on a real database and would just be noise in the catalog.
    if module.startswith("test_"):
        return None
    return module


def parse_records(xml_text, model):
    """Yield (xml_id, fields_dict) for <record model="..."> blocks, best-effort."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return
    for record in root.iter("record"):
        if record.get("model") != model:
            continue
        rec_id = record.get("id")
        if not rec_id:
            continue
        fields = {}
        for field in record.findall("field"):
            fname = field.get("name")
            if fname in ("name", "comment"):
                fields[fname] = "".join(field.itertext()).strip()
            elif fname == "category_id":
                fields["category_ref"] = field.get("ref")
        yield rec_id, fields


def scan_records_in_dir(root, layout, model):
    """Yield (module, xml_id, fields) for every `model` record found under
    this version's checkout - a plain filesystem walk + XML parse, since
    `root` is a real, dedicated checkout (tlc resets it on every pull), not
    a shared working tree that needs git-show-without-checkout care."""
    needle = f'model="{model}"'
    for path in sorted(root.rglob("*.xml")):
        module = module_from_path(path.relative_to(root), layout)
        if module is None:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if needle not in text:
            continue
        yield from ((module, rec_id, fields) for rec_id, fields in parse_records(text, model))


def list_modules_in_dir(root, layout):
    """Return the set of module names whose addon directory exists in this checkout."""
    modules = set()
    if layout == "ce":
        for sub in ("addons", "odoo/addons"):
            d = root / sub
            if d.is_dir():
                modules.update(p.name for p in d.iterdir() if p.is_dir())
    else:
        if root.is_dir():
            modules.update(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    return modules


def resolve_category(category_ref, module, categories):
    """Resolve category_ref to a human name via the static ir.module.category
    lookup. Returns None (not the raw ref) when unresolved, so the caller can
    fall back to reading the module manifest instead of storing a raw id."""
    if not category_ref:
        return None
    xml_id = category_ref if "." in category_ref else f"{module}.{category_ref}"
    return categories.get(xml_id)


def read_manifest_category(root, layout, module, cache):
    """Many ir.module.category records are created at runtime from a module's
    __manifest__.py `category` field rather than declared in static XML (e.g.
    "Sales/Sales", "Inventory/Purchase") - fall back to reading it directly
    when the static ir.module.category lookup above comes up empty."""
    key = (str(root), module)
    if key in cache:
        return cache[key]
    candidates = (
        [root / module / "__manifest__.py"]
        if layout == "ee"
        else [root / "addons" / module / "__manifest__.py", root / "odoo" / "addons" / module / "__manifest__.py"]
    )
    category = None
    for path in candidates:
        if not path.exists():
            continue
        try:
            manifest = ast.literal_eval(path.read_text(errors="ignore"))
        except (ValueError, SyntaxError, OSError):
            manifest = None
        if isinstance(manifest, dict):
            category = manifest.get("category")
        break
    cache[key] = category
    return category


@click.command()
@click.option("--ce-base", default=DEFAULT_CE_BASE, type=click.Path(), help=f"Base directory holding one Odoo Community checkout per version (<ce-base>/<version>) - the layout `tlc pull-repos` (github.com/trobz/local.py) creates and keeps up to date. Default: {DEFAULT_CE_BASE}")
@click.option("--ee-base", default=DEFAULT_EE_BASE, type=click.Path(), help=f"Base directory holding one Odoo Enterprise checkout per version (<ee-base>/<version>). Optional - a missing version's directory (or the whole base) is skipped silently, since not everyone has access to the private repo. Default: {DEFAULT_EE_BASE}")
@click.option("--refs", default="18.0", help="Comma-separated Odoo series to scan (e.g. 16.0,17.0,18.0,19.0) - each resolved as <base>/<version>.")
@click.option("--known-list", required=True, type=click.Path(), help="known_groups.yaml to merge results into (created if missing).")
@click.option("--dry-run", is_flag=True, default=False, help="Print the diff summary without writing the known list.")
def run(ce_base, ee_base, refs, known_list, dry_run):
    """Extract res.groups from local CE/EE checkouts across versions and merge into the known list."""
    versions = [v.strip() for v in refs.split(",") if v.strip()]
    ce_base = pathlib.Path(ce_base).expanduser()
    ee_base = pathlib.Path(ee_base).expanduser()

    version_dirs = []
    skipped_versions = []
    for version in versions:
        ce_dir = ce_base / version
        if not ce_dir.is_dir():
            skipped_versions.append(version)
            continue
        ee_dir = ee_base / version
        version_dirs.append((version, ce_dir, ee_dir if ee_dir.is_dir() else None))

    if skipped_versions:
        click.echo(
            f"Skipping {len(skipped_versions)} version(s) with no local checkout under {ce_base}: "
            f"{', '.join(skipped_versions)} - run `tlc pull-repos` (https://github.com/trobz/local.py) "
            f"to fetch them, or pass --ce-base.",
            err=True,
        )
    if not version_dirs:
        click.echo("No requested version has a local checkout - nothing to scan.", err=True)
        sys.exit(1)
    scanned_versions = [v for v, _, _ in version_dirs]

    known_path = pathlib.Path(known_list)
    known = {}
    if known_path.exists():
        known = yaml.safe_load(known_path.read_text()) or {}

    added, updated_versions, seen_this_run = 0, 0, set()

    # (version, root, layout, ce_or_ee) for each version's CE checkout, plus
    # its EE checkout when present.
    sources = []
    for version, ce_dir, ee_dir in version_dirs:
        sources.append((version, ce_dir, "ce", "community"))
        if ee_dir:
            sources.append((version, ee_dir, "ee", "enterprise"))

    # Pass 1: figure out which checkout (community/enterprise) actually owns
    # each module's addon directory. A record's owning module (from its
    # xml_id) is not necessarily the module of the file that happens to touch
    # it - e.g. an Enterprise module's demo data can extend a Community
    # "base" record - so ce_or_ee must be looked up by owning module, never
    # by "which checkout this occurrence was found in".
    module_repo = {}
    for _version, root, layout, ce_or_ee in sources:
        for module in list_modules_in_dir(root, layout):
            module_repo.setdefault(module, ce_or_ee)

    # Pass 2: build one category-name lookup shared across CE + EE, since a
    # group's category is often defined in a different module (base) than
    # the group itself (e.g. an Enterprise group filed under a category
    # declared in Community's base module).
    categories = {}
    for _version, root, layout, _ce_or_ee in sources:
        for module, rec_id, fields in scan_records_in_dir(root, layout, "ir.module.category"):
            name = fields.get("name")
            if name:
                categories[f"{module}.{rec_id}"] = name

    # Pass 3: extract groups and resolve their category + owning checkout
    # against the shared lookups built above.
    manifest_cache = {}
    for version, root, layout, ce_or_ee in sources:
        groups = {}
        for module, rec_id, fields in scan_records_in_dir(root, layout, "res.groups"):
            # An id containing a dot (e.g. "base.default_user_group") is
            # Odoo's syntax for extending/overriding a record that already
            # exists under that fully-qualified xml_id in another module -
            # it is NOT a new record scoped to the current module, so it
            # must not be re-prefixed.
            xml_id = rec_id if "." in rec_id else f"{module}.{rec_id}"
            owning_module = xml_id.rsplit(".", 1)[0]
            merged = groups.setdefault(xml_id, {"module": owning_module})
            for k, v in fields.items():
                if v:
                    merged[k] = v

        for xml_id, fields in groups.items():
            seen_this_run.add(xml_id)
            entry = known.setdefault(xml_id, {})
            entry.setdefault("versions_seen", [])
            is_new = "name" not in entry and "module" not in entry

            entry["module"] = fields["module"]
            entry["ce_or_ee"] = module_repo.get(fields["module"], ce_or_ee)
            if fields.get("name"):
                new_name = fields["name"]
                # A group's xml_id can outlive a change to its own display
                # name (e.g. base.group_user's name text itself, not its
                # xml_id) - versions_seen only tracks "does this xml_id
                # exist", so without this the older text (still what many
                # real, not-yet-upgraded instances actually show) would be
                # silently discarded on every later-version scan.
                #
                # Only the LAST version actually scanned is authoritative
                # for entry["name"] - versions are re-scanned from scratch
                # on every run, so comparing an EARLIER version's text
                # against whatever a *previous run* already settled on
                # (rather than against this run's own scan order) would
                # misfile the current name as if it were the old one the
                # moment an older version gets processed after it.
                if version == scanned_versions[-1]:
                    old_name = entry.get("name")
                    if old_name and old_name != new_name:
                        aliases = entry.setdefault("also_named", [])
                        if old_name not in aliases:
                            aliases.append(old_name)
                    entry["name"] = new_name
                else:
                    current_name = entry.get("name")
                    if not current_name:
                        entry["name"] = new_name
                    elif current_name != new_name:
                        aliases = entry.setdefault("also_named", [])
                        if new_name not in aliases:
                            aliases.append(new_name)
            category = resolve_category(fields.get("category_ref"), fields["module"], categories)
            if not category and fields.get("category_ref"):
                manifest_category = read_manifest_category(root, layout, fields["module"], manifest_cache)
                if manifest_category:
                    # __manifest__.py's category is a "Parent/Child" string
                    # used to build the ir.module.category tree at install
                    # time - but a live instance's res.groups.category_id.name
                    # (what discover_groups.py reads, and what every live
                    # diff CSV actually shows) only ever holds the LEAF
                    # record's own name ("Point of Sale", never "Sales/Point
                    # of Sale" - the parent is a separate record, reached via
                    # parent_id, not part of this field). Keep only the leaf
                    # here too, so this fallback doesn't drift from what
                    # discover_groups.py and live instances actually show.
                    category = manifest_category.rsplit("/", 1)[-1]
            if category:
                entry["category"] = category
            if fields.get("comment") and not entry.get("purpose"):
                entry["purpose"] = fields["comment"]
            entry.setdefault("purpose", TODO_PURPOSE)

            if version not in entry["versions_seen"]:
                entry["versions_seen"].append(version)
                updated_versions += 1
            if is_new:
                added += 1

    click.echo(f"Scanned versions: {', '.join(scanned_versions)}")
    click.echo(f"Groups found this run: {len(seen_this_run)}")
    click.echo(f"New entries added to known list: {added}")
    click.echo(f"Entries with a version-presence update: {updated_versions}")
    click.echo(f"Total entries in known list: {len(known)}")

    if dry_run:
        click.echo("[dry-run] known list not written.")
        return

    write_known_list(known, known_path)
    click.echo(f"Wrote {known_path}")


if __name__ == "__main__":
    run()
