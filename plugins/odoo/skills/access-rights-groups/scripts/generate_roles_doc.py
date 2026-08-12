#!/usr/bin/env python3
"""
Render known_groups.yaml (optionally merged with a live project's own
groups) into a roles/purpose document: CSV, Markdown, or an Excel table.

Two source modes:
  - No --env: renders the known list as-is (a version-agnostic reference of
    every native group ever discovered), including a `versions_seen` column
    so readers see which Odoo series confirmed each group. Optionally
    narrowed to one series with --odoo-series.
  - With --env: connects live via odooly and renders the groups that
    actually exist on THAT project (correct for its exact Odoo version and
    installed modules). known_groups.yaml is only used to look up purpose
    text by xml_id; a live group without a known purpose yet is shown as
    "(purpose not documented yet)" rather than being dropped. Add
    --include-project-groups to also include that project's own
    custom/OCA groups, not just the native ones.

Usage:
    python generate_roles_doc.py --known-list known_groups.yaml --output roles.csv
    python generate_roles_doc.py --known-list known_groups.yaml --format md --output roles.md
    python generate_roles_doc.py --known-list known_groups.yaml --format table --output roles.xlsx
    python generate_roles_doc.py --known-list known_groups.yaml -c ~/odooly.ini --env ENV \
        --include-project-groups --format md --output roles.md
"""

import pathlib
import sys

import click
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _known_list import TODO_PURPOSE  # noqa: E402


def rows_from_known_list(known, odoo_series_filter):
    rows = []
    for xml_id, entry in known.items():
        if odoo_series_filter and odoo_series_filter not in (entry.get("versions_seen") or []):
            continue
        rows.append(
            {
                "category": entry.get("category") or "(uncategorized)",
                "name": entry.get("name") or xml_id,
                "xml_id": xml_id,
                "module": entry.get("module") or xml_id.split(".", 1)[0],
                "origin": entry.get("ce_or_ee") or "",
                "purpose": (entry.get("purpose") or "").strip(),
                "versions_seen": ", ".join(entry.get("versions_seen") or []),
            }
        )
    return rows


def rows_from_live_project(known, config, env, include_project_groups):
    # Imported lazily (requires odooly) so the known-list-only path above can
    # run without odooly installed at all, same as generate_html_report.py
    # does in the sibling odooly skill.
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import discover_groups

    odooly = discover_groups.odooly
    odooly.Client._config_file = pathlib.Path(config).expanduser()
    client = odooly.Client.from_config(env)
    odoo_series = discover_groups.get_odoo_series(client)

    live_rows = discover_groups.fetch_groups(client, odoo_series)
    if not include_project_groups:
        live_rows = [r for r in live_rows if r["origin"] in ("community", "enterprise")]

    rows = []
    for r in live_rows:
        known_entry = known.get(r["xml_id"], {})
        purpose = (known_entry.get("purpose") or r["comment"] or "").strip()
        if not purpose or purpose.startswith(TODO_PURPOSE):
            purpose = "(purpose not documented yet)"
        rows.append(
            {
                "category": r["category"] or "(uncategorized)",
                "name": r["full_name"],
                "xml_id": r["xml_id"],
                "module": r["xml_id"].split(".", 1)[0] if r["xml_id"] != "(no xml_id)" else "",
                "origin": r["origin"] or "",
                "purpose": purpose,
                "versions_seen": odoo_series.value,
            }
        )
    return rows


def write_csv(rows, output, include_versions):
    import csv

    fieldnames = ["category", "name", "xml_id", "module", "origin", "purpose"]
    if include_versions:
        fieldnames.append("versions_seen")
    out = open(output, "w", newline="") if output else sys.stdout
    try:
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if output:
            out.close()


def write_markdown(rows, output, include_versions):
    lines = []
    by_category = {}
    for r in rows:
        by_category.setdefault(r["category"], []).append(r)

    for category in sorted(by_category):
        lines.append(f"## {category}\n")
        header = ["Group", "XML ID", "Purpose"]
        if include_versions:
            header.append("Versions Seen")
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for r in sorted(by_category[category], key=lambda r: r["name"]):
            cells = [r["name"], f"`{r['xml_id']}`", r["purpose"].replace("\n", " ").strip() or "-"]
            if include_versions:
                cells.append(r["versions_seen"])
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    text = "\n".join(lines)
    if output:
        pathlib.Path(output).write_text(text)
    else:
        click.echo(text)


def write_xlsx(rows, output, include_versions):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    if not output:
        raise click.UsageError("--format table requires --output <file.xlsx>")

    wb = Workbook()
    ws = wb.active
    ws.title = "Access Rights Groups"

    headers = ["Category", "Group", "XML ID", "Module", "Origin", "Purpose"]
    if include_versions:
        headers.append("Versions Seen")
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in sorted(rows, key=lambda r: (r["category"], r["name"])):
        row = [r["category"], r["name"], r["xml_id"], r["module"], r["origin"], r["purpose"]]
        if include_versions:
            row.append(r["versions_seen"])
        ws.append(row)

    ws.freeze_panes = "A2"
    for col_cells in ws.columns:
        length = max(len(str(c.value)) if c.value is not None else 0 for c in col_cells)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 10), 60)

    wb.save(output)


@click.command()
@click.option("--known-list", required=True, type=click.Path(exists=True), help="known_groups.yaml to render.")
@click.option("-c", "--config", default="odooly.ini", help="Odooly config file (only used with --env).")
@click.option("--env", help="Odooly environment name - if set, renders that project's live groups instead of the raw known list.")
@click.option("--include-project-groups", is_flag=True, default=False, help="With --env, also include the project's own custom/OCA groups, not just native ones.")
@click.option("--odoo-series", help="Without --env, only include known-list entries seen in this series (e.g. 18.0).")
@click.option("--format", "fmt", type=click.Choice(["csv", "md", "table"]), default="csv", help="Output format: csv (default), md (Markdown table), table (.xlsx).")
@click.option("--output", type=click.Path(), help="Output file. Required for --format table; defaults to stdout for csv/md.")
def run(known_list, config, env, include_project_groups, odoo_series, fmt, output):
    """Generate a roles/purpose document from the known Access Rights groups list."""
    known = yaml.safe_load(pathlib.Path(known_list).read_text()) or {}

    if env:
        rows = rows_from_live_project(known, config, env, include_project_groups)
        include_versions = False
    else:
        rows = rows_from_known_list(known, odoo_series)
        include_versions = True

    if fmt == "csv":
        write_csv(rows, output, include_versions)
    elif fmt == "md":
        write_markdown(rows, output, include_versions)
    elif fmt == "table":
        write_xlsx(rows, output, include_versions)

    if output:
        click.echo(f"Wrote {output} ({len(rows)} groups).", err=True)


if __name__ == "__main__":
    run()
