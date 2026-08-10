#!/usr/bin/env python3
"""
Discover res.groups (Access Rights groups) live on one Odoo instance via
odooly, and optionally sync the native ones into known_groups.yaml.

This is the live-instance counterpart to extract_native_groups.py (which
reads local CE/EE source across versions instead). Use this script when you
want:
  - the exact groups actually present/installed on ONE real project
    (--include-project-groups mode in generate_roles_doc.py relies on this),
  - or to confirm/extend known_groups.yaml's versions_seen against a real
    running instance rather than static source.

known_groups.yaml only ever stores NATIVE Odoo groups - a project's own
custom/OCA groups have no local source this skill can read, so there is
nowhere to look up their purpose from except the live database itself. Pass
--evidence to fetch, for each group, which models it has ir.model.access
entries on (with read/write/create/unlink) and which menus it gates - the
same kind of evidence extract_native_groups.py reads from source XML, just
sourced from the live instance instead. This does not write a purpose; it
gives you (or an LLM) what's needed to write one accurately.

--sync-known-list always refreshes `name`/`category`/`module`/`ce_or_ee`
from live data and appends to `versions_seen` - this is the intended way
known_groups.yaml stays current as new projects/instances confirm it over
the years. Since known_groups.yaml is a catalog meant to be shared and
pushed for everyone, don't point --sync-known-list at it directly while
just testing against a one-off instance whose data you're not ready to
commit - sync into a separate local file instead, and only merge into
known_groups.yaml once you actually mean to contribute that data back.

Usage:
    python discover_groups.py -c ~/odooly.ini --env ENV [--all] [--format table|csv|yaml]
    python discover_groups.py -c ~/odooly.ini --env ENV --sync-known-list known_groups.yaml [--dry-run]
    python discover_groups.py -c ~/odooly.ini --env ENV --all --evidence --format yaml
"""

import csv
import pathlib
import sys

import click
import odooly
import yaml
from manifestoo_core.core_addons import is_core_ce_addon, is_core_ee_addon
from manifestoo_core.odoo_series import OdooSeries

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _known_list import TODO_PURPOSE, bare_name, write_known_list  # noqa: E402


def get_odoo_series(client):
    major_minor = f"{int(client.version_info)}.0"
    return OdooSeries(major_minor)


def build_xmlid_map(client, model_name, res_ids):
    """Return {res_id: xmlid} for the given ids of a model (first xmlid found wins)."""
    res_ids = [i for i in res_ids if i]
    if not res_ids:
        return {}
    Data = client.env["ir.model.data"]
    recs = Data.search([("model", "=", model_name), ("res_id", "in", res_ids)])
    result = {}
    for r in recs.read(["module", "name", "res_id"]):
        result.setdefault(r["res_id"], f"{r['module']}.{r['name']}")
    return result


def classify(xmlid, odoo_series):
    if xmlid is None:
        return None  # no xml_id at all - can't classify, treat as neither
    module = xmlid.split(".", 1)[0]
    if is_core_ce_addon(module, odoo_series):
        return "community"
    if is_core_ee_addon(module, odoo_series):
        return "enterprise"
    return "custom"  # OCA or project-specific


def fetch_groups(client, odoo_series):
    Group = client.env["res.groups"]
    records = Group.search([])
    raw = records.read(["full_name", "category_id", "comment", "implied_ids"])
    xmlid_map = build_xmlid_map(client, "res.groups", [r["id"] for r in raw])

    implied_ids = {i for r in raw for i in r["implied_ids"].ids}
    implied_names = {}
    if implied_ids:
        implied_names = {
            r["id"]: r["full_name"] for r in client.env["res.groups"].browse(list(implied_ids)).read(["full_name"])
        }

    rows = []
    for r in raw:
        xmlid = xmlid_map.get(r["id"])
        rows.append(
            {
                "id": r["id"],
                "xml_id": xmlid or "(no xml_id)",
                "full_name": r["full_name"],
                "category": r["category_id"].name if r["category_id"] else "",
                "comment": (r["comment"] or "").strip(),
                "implied_by": ", ".join(implied_names.get(i, str(i)) for i in r["implied_ids"].ids),
                "origin": classify(xmlid, odoo_series),
            }
        )
    return rows


def fetch_access_evidence(client, group_ids):
    """Return {group_id: ["model.name (rwcu)", ...]} from ir.model.access."""
    Access = client.env["ir.model.access"]
    raw = Access.search([("group_id", "in", group_ids)]).read(
        ["group_id", "model_id", "perm_read", "perm_write", "perm_create", "perm_unlink"]
    )
    model_ids = {r["model_id"].id for r in raw if r["model_id"]}
    model_names = {}
    if model_ids:
        model_names = {
            r["id"]: r["model"] for r in client.env["ir.model"].browse(list(model_ids)).read(["model"])
        }

    result = {}
    for r in raw:
        if not r["model_id"]:
            continue
        model = model_names.get(r["model_id"].id, str(r["model_id"].id))
        flags = "".join(
            f for f, on in (("r", r["perm_read"]), ("w", r["perm_write"]), ("c", r["perm_create"]), ("u", r["perm_unlink"])) if on
        )
        result.setdefault(r["group_id"].id, []).append(f"{model} ({flags or 'none'})")
    for gid in result:
        result[gid].sort()
    return result


def fetch_menu_evidence(client, group_ids):
    """Return {group_id: ["Menu > Path", ...]} for menus gated by each group."""
    Menu = client.env["ir.ui.menu"]
    raw = Menu.search([("groups_id", "in", group_ids)]).read(["complete_name", "groups_id"])
    result = {}
    for r in raw:
        for gid in r["groups_id"].ids:
            if gid in group_ids:
                result.setdefault(gid, []).append(r["complete_name"])
    for gid in result:
        result[gid].sort()
    return result


def print_table(rows, columns):
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) if rows else len(c) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    click.echo(header)
    click.echo("  ".join("-" * widths[c] for c in columns))
    for r in rows:
        click.echo("  ".join(str(r[c]).ljust(widths[c]) for c in columns))


def sync_known_list(rows, known_path, odoo_series, dry_run):
    known = {}
    if known_path.exists():
        known = yaml.safe_load(known_path.read_text()) or {}

    version = odoo_series.value
    native_rows = [r for r in rows if r["origin"] in ("community", "enterprise") and r["xml_id"] != "(no xml_id)"]
    seen_xmlids = {r["xml_id"] for r in native_rows}

    added, version_updates = 0, 0
    for r in native_rows:
        entry = known.setdefault(r["xml_id"], {})
        is_new = "name" not in entry and "module" not in entry
        # r["full_name"] is Odoo's own "Category / Name" combined display
        # string - strip the category prefix so `name` stays bare, matching
        # every other writer of this file (never store the combined form).
        # Always refreshed from live data, same as module/ce_or_ee - this is
        # the intended way known_groups.yaml stays current over the years.
        # If you're syncing a one-off/test instance and don't want its data
        # merged into the shared known_groups.yaml before you're ready to
        # commit it, point --sync-known-list at a separate local file
        # instead - don't run it against known_groups.yaml itself until you
        # mean to.
        entry["name"] = bare_name(r["full_name"], r["category"])
        if r["category"]:
            entry["category"] = r["category"]
        entry["module"] = r["xml_id"].split(".", 1)[0]
        entry["ce_or_ee"] = r["origin"]
        if r["comment"] and not entry.get("purpose"):
            entry["purpose"] = r["comment"]
        entry.setdefault("purpose", TODO_PURPOSE)
        entry.setdefault("versions_seen", [])
        if version not in entry["versions_seen"]:
            entry["versions_seen"].append(version)
            version_updates += 1
        if is_new:
            added += 1

    stale = sorted(xid for xid in known if xid not in seen_xmlids)

    click.echo(f"Odoo series: {version}")
    click.echo(f"Native groups found live: {len(native_rows)}")
    click.echo(f"New entries added to known list: {added}")
    click.echo(f"Entries confirmed present in {version}: {version_updates}")
    if stale:
        click.echo(
            f"\n{len(stale)} known-list entries NOT seen on this instance "
            "(module likely not installed here - not necessarily removed from Odoo):"
        )
        for xid in stale[:30]:
            click.echo(f"  - {xid}")
        if len(stale) > 30:
            click.echo(f"  ... and {len(stale) - 30} more")

    if dry_run:
        click.echo("\n[dry-run] known list not written.")
        return

    write_known_list(known, known_path)
    click.echo(f"\nWrote {known_path}")


@click.command()
@click.option("-c", "--config", default="odooly.ini", help="Odooly config file (default: odooly.ini).")
@click.option("--env", required=True, help="Odooly environment name from config.")
@click.option("--all", "include_all", is_flag=True, default=False, help="Include custom/OCA groups too (default: native CE/EE only).")
@click.option("--format", "fmt", type=click.Choice(["table", "csv", "yaml"]), default="table", help="Output format.")
@click.option("--sync-known-list", "known_list", type=click.Path(), help="Merge discovered native groups into this known_groups.yaml.")
@click.option("--dry-run", is_flag=True, default=False, help="With --sync-known-list, print the diff without writing.")
@click.option("--evidence", is_flag=True, default=False, help="Fetch ir.model.access + menu evidence for each group (helps write purposes for custom/project groups, which have no source to read).")
def run(config, env, include_all, fmt, known_list, dry_run, evidence):
    """Discover res.groups on a live Odoo instance via odooly."""
    odooly.Client._config_file = pathlib.Path(config).expanduser()
    client = odooly.Client.from_config(env)
    odoo_series = get_odoo_series(client)

    rows = fetch_groups(client, odoo_series)
    # test_* modules only exist to drive Odoo's own test suite; skip the noise.
    rows = [r for r in rows if not r["xml_id"].split(".", 1)[0].startswith("test_")]
    if not include_all:
        rows = [r for r in rows if r["origin"] in ("community", "enterprise")]
    rows.sort(key=lambda r: r["xml_id"])

    if known_list:
        sync_known_list(rows, pathlib.Path(known_list), odoo_series, dry_run)
        return

    if evidence:
        group_ids = [r["id"] for r in rows]
        access_by_group = fetch_access_evidence(client, group_ids)
        menus_by_group = fetch_menu_evidence(client, group_ids)
        for r in rows:
            r["access"] = access_by_group.get(r["id"], [])
            r["menus"] = menus_by_group.get(r["id"], [])

    columns = ["xml_id", "full_name", "category", "origin"]
    if evidence:
        columns += ["access", "menus"]

    if fmt == "yaml":
        click.echo(yaml.dump(rows, sort_keys=False, allow_unicode=True))
        return

    # table/csv can't hold list values - flatten access/menus to one string each.
    flat_rows = rows
    if evidence:
        flat_rows = [{**r, "access": "; ".join(r["access"]), "menus": "; ".join(r["menus"])} for r in rows]

    if fmt == "table":
        print_table(flat_rows, columns)
    elif fmt == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=list(flat_rows[0].keys()) if flat_rows else columns)
        writer.writeheader()
        writer.writerows(flat_rows)


if __name__ == "__main__":
    run()
