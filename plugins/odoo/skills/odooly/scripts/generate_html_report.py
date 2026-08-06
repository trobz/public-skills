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
"""

import csv
import html
import pathlib
from datetime import date

import click

# Must match GROUP_LIST_SEP in compare_access_rights.py's fetch_user_groups().
DEFAULT_GROUP_SEP = " | "


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
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --fg: #e5e7eb; --muted: #9ca3af; --border: #2a2e37;
    --card: #171a21; --added: #34d399; --added-bg: #052e22;
    --removed: #f87171; --removed-bg: #2c1315; --accent: #7fa8d0;
    --critical-bg: #2c1315; --critical-border: #7f1d1d;
    --role: #c4b5fd; --role-bg: #211a36; --role-border: #4c3a83;
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


def render_group_col(title, items, css_class):
    if not items:
        return f'<div class="col"><h4>{html.escape(title)} (0)</h4><div class="empty">none</div></div>'
    lis = "".join(f'<li class="{css_class}">{html.escape(g)}</li>' for g in items)
    return f'<div class="col"><h4>{html.escape(title)} ({len(items)})</h4><ul class="grouplist">{lis}</ul></div>'


def render_user_block(login, before, after, roles):
    added = sorted(after - before)
    removed = sorted(before - after)
    critical = bool(before) and not after
    css_classes = "user critical" if critical else "user"
    badge = '<span class="badge critical">ALL ACCESS REMOVED</span>' if critical else ""
    roles_panel = render_roles_panel(roles)
    added_col = render_group_col("Added", added, "g-added")
    removed_col = render_group_col("Removed", removed, "g-removed")
    return f"""    <details class="{css_classes}">
      <summary>
        <span class="login">{html.escape(login)}</span>
        <span class="counts">{len(before)} &rarr; {len(after)} groups &nbsp; <span class="added-count">+{len(added)}</span> <span class="removed-count">-{len(removed)}</span></span>
        {badge}
      </summary>
      <div class="body">
        {roles_panel}
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
def run(input_path, output_path, title, env_a, env_b, group_sep):
    """Render a compare_access_rights.py CSV export as a per-user HTML report."""
    rows = load_rows(input_path)

    users, missing_users, warnings = build_user_diffs(rows, group_sep)
    roles_by_user = build_user_roles(rows)

    for w in warnings:
        click.echo(f"warning: {w}", err=True)

    logins = sorted(users)
    critical_count = sum(1 for login in logins if users[login]["before"] and not users[login]["after"])
    partial_count = len(logins) - critical_count

    blocks = "".join(
        render_user_block(login, users[login]["before"], users[login]["after"], roles_by_user.get(login, []))
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
