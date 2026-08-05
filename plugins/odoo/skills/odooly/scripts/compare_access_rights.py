#!/usr/bin/env python3
"""
Compare access rights (ACL, record rules, groups, user groups, user roles)
between two Odoo environments.

Usage:
    python compare_access_rights.py -c ~/odooly.ini --env-a ENV_A --env-b ENV_B [OPTIONS]

Examples:
    # Compare everything, only show differences, filter out core module records
    python compare_access_rights.py -c ~/odooly.ini --env-a staging --env-b production

    # Include core (base/mail/...) ACL and rules too
    python compare_access_rights.py -c ~/odooly.ini --env-a staging --env-b production --include-core

    # Only compare ir.model.access and ir.rule, restricted to one model
    python compare_access_rights.py -c ~/odooly.ini --env-a staging --env-b production \
        --types access,rule --model sale.order

    # CSV output to a file
    python compare_access_rights.py -c ~/odooly.ini --env-a staging --env-b production \
        --format csv --output diff.csv
"""

import csv
import pathlib
import sys

import click
import odooly
from manifestoo_core.core_addons import is_core_ce_addon, is_core_ee_addon
from manifestoo_core.odoo_series import OdooSeries


# Separator used to join a user's group names into a single CSV field
# (fetch_user_groups). Group full_name can itself contain a comma (e.g.
# "View Member SmartButton (Account Analytic, Archive)"), so joining/splitting
# on ", " is ambiguous. " | " is far less likely to collide and is what
# generate_html_report.py expects when it splits this field back into a list.
GROUP_LIST_SEP = " | "


def get_odoo_series(client):
    major_minor = f"{int(client.version_info)}.0"
    return OdooSeries(major_minor)


def build_xmlid_map(client, model_name, res_ids):
    """Return {res_id: set(xmlids)} for the given ids of a model."""
    res_ids = [i for i in res_ids if i]
    if not res_ids:
        return {}
    Data = client.env["ir.model.data"]
    recs = Data.search([("model", "=", model_name), ("res_id", "in", res_ids)])
    result = {}
    for r in recs.read(["module", "name", "res_id"]):
        xmlid = f"{r['module']}.{r['name']}"
        result.setdefault(r["res_id"], set()).add(xmlid)
    return result


def make_item(res_id, xmlid_map, natural_key, fields, display=None):
    return {
        "res_id": res_id,
        "xmlids": xmlid_map.get(res_id, set()),
        "natural_key": natural_key,
        "fields": fields,
        "display": display if display is not None else str(natural_key),
    }


def batch_read(client, model, ids, field):
    """Read `field` for a batch of ids of `model`. Returns {id: value}."""
    ids = list(ids)
    if not ids:
        return {}
    return {r["id"]: r[field] for r in client.env[model].browse(ids).read([field])}


# --- Fetchers -------------------------------------------------------------
# Each fetcher returns a list of "items" (see make_item). It never fetches
# related field values (names) one record at a time; it collects all the
# referenced ids first and resolves them in a single batched read, to avoid
# an N+1 RPC round-trip pattern on large models like ir.model.access.

def fetch_groups(client, model_filter=None, **kwargs):
    Group = client.env["res.groups"]
    records = Group.search([])
    raw = records.read(["full_name", "category_id"])
    xmlid_map = build_xmlid_map(client, "res.groups", [r["id"] for r in raw])

    items = []
    for r in raw:
        category = r["category_id"]
        fields = {
            "full_name": r["full_name"],
            "category": category.name if category else "",
        }
        items.append(make_item(r["id"], xmlid_map, r["full_name"], fields, display=r["full_name"]))
    return items


def fetch_access(client, model_filter=None, **kwargs):
    Access = client.env["ir.model.access"]
    domain = [("model_id.model", "=", model_filter)] if model_filter else []
    records = Access.search(domain)
    raw = records.read(["name", "model_id", "group_id", "perm_read", "perm_write", "perm_create", "perm_unlink"])
    xmlid_map = build_xmlid_map(client, "ir.model.access", [r["id"] for r in raw])

    model_ids = {r["model_id"].id for r in raw if r["model_id"]}
    group_ids = {r["group_id"].id for r in raw if r["group_id"]}
    model_name = batch_read(client, "ir.model", model_ids, "model")
    group_name = batch_read(client, "res.groups", group_ids, "full_name")

    items = []
    for r in raw:
        model = model_name.get(r["model_id"].id, "(no model)") if r["model_id"] else "(no model)"
        group = group_name.get(r["group_id"].id, "(no group / all users)") if r["group_id"] else "(no group / all users)"
        natural_key = (model, group, r["name"])
        fields = {
            "model": model,
            "group": group,
            "perm_read": r["perm_read"],
            "perm_write": r["perm_write"],
            "perm_create": r["perm_create"],
            "perm_unlink": r["perm_unlink"],
        }
        items.append(make_item(r["id"], xmlid_map, natural_key, fields, display=f"{model} / {group} ({r['name']})"))
    return items


def fetch_rules(client, model_filter=None, **kwargs):
    Rule = client.env["ir.rule"]
    domain = [("model_id.model", "=", model_filter)] if model_filter else []
    records = Rule.search(domain)
    raw = records.read(["name", "model_id", "groups", "domain_force", "active"])
    xmlid_map = build_xmlid_map(client, "ir.rule", [r["id"] for r in raw])

    model_ids = {r["model_id"].id for r in raw if r["model_id"]}
    group_ids = set()
    for r in raw:
        group_ids.update(r["groups"].ids)
    model_name = batch_read(client, "ir.model", model_ids, "model")
    group_name = batch_read(client, "res.groups", group_ids, "full_name")

    items = []
    for r in raw:
        model = model_name.get(r["model_id"].id, "(no model)") if r["model_id"] else "(no model)"
        groups = sorted(group_name.get(gid, str(gid)) for gid in r["groups"].ids)
        natural_key = (model, r["name"])
        fields = {
            "model": model,
            "groups": ", ".join(groups) if groups else "(global)",
            "domain_force": r["domain_force"] or "",
            "active": r["active"],
        }
        items.append(make_item(r["id"], xmlid_map, natural_key, fields, display=f"{model} / {r['name']}"))
    return items


def fetch_user_groups(client, model_filter=None, include_archived_users=False, **kwargs):
    User = client.env["res.users"]
    domain = [("share", "=", False)]
    if include_archived_users:
        # Odoo's search() implicitly filters active=True; without this, archived
        # (inactive) users are silently excluded from the comparison and show up
        # as spurious "missing" rows instead of being recognized as archived.
        domain.append(("active", "in", [True, False]))
    records = User.search(domain)
    raw = records.read(["login", "groups_id"])

    group_ids = set()
    for r in raw:
        group_ids.update(r["groups_id"].ids)
    group_name = batch_read(client, "res.groups", group_ids, "full_name")

    items = []
    for r in raw:
        groups = sorted(group_name.get(gid, str(gid)) for gid in r["groups_id"].ids)
        fields = {"groups": GROUP_LIST_SEP.join(groups)}
        items.append({
            "res_id": None,
            "xmlids": set(),  # matched by login only, no XML ID for users
            "natural_key": r["login"],
            "fields": fields,
            "display": r["login"],
        })
    return items


def fetch_role_lines(client, model_filter=None, **kwargs):
    """Compare res.users.role.line (OCA base_user_role), if installed."""
    try:
        RoleLine = client.env["res.users.role.line"]
        records = RoleLine.search([])
        raw = records.read(["user_id", "role_id", "is_enabled"])
    except Exception:
        return []

    user_ids = {r["user_id"].id for r in raw if r["user_id"]}
    role_ids = {r["role_id"].id for r in raw if r["role_id"]}
    user_login = batch_read(client, "res.users", user_ids, "login")
    role_name = batch_read(client, "res.users.role", role_ids, "name")

    items = []
    for r in raw:
        # is_enabled looked non-stored/unreliable to filter via domain during
        # exploration (search domain on it returned all records), so filter
        # in Python instead, after reading the real value.
        if not r["is_enabled"]:
            continue
        login = user_login.get(r["user_id"].id, "(no user)") if r["user_id"] else "(no user)"
        role = role_name.get(r["role_id"].id, "(no role)") if r["role_id"] else "(no role)"
        natural_key = (login, role)
        items.append({
            "res_id": r["id"],
            "xmlids": set(),  # runtime records, no XML ID
            "natural_key": natural_key,
            "fields": {"role": role},
            "display": f"{login} / {role}",
        })
    return items


FETCHERS = {
    "access": fetch_access,
    "rule": fetch_rules,
    "groups": fetch_groups,
    "users": fetch_user_groups,
    "roles": fetch_role_lines,
}


# --- Core-module filtering --------------------------------------------------

def is_core_item(item, odoo_series):
    for xmlid in item["xmlids"]:
        module = xmlid.split(".", 1)[0]
        if is_core_ce_addon(module, odoo_series) or is_core_ee_addon(module, odoo_series):
            return True
    return False


def filter_core(items, odoo_series, include_core):
    if include_core:
        return items
    return [item for item in items if not is_core_item(item, odoo_series)]


# --- Comparison --------------------------------------------------------------

def find_duplicate_natural_keys(items):
    """Return {natural_key: (count, display)} for natural keys shared by 2+ items.

    compare_items() matches records by natural_key via a dict, so duplicates
    silently collapse (last one wins on the B side; on the A side, every
    duplicate matches the same single B record) without ever being reported.
    This surfaces them explicitly instead.
    """
    counts = {}
    displays = {}
    for item in items:
        key = item["natural_key"]
        counts[key] = counts.get(key, 0) + 1
        displays.setdefault(key, item["display"])
    return {key: (count, displays[key]) for key, count in counts.items() if count > 1}


def compare_items(items_a, items_b, item_type, full=False):
    xmlid_index_b = {}
    natural_index_b = {}
    for item in items_b:
        for xid in item["xmlids"]:
            xmlid_index_b[xid] = item
        natural_index_b[item["natural_key"]] = item

    matched_b = set()
    diffs = []

    for _key, (count, display) in find_duplicate_natural_keys(items_a).items():
        diffs.append({
            "type": item_type, "key": display, "field": "(duplicate)",
            "value_a": f"appears {count} times", "value_b": "", "status": "duplicate_in_a",
        })
    for _key, (count, display) in find_duplicate_natural_keys(items_b).items():
        diffs.append({
            "type": item_type, "key": display, "field": "(duplicate)",
            "value_a": "", "value_b": f"appears {count} times", "status": "duplicate_in_b",
        })

    for item_a in items_a:
        match = None
        for xid in item_a["xmlids"]:
            if xid in xmlid_index_b:
                match = xmlid_index_b[xid]
                break
        if match is None:
            match = natural_index_b.get(item_a["natural_key"])

        if match is None:
            diffs.append({
                "type": item_type, "key": item_a["display"], "field": "(record)",
                "value_a": "present", "value_b": "", "status": "missing_in_b",
            })
            continue

        matched_b.add(id(match))
        for field, value_a in item_a["fields"].items():
            value_b = match["fields"].get(field)
            if value_a != value_b:
                diffs.append({
                    "type": item_type, "key": item_a["display"], "field": field,
                    "value_a": value_a, "value_b": value_b, "status": "different",
                })
            elif full:
                diffs.append({
                    "type": item_type, "key": item_a["display"], "field": field,
                    "value_a": value_a, "value_b": value_b, "status": "same",
                })

    for item_b in items_b:
        if id(item_b) not in matched_b:
            diffs.append({
                "type": item_type, "key": item_b["display"], "field": "(record)",
                "value_a": "", "value_b": "present", "status": "missing_in_a",
            })

    return diffs


# --- Output ------------------------------------------------------------------

COLUMNS = ["type", "key", "field", "value_a", "value_b", "status"]
COLUMN_WIDTHS = {"type": 8, "key": 55, "field": 14, "value_a": 22, "value_b": 22, "status": 14}


def render(diffs, fmt, output):
    if fmt == "csv":
        out = open(output, "w", newline="") if output else sys.stdout
        try:
            writer = csv.writer(out)
            writer.writerow(COLUMNS)
            for d in diffs:
                writer.writerow([d[c] for c in COLUMNS])
        finally:
            if output:
                out.close()
        return

    lines = []
    header = "  ".join(f"{c.capitalize():<{COLUMN_WIDTHS[c]}}" for c in COLUMNS)
    lines.append(header)
    lines.append("-" * len(header))
    for d in diffs:
        lines.append("  ".join(f"{str(d[c]):<{COLUMN_WIDTHS[c]}}" for c in COLUMNS))
    lines.append(f"\nTotal: {len(diffs)} rows")
    text = "\n".join(lines)
    if output:
        pathlib.Path(output).write_text(text + "\n")
    else:
        click.echo(f"\n{text}")


# --- CLI -----------------------------------------------------------------

@click.command()
@click.option("-c", "--config", default="odooly.ini", help="Specify alternate config file (default: odooly.ini).")
@click.option("--env-a", required=True, help="First odooly environment name.")
@click.option("--env-b", required=True, help="Second odooly environment name.")
@click.option("--types", default="access,rule,groups,users,roles",
              help="Comma-separated types to compare: access,rule,groups,users,roles.")
@click.option("--model", "model_filter", default=None, help="Restrict access/rule comparison to one model (technical name).")
@click.option("--include-core", is_flag=True, default=False, help="Include ACL/rules belonging to core CE/EE modules (default: excluded).")
@click.option("--include-archived-users", is_flag=True, default=False,
              help="Include archived (inactive) users in the 'users' comparison (default: excluded, like Odoo's own default search).")
@click.option("--format", "fmt", type=click.Choice(["table", "csv"]), default="table", help="Output format (default: table).")
@click.option("--full", is_flag=True, default=False, help="Also show fields that are identical, not just differences.")
@click.option("--output", default=None, type=click.Path(), help="Write output to a file instead of stdout.")
def run(config, env_a, env_b, types, model_filter, include_core, include_archived_users, fmt, full, output):
    """Compare access rights between two Odoo environments."""
    odooly.Client._config_file = pathlib.Path(config).expanduser()
    client_a = odooly.Client.from_config(env_a)
    client_b = odooly.Client.from_config(env_b)

    is_csv = fmt == "csv"
    if not is_csv:
        click.echo(f"env_a: {env_a} (db={client_a.env.db_name}, {client_a.server_version})")
        click.echo(f"env_b: {env_b} (db={client_b.env.db_name}, {client_b.server_version})")

    series_a = get_odoo_series(client_a)
    series_b = get_odoo_series(client_b)

    selected_types = [t.strip() for t in types.split(",") if t.strip()]
    for t in selected_types:
        if t not in FETCHERS:
            raise click.BadParameter(f"Unknown type '{t}'. Available: {','.join(FETCHERS)}")

    all_diffs = []
    for t in selected_types:
        fetcher = FETCHERS[t]
        items_a = filter_core(fetcher(client_a, model_filter, include_archived_users=include_archived_users), series_a, include_core)
        items_b = filter_core(fetcher(client_b, model_filter, include_archived_users=include_archived_users), series_b, include_core)
        diffs = compare_items(items_a, items_b, t, full=full)
        all_diffs.extend(diffs)
        if not is_csv:
            click.echo(f"{t}: {len(items_a)} in env_a, {len(items_b)} in env_b, {len(diffs)} rows")

    render(all_diffs, fmt, output)


if __name__ == "__main__":
    run()
