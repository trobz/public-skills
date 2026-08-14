#!/usr/bin/env python3
"""
Render a list_users.py CSV export as a standalone HTML report.

A separate script from list_users.py on purpose, mirroring the sibling
`odooly` skill's own split between fetching data (compare_access_rights.py)
and rendering it (generate_html_report.py): one script talks to the live
instance, the other only ever reads a CSV already on disk. This report is
its own thing, not a section bolted onto odooly's diff report - different
skills, different reports.

Usage:
    python list_users.py -c ~/odooly.ini --env ENV --format csv --output /tmp/users.csv
    python generate_users_report.py --input /tmp/users.csv --output /tmp/report.html --env ENV
"""

import csv
import html
import pathlib
from datetime import date

import click
import yaml

CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --card: #f9fafb; --accent: #1f4e79; --role: #6d28d9; --role-bg: #f5f3ff;
  --role-border: #ddd6fe;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --fg: #e5e7eb; --muted: #9ca3af; --border: #2a2e37;
    --card: #171a21; --accent: #7fa8d0; --role: #c4b5fd; --role-bg: #211a36;
    --role-border: #4c3a83;
  }
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 0; padding: 2rem 1.25rem 4rem; line-height: 1.5;
  font-variant-numeric: tabular-nums;
}
.wrap { max-width: min(1400px, 96vw); margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; color: var(--accent); }
.meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 1.5rem; }
.summary {
  display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1.5rem;
  padding: 0.9rem 1.1rem; background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; font-size: 0.9rem;
}
.summary b { font-size: 1.1rem; display: block; }
input.filter {
  width: 100%; padding: 0.55rem 0.8rem; margin-bottom: 1rem; font-size: 0.9rem;
  background: var(--bg); color: var(--fg); border: 1px solid var(--border);
  border-radius: 8px;
}
.table-wrap { max-width: 100%; overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
table.users-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.85rem; }
table.users-table th, table.users-table td {
  text-align: left; padding: 0.5rem 0.7rem; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
table.users-table td.col-roles {
  white-space: normal; min-width: 280px;
}
table.users-table th {
  color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase;
  letter-spacing: 0.02em; background: var(--card); position: sticky; top: 0;
}
table.users-table tr:last-child td { border-bottom: none; }
.role-chip {
  display: inline-block; white-space: nowrap; font-size: 0.78rem; font-weight: 600;
  color: var(--role); background: var(--role-bg); border: 1px solid var(--role-border);
  padding: 0.1rem 0.55rem; border-radius: 999px; margin: 0.1rem 0.2rem 0.1rem 0;
}
.group-chip {
  display: inline-block; white-space: nowrap; font-size: 0.76rem; color: var(--fg);
  background: var(--bg); border: 1px solid var(--border); padding: 0.1rem 0.5rem;
  border-radius: 999px; margin: 0.1rem 0.2rem 0.1rem 0;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.group-chip:hover { background: var(--card); border-color: var(--accent); }
.group-chip.has-purpose { cursor: help; }
.groups-toggle {
  cursor: pointer; color: var(--muted); font-size: 0.82rem; user-select: none;
  display: inline-flex; align-items: center; gap: 0.4rem;
  transition: color 0.15s ease;
}
.groups-toggle:hover, .groups-toggle.open { color: var(--accent); }
.groups-toggle::before {
  content: "\\25b8"; display: inline-block; font-size: 0.7rem;
  transition: transform 0.15s ease; transform-origin: 50% 50%;
}
.groups-toggle.open::before { transform: rotate(90deg); }
table.users-table td.col-groups.open {
  background: var(--card);
  border: 1px solid var(--border); border-bottom: none;
  border-radius: 14px 14px 0 0;
}
tr.groups-row { display: none; }
tr.groups-row.open { display: table-row; }
tr.groups-row td {
  background: var(--card); padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--border);
  white-space: normal;
}
tr.groups-row.open td {
  border: 1px solid var(--border); border-top: none; border-radius: 0 0 14px 14px;
}
tr.row-open td { border-bottom: none; }
.groups-chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
footer { margin-top: 2rem; color: var(--muted); font-size: 0.78rem; }
"""

SCRIPT = """
document.querySelectorAll('.groups-toggle').forEach(function (toggle) {
  toggle.addEventListener('click', function () {
    var mainRow = toggle.closest('tr');
    var row = mainRow.nextElementSibling;
    if (!row || !row.classList.contains('groups-row')) return;
    var open = row.classList.toggle('open');
    toggle.classList.toggle('open', open);
    toggle.closest('td').classList.toggle('open', open);
    mainRow.classList.toggle('row-open', open);
  });
});

document.getElementById('filter').addEventListener('input', function () {
  var q = this.value.toLowerCase();
  document.querySelectorAll('table.users-table tbody > tr:not(.groups-row)').forEach(function (row) {
    var groupsRow = row.nextElementSibling && row.nextElementSibling.classList.contains('groups-row')
      ? row.nextElementSibling : null;
    var groupsText = groupsRow ? groupsRow.textContent.toLowerCase() : '';
    var groupsMatches = q !== '' && groupsText.includes(q);
    var rowMatches = q === '' || row.textContent.toLowerCase().includes(q) || groupsMatches;
    row.style.display = rowMatches ? '' : 'none';
    if (!groupsRow) return;
    // Hidden along with its main row regardless of open/closed state; open
    // state itself is left untouched by filtering, whether the match came
    // from the groups list or elsewhere on the row.
    groupsRow.style.display = rowMatches ? '' : 'none';
  });
});
"""


def load_users_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_purposes(path):
    """Build a {full_name: purpose} lookup from the sibling access-rights-groups
    skill's known_groups.yaml. Odoo's own res.groups.full_name is computed as
    "category / name" (or just "name" when there's no category), so the same
    shape is reconstructed here from each entry's category/also_category x
    name/also_named combinations - no xml_id plumbing needed since list_users.py
    already exports full_name, and full_name is exactly what a rendered chip's
    text is."""
    data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8")) or {}
    lookup = {}
    for entry in data.values():
        purpose = entry.get("purpose")
        if not purpose:
            continue
        names = [entry["name"], *entry.get("also_named", [])]
        cats = [entry["category"]] if entry.get("category") else []
        cats += entry.get("also_category", [])
        for name in names:
            if cats:
                for cat in cats:
                    lookup[f"{cat} / {name}"] = purpose
            else:
                lookup[name] = purpose
    return lookup


def render_cell(column, value):
    if column == "roles" and value:
        chips = "".join(f'<span class="role-chip">{html.escape(r.strip())}</span>' for r in value.split("|") if r.strip())
        return chips or html.escape(value)
    if column == "groups":
        groups = [g.strip() for g in (value or "").split("|") if g.strip()]
        if not groups:
            return html.escape(value or "")
        n = len(groups)
        return f'<span class="groups-toggle">{n} group{"s" if n != 1 else ""}</span>'
    return html.escape(value or "")


def render_groups_row(value, ncols, purposes):
    """A group list is rendered as its own full-width row directly below
    the user's main row (colspan across every column), not squeezed into
    the narrow groups cell - a user can hold dozens of groups, and cramming
    that into one column's width wraps every chip's own text instead of
    wrapping between chips, which is unreadable. Hidden by default (see
    tr.groups-row CSS) - the toggle in the main row's groups cell reveals
    it. Returns "" when there's nothing to show, so no empty row gets
    emitted. Each chip gets a native `title` tooltip with its purpose when
    the group is found in the known_groups.yaml lookup - a plain HTML
    attribute rather than a custom tooltip widget, since it's free
    (accessible, no positioning/JS to get wrong) and this is a report meant
    to be scanned, not a polished app UI."""
    groups = [g.strip() for g in (value or "").split("|") if g.strip()]
    if not groups:
        return ""
    chips = "".join(
        f'<span class="group-chip{" has-purpose" if g in purposes else ""}"'
        + (f' title="{html.escape(purposes[g])}"' if g in purposes else "")
        + f">{html.escape(g)}</span>"
        for g in groups
    )
    return f'<tr class="groups-row"><td colspan="{ncols}"><div class="groups-chips">{chips}</div></td></tr>'


def render_table(rows, purposes):
    if not rows:
        return '<p class="meta">No users matched.</p>'
    cols = list(rows[0].keys())
    ncols = len(cols)
    header = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body_rows = "".join(
        "<tr>" + "".join(
            f'<td class="col-{html.escape(c)}">{render_cell(c, r.get(c))}</td>' for c in cols
        ) + "</tr>"
        + (render_groups_row(r.get("groups"), ncols, purposes) if "groups" in cols else "")
        for r in rows
    )
    return f"""
    <div class="table-wrap">
      <table class="users-table">
        <thead><tr>{header}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>"""


@click.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="CSV produced by list_users.py --format csv.")
@click.option("--output", "output_path", required=True, type=click.Path(dir_okay=False),
              help="Path to write the HTML report to.")
@click.option("--title", default=None, help="Report title (default: 'Users Report').")
@click.option("--env", default=None, help="Environment label shown in the meta line (purely cosmetic - just a label, doesn't reconnect to anything).")
@click.option("--purposes", "purposes_paths", multiple=True, type=click.Path(exists=True, dir_okay=False),
              help="A known_groups.yaml-shaped file (the sibling access-rights-groups skill's own "
                   "known_groups.yaml for native groups, and/or a project-local file from "
                   "write_project_group_purposes.py for that project's custom groups). Repeatable - pass it "
                   "once per file to merge purposes from several sources. When given, hovering a group chip "
                   "shows its purpose as a tooltip. Optional - groups render as plain chips without it.")
def run(input_path, output_path, title, env, purposes_paths):
    """Render a list_users.py CSV export as a standalone HTML report."""
    rows = load_users_csv(input_path)
    purposes = {}
    for path in purposes_paths:
        purposes.update(load_purposes(path))

    report_title = title or "Users Report"
    meta_parts = [html.escape(env)] if env else []
    meta_parts.append("generated by generate_users_report.py (list-users skill)")
    meta_parts.append(f"data as of {date.today().isoformat()}")
    meta = " &middot; ".join(meta_parts)

    doc = f"""<meta charset="utf-8"/>
<title>{html.escape(report_title)}</title>
<style>{CSS}</style>

<div class="wrap">
  <h1>{html.escape(report_title)}</h1>
  <div class="meta">{meta}</div>

  <div class="summary">
    <div><b>{len(rows)}</b> users</div>
  </div>

  <input class="filter" id="filter" type="text" placeholder="Filter by login, name, or role...">
{render_table(rows, purposes)}

  <footer>Source: {html.escape(pathlib.Path(input_path).name)}</footer>
</div>
<script>{SCRIPT}</script>
"""

    pathlib.Path(output_path).write_text(doc, encoding="utf-8")
    click.echo(f"{len(rows)} users")
    click.echo(f"Report written to {output_path}")


if __name__ == "__main__":
    run()
