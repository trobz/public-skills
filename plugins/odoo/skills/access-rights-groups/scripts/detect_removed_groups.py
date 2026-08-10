#!/usr/bin/env python3
"""
Detect res.groups xml_ids that a real Odoo module-update/upgrade run
permanently removed (not renamed - simply no longer declared in the newer
version's data files), and mark them in known_groups.yaml.

Odoo's own registry cleanup (ir.model's stale-record cleanup, run on every
module update/upgrade, independent of OpenUpgrade) logs this in the standard
form:

    odoo.addons.base.models.ir_model: Deleting <id>@res.groups (<xml_id>)

Point this at a local Odoo server log file from a real upgrade run (any
project, any version - nothing here is specific to one project's
infrastructure) to extract these lines and record which known_groups.yaml
entries were confirmed removed at that version.

This is a different kind of evidence than resolve_renames.py's OpenUpgrade
source data: OpenUpgrade's _xmlids_renames is authoritative (it is what
module authors declared should happen everywhere), whereas a deletion seen
in one project's log is empirical - a real deletion that did happen on that
run, but not proof the group is gone for every installation (e.g. a module
simply not being installed there would look the same). Treat removed_in as
"confirmed removed by at least one real run", not "removed for everyone".

Only xml_ids already present in known_groups.yaml are touched - same
principle as resolve_renames.py: this script never invents a new group
entry, it only annotates ones already known.

--version is taken on trust (a log has no single reliable field naming "the
version this run upgraded into"), but it's cross-checked on a best-effort
basis against two independent hints, when present: Odoo's own startup log
line ("Odoo version X", printed by every real Odoo server - not specific to
any one project's tooling) and a "NN.0"-shaped substring in the log
filename. Neither hint is guaranteed to be there - a grepped excerpt has no
startup banner, a filename may not encode a version at all - so absence of a
hint is never treated as a mismatch. But when a hint IS there and disagrees
with --version, the run aborts before touching known_groups.yaml at all
(exit code 1) rather than silently writing removed_in under the wrong
version - pass --force to proceed anyway once you've confirmed by hand which
version is actually right.

Usage:
    python detect_removed_groups.py --log path/to/upgrade_18.0.log --version 18.0 \
        --known-list known_groups.yaml
"""

import pathlib
import re
import sys

import click
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _known_list import write_known_list  # noqa: E402

DELETE_RE = re.compile(r"Deleting\s+\d+@res\.groups\s+\(([\w.]+)\)")
VERSION_BANNER_RE = re.compile(r"Odoo version (\S+)")
FILENAME_VERSION_RE = re.compile(r"(\d+)\.0(?=\D|$)")


def extract_removed_xmlids(text):
    """Return the deduplicated, sorted set of res.groups xml_ids the log
    shows as deleted. Some deletions log only a numeric id with no xml_id
    (the ir.model.data row was already gone by the time of deletion) - those
    can't be attributed to a group and are silently skipped, not guessed."""
    return sorted(set(DELETE_RE.findall(text)))


def normalize_series(raw_version):
    """Best-effort: pull a clean 'NN.0' series out of a raw Odoo version
    string (release.version can be '18.0', '18.0-20240101', 'saas~17.4', a
    git describe string, ...). Returns None when no such series can be
    found, so the caller just skips that hint rather than risking a false
    warning on an unrecognized format."""
    match = re.search(r"(\d+)\.0", raw_version)
    return f"{match.group(1)}.0" if match else None


def cross_check_version(text, log_path, version):
    """Compare --version against whatever version hints the log itself
    offers, and return the mismatches as {source_description: hint_found}.
    Absence of a hint is never a mismatch - only an actual disagreement is
    reported, never a guess made from silence."""
    hints = {}

    banner = VERSION_BANNER_RE.search(text)
    if banner:
        series = normalize_series(banner.group(1))
        if series:
            hints[f"log content says \"Odoo version {banner.group(1)}\""] = series

    filename_match = FILENAME_VERSION_RE.search(pathlib.Path(log_path).name)
    if filename_match:
        hints[f"log filename contains \"{filename_match.group(0)}\""] = f"{filename_match.group(1)}.0"

    return {source: hint for source, hint in hints.items() if hint != version}


@click.command()
@click.option("--log", "log_path", required=True, type=click.Path(exists=True), help="Local Odoo upgrade/update log file (any project, any version).")
@click.option("--version", "version", required=True, help="Odoo series this log run upgraded INTO (e.g. 18.0).")
@click.option("--known-list", required=True, type=click.Path(exists=True), help="known_groups.yaml to annotate.")
@click.option("--dry-run", is_flag=True, default=False, help="Print what would be marked without writing.")
@click.option("--force", is_flag=True, default=False, help="Proceed even if --version disagrees with the log's own version hints (default: abort).")
def run(log_path, version, known_list, dry_run, force):
    """Mark known_groups.yaml entries confirmed removed by a real Odoo upgrade log."""
    text = pathlib.Path(log_path).read_text(errors="replace")

    mismatches = cross_check_version(text, log_path, version)
    if mismatches:
        click.echo(f"--version {version} was passed, but:", err=True)
        for source, hint in mismatches.items():
            click.echo(f"  - {source} (series {hint})", err=True)
        if not force:
            click.echo(
                "\nAborting before touching known_groups.yaml - fix --version, "
                "or pass --force if this is intentional.",
                err=True,
            )
            sys.exit(1)
        click.echo("--force passed: proceeding despite the mismatch.\n", err=True)

    removed = extract_removed_xmlids(text)
    click.echo(f"res.groups deletions found in log: {len(removed)}")

    known_path = pathlib.Path(known_list)
    known = yaml.safe_load(known_path.read_text()) or {}

    marked, unknown = [], []
    for xml_id in removed:
        if xml_id not in known:
            unknown.append(xml_id)
            continue
        entry = known[xml_id]
        entry.setdefault("removed_in", [])
        if version not in entry["removed_in"]:
            entry["removed_in"].append(version)
            marked.append(xml_id)

    click.echo(f"Newly marked removed_in {version}: {len(marked)}")
    for xml_id in marked:
        click.echo(f"  - {xml_id}")
    if unknown:
        click.echo(f"\n{len(unknown)} deleted xml_id(s) not in known list (not res.groups, or not yet discovered - skipped):")
        for xml_id in unknown[:30]:
            click.echo(f"  - {xml_id}")
        if len(unknown) > 30:
            click.echo(f"  ... and {len(unknown) - 30} more")

    if dry_run:
        click.echo("\n[dry-run] known list not written.")
        return

    write_known_list(known, known_path)
    click.echo(f"\nWrote {known_path}")


if __name__ == "__main__":
    run()
