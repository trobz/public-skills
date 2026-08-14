#!/usr/bin/env python3
"""
List Odoo users from an environment, defaulting to active users that have
at least one currently-enabled role from the OCA `base_user_role` module.

Both defaults are meant to match what "who's actually using the system
under the roles model" means in practice: an inactive (archived) user isn't
using anything, and a user with no role assigned yet isn't managed by the
roles model at all - showing them by default would bury the users the
roles model actually governs under everyone else. Both are switches, not
hardcoded, for whoever needs the fuller picture (e.g. auditing who's
*missing* a role - see --include-no-role).

`res.users.role.line`'s `is_enabled` is a computed field reflecting
whether *today* falls inside that role assignment's From/To date window -
computed, not stored, so it's read per-record in Python rather than
filtered via a search domain (a domain on it silently returns every
record, not just the enabled ones - seen firsthand exploring this same
model in compare_access_rights.py's fetch_role_lines()).

Usage:
    python list_users.py -c ~/odooly.ini --env ENV [OPTIONS]

Examples:
    # Active users with a currently-enabled role (the default)
    python list_users.py -c ~/odooly.ini --env production

    # Every active user, role or not - e.g. to find who's missing one
    python list_users.py -c ~/odooly.ini --env production --include-no-role

    # Everyone, active or archived, role or not
    python list_users.py -c ~/odooly.ini --env production --include-inactive --include-no-role

    # CSV, custom columns
    python list_users.py -c ~/odooly.ini --env production --format csv --columns login,name,roles,email
"""

import csv
import pathlib
import sys

import click
import odooly

AVAILABLE_COLUMNS = ["login", "name", "email", "active", "roles", "groups"]

COLUMN_TO_FIELD = {
    "login": "login",
    "name": "name",
    "email": "email",
    "active": "active",
    "roles": None,  # computed from res.users.role.line
    "groups": None,  # computed from res.users.groups_id
}

COLUMN_WIDTHS = {
    "login": 30,
    "name": 25,
    "email": 30,
    "active": 8,
    "roles": 40,
    "groups": 60,
}

ROLE_SEP = " | "
GROUP_SEP = " | "


def fetch_enabled_roles_by_user(client):
    """Return {user_id: [role_name, ...]} from res.users.role.line, only the
    lines whose is_enabled is True right now. Raises if base_user_role isn't
    installed (no res.users.role.line model) - the caller decides how to
    handle that, since it means "no user anywhere has a role", not "zero
    role lines happened to match a filter"."""
    RoleLine = client.env["res.users.role.line"]
    records = RoleLine.search([])
    raw = records.read(["user_id", "role_id", "is_enabled"])

    role_ids = {r["role_id"].id for r in raw if r["role_id"]}
    Role = client.env["res.users.role"]
    role_name = {r["id"]: r["name"] for r in Role.browse(list(role_ids)).read(["name"])} if role_ids else {}

    by_user = {}
    for r in raw:
        if not r["is_enabled"] or not r["user_id"]:
            continue
        role = role_name.get(r["role_id"].id, "(no role)") if r["role_id"] else "(no role)"
        by_user.setdefault(r["user_id"].id, []).append(role)
    return by_user


def fetch_groups_by_user(client, records):
    """Return {user_id: [group_full_name, ...]} for exactly the given user
    records (each must already have `groups_id` in it, from a prior
    .read()). Resolves via one batched read of res.groups.full_name - same
    pattern as the sibling odooly skill's compare_access_rights.py ->
    fetch_user_groups() (not imported, each skill stays self-contained, but
    the same "batch-resolve ids, never one at a time" shape)."""
    group_ids = set()
    for r in records:
        group_ids.update(r["groups_id"].ids)
    if not group_ids:
        return {}
    Group = client.env["res.groups"]
    group_name = {g["id"]: g["full_name"] for g in Group.browse(list(group_ids)).read(["full_name"])}
    return {r["id"]: sorted(group_name.get(gid, str(gid)) for gid in r["groups_id"].ids) for r in records}


def get_column_value(record, column, roles_by_user, groups_by_user):
    if column == "roles":
        return ROLE_SEP.join(sorted(roles_by_user.get(record["id"], [])))
    if column == "groups":
        return GROUP_SEP.join(groups_by_user.get(record["id"], []))
    if column == "active":
        return "yes" if record.get("active") else "no"
    field = COLUMN_TO_FIELD[column]
    return record.get(field) or ""


@click.command()
@click.option("-c", "--config", default="odooly.ini", help="Specify alternate config file (default: odooly.ini).")
@click.option("--env", required=True, help="Odooly environment name from config.")
@click.option("--include-inactive", is_flag=True, default=False, help="Include archived (active=False) users too (default: active only).")
@click.option("--include-no-role", is_flag=True, default=False, help="Include users with no currently-enabled base_user_role role too (default: role-holders only).")
@click.option("--format", "fmt", type=click.Choice(["table", "csv"]), default="table", help="Output format (default: table).")
@click.option("--columns", default="login,name,roles", help=f"Comma-separated columns to display. Available: {','.join(AVAILABLE_COLUMNS)}")
@click.option("--output", default=None, type=click.Path(), help="Write output to a file instead of stdout.")
def run(config, env, include_inactive, include_no_role, fmt, columns, output):
    """List Odoo users, defaulting to active users with a currently-enabled base_user_role role."""
    odooly.Client._config_file = pathlib.Path(config).expanduser()
    client = odooly.Client.from_config(env)

    is_csv = fmt == "csv"
    if not is_csv:
        click.echo(f"Connected to environment: {env}")
        click.echo(f"Database: {client.env.db_name}")

    cols = [c.strip() for c in columns.split(",")]
    for c in cols:
        if c not in AVAILABLE_COLUMNS:
            raise click.BadParameter(f"Unknown column '{c}'. Available: {','.join(AVAILABLE_COLUMNS)}")

    try:
        roles_by_user = fetch_enabled_roles_by_user(client)
    except Exception:
        if not include_no_role:
            raise click.UsageError(
                "res.users.role.line not found - base_user_role doesn't look installed on this "
                "environment, so no user has a role by definition. Pass --include-no-role to list "
                "users anyway (roles column will just be empty for everyone)."
            )
        roles_by_user = {}

    Users = client.env["res.users"]
    if include_inactive:
        Users = Users.with_context(active_test=False)
        domain = []
    else:
        domain = [("active", "=", True)]
    users = Users.search(domain)
    fields_to_read = {"id", "login"} | {COLUMN_TO_FIELD[c] for c in cols if COLUMN_TO_FIELD.get(c)}
    if "groups" in cols:
        fields_to_read.add("groups_id")
    records = users.read(list(fields_to_read))

    if not include_no_role:
        records = [r for r in records if roles_by_user.get(r["id"])]

    records.sort(key=lambda r: r["login"])

    # Resolve group names only for the users actually being shown, and only
    # when the column was asked for - groups_id can be dozens of ids per
    # user, no point reading and resolving it for a population it'll never
    # be displayed for.
    groups_by_user = fetch_groups_by_user(client, records) if "groups" in cols else {}

    if fmt == "csv":
        out = open(output, "w", newline="") if output else sys.stdout
        try:
            writer = csv.writer(out)
            writer.writerow(cols)
            for r in records:
                writer.writerow([get_column_value(r, c, roles_by_user, groups_by_user) for c in cols])
        finally:
            if output:
                out.close()
    else:
        header = "  ".join(f"{c.capitalize():<{COLUMN_WIDTHS.get(c, 20)}}" for c in cols)
        click.echo(f"\n{header}")
        click.echo("-" * len(header))
        for r in records:
            row = "  ".join(
                f"{str(get_column_value(r, c, roles_by_user, groups_by_user)):<{COLUMN_WIDTHS.get(c, 20)}}"
                for c in cols
            )
            click.echo(row)
        click.echo(f"\nTotal: {len(records)} users")


if __name__ == "__main__":
    run()
