#!/usr/bin/env python3
"""
Write purpose text for a project's own custom/OCA res.groups - groups
discover_groups.py --evidence found live but that have no source this skill
can read (they don't belong in known_groups.yaml, which only ever tracks
native Odoo groups).

The purpose is built mechanically from the same ir.model.access + ir.ui.menu
evidence a human would read to write one by hand: it only ever states real
model/menu names the evidence actually contains, never an inferred guess
about what the group is "for" in plain language. An entry that already has a
purpose is left untouched on re-run (nothing here overwrites a purpose
someone has since hand-edited).

Output uses the same schema as known_groups.yaml (xml_id -> {name, category,
module, purpose}), deliberately - not the ad-hoc combined-name format some
earlier project-local files used - so the result can be pointed at directly
by generate_html_report.py's --known-list, or merged into one, without an
adapter.

Usage:
    python discover_groups.py -c ~/odooly.ini --env ENV --all --evidence \
        --format yaml > /tmp/evidence.yaml
    python write_project_group_purposes.py --evidence /tmp/evidence.yaml \
        --known-list project_groups.yaml
"""

import pathlib
import sys

import click
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _known_list import bare_name, write_known_list  # noqa: E402

FLAG_LABELS = {
    frozenset("rwcu"): "Full control (read/write/create/delete)",
    frozenset("rwc"): "Full control (no delete) access",
    frozenset("rw"): "Read/write access",
    frozenset("wc"): "Write/create access",
    frozenset("r"): "Read-only access",
    frozenset("w"): "Write-only access",
}


def describe_flags(flags):
    return FLAG_LABELS.get(frozenset(flags), f"Access ({flags})")


def parse_access_entry(entry):
    """'model.name (rwcu)' -> ('model.name', 'rwcu'). Malformed entries
    (shouldn't happen - this is discover_groups.py's own output format) are
    skipped rather than guessed at."""
    if " (" not in entry or not entry.endswith(")"):
        return None
    model, flags = entry.rsplit(" (", 1)
    return model, flags[:-1]


def humanize_model(model):
    """'sale.order' -> 'Sale Order'. Purely a mechanical reformat of the
    technical name (split on '.'/'_', title-case each word) - not a lookup
    of Odoo's own display name, which this evidence doesn't carry, so a
    model whose real label reads differently (e.g. res.partner -> "Contact")
    still shows its literal words here."""
    words = model.replace(".", " ").replace("_", " ").split()
    return " ".join(w.capitalize() for w in words)


def bullet_list(items):
    """One `- item` per line - the full list, never truncated with an
    "and N more" that would hide which ones. Rendered as a real list (not a
    single comma-run sentence) because this text ends up in an HTML `title`
    tooltip, where a browser renders `\\n` as an actual line break."""
    return "\n".join(f"- {item}" for item in items)


def summarize_models(models):
    """Bullet list of humanized model names for the purpose text."""
    return bullet_list(sorted(humanize_model(m) for m in models))


def summarize_menus(menus):
    """Bullet list of full menu paths for the purpose text."""
    return bullet_list(sorted(menus))


def build_purpose(row):
    """Return purpose text built only from what the evidence actually
    contains, or None when there's no access/menu evidence at all to
    summarize (nothing to write). One section per permission level / menus,
    each a real bullet list rather than a truncated comma-run sentence, so a
    group with many models still shows every one of them."""
    by_flags = {}
    for entry in row.get("access") or []:
        parsed = parse_access_entry(entry)
        if not parsed:
            continue
        model, flags = parsed
        if flags == "none":
            continue
        by_flags.setdefault(flags, []).append(model)

    sections = [
        f"{describe_flags(flags)} to records:\n{summarize_models(models)}"
        for flags, models in sorted(by_flags.items(), key=lambda kv: -len(kv[1]))
    ]

    menus = row.get("menus") or []
    if not sections and not menus:
        return None
    if not sections:
        sections.append("No direct record access found.")

    if menus:
        noun = "Menu" if len(menus) == 1 else "Menus"
        sections.append(f"{noun} access:\n{summarize_menus(menus)}")

    return "\n\n".join(sections)


@click.command()
@click.option("--evidence", "evidence_path", required=True, type=click.Path(exists=True),
              help="YAML produced by discover_groups.py --all --evidence --format yaml.")
@click.option("--known-list", "known_list", required=True, type=click.Path(),
              help="Project-local known_groups.yaml-shaped file to write purposes into (created if missing, merged if it exists).")
@click.option("--only-custom", is_flag=True, default=True,
              help="Only write for origin=custom groups (default on) - native groups belong in known_groups.yaml, sourced from CE/EE instead.")
def run(evidence_path, known_list, only_custom):
    """Write purpose text for a project's custom groups from live access evidence."""
    rows = yaml.safe_load(pathlib.Path(evidence_path).read_text()) or []

    known_path = pathlib.Path(known_list)
    known = {}
    if known_path.exists():
        known = yaml.safe_load(known_path.read_text()) or {}

    written, skipped_has_purpose, skipped_no_evidence, skipped_native = 0, 0, 0, 0
    for row in rows:
        xml_id = row.get("xml_id")
        if not xml_id or xml_id == "(no xml_id)":
            continue
        if only_custom and row.get("origin") != "custom":
            skipped_native += 1
            continue

        category = row.get("category") or ""
        entry = known.setdefault(xml_id, {})
        entry["name"] = bare_name(row.get("full_name") or xml_id.split(".", 1)[-1], category)
        entry["category"] = category
        entry["module"] = xml_id.split(".", 1)[0]

        if entry.get("purpose"):
            skipped_has_purpose += 1
            continue

        purpose = build_purpose(row)
        if purpose is None:
            skipped_no_evidence += 1
            continue
        entry["purpose"] = purpose
        written += 1

    click.echo(f"Written: {written}")
    click.echo(f"Skipped (already has a purpose): {skipped_has_purpose}")
    click.echo(f"Skipped (no access/menu evidence to summarize): {skipped_no_evidence}")
    if only_custom:
        click.echo(f"Skipped (native group - use extract_native_groups.py / known_groups.yaml instead): {skipped_native}")

    write_known_list(known, known_path)
    click.echo(f"\nWrote {known_path}")


if __name__ == "__main__":
    run()
