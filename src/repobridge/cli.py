"""`repobridge` command-line entry point.

repobridge schemas                      list contracts and their schema versions
repobridge schemas --export docs/schemas   write JSON Schema files
repobridge schemas --check  docs/schemas   fail if the committed schemas are stale
repobridge validate FILE                validate a .json / .jsonl file of records
repobridge index PATH                   index a Python repository into the graph (Stage B)
repobridge query callers|callees|chains|tests|ego|slice|find|stats ...   query the graph
repobridge bundle                       arrives in Stage C
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from repobridge import __version__
from repobridge.core import rules
from repobridge.core.schemas import (
    CONTRACTS,
    ContextBundle,
    Evidence,
    ScoutFinding,
    ScoutRequest,
    Status,
    Summary,
    load,
)
from repobridge.core.serialization import Contract, ContractError, contract_json_schema


def _schema_files() -> dict[str, str]:
    return {
        f"{c.__name__}.schema.json": json.dumps(contract_json_schema(c), indent=2) + "\n"
        for c in CONTRACTS
    }


def cmd_schemas(args: argparse.Namespace) -> int:
    files = _schema_files()
    if args.export:
        out = Path(args.export)
        out.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {len(files)} schema files to {out}")
        return 0
    if args.check:
        out = Path(args.check)
        stale = [
            n
            for n, t in files.items()
            if not (out / n).exists() or (out / n).read_text(encoding="utf-8") != t
        ]
        if stale:
            print(
                f"stale or missing schema files in {out}: {stale}\n"
                f"run: repobridge schemas --export {out}",
                file=sys.stderr,
            )
            return 1
        print(f"{len(files)} schema files in {out} are up to date")
        return 0
    for c in CONTRACTS:
        print(f"{c.__name__:<15} {c.SCHEMA}")
    return 0


def _read_records(path: Path) -> list[tuple[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [
            (f"{path.name}:{i}", json.loads(line))
            for i, line in enumerate(text.splitlines(), 1)
            if line.strip()
        ]
    data = json.loads(text)
    items = data if isinstance(data, list) else [data]
    return [(f"{path.name}[{i}]", d) for i, d in enumerate(items)]


def _record_id(rec: Contract) -> str:
    return getattr(rec, dataclasses.fields(rec)[0].name)  # type: ignore[arg-type]


def validate_records(raw: list[tuple[str, Any]]) -> tuple[list[Contract], list[str]]:
    """Decode every record, then run the cross-record rules that the file allows."""
    records: list[Contract] = []
    errors: list[str] = []
    for where, data in raw:
        try:
            records.append(load(data))
        except (ContractError, json.JSONDecodeError) as exc:
            errors.append(f"{where}: {exc}")

    ids_seen: dict[str, int] = {}
    for rec in records:
        rid = _record_id(rec)
        ids_seen[rid] = ids_seen.get(rid, 0) + 1
    errors += [f"duplicate record ID {rid}" for rid, n in ids_seen.items() if n > 1]

    bundles_by_order = {r.order_id: r for r in records if isinstance(r, ContextBundle)}
    bundles_by_id = {r.bundle_id: r for r in records if isinstance(r, ContextBundle)}
    accepted = {
        _record_id(r)
        for r in records
        if isinstance(r, Evidence | Summary | ScoutFinding) and r.status.at_least(Status.CHECKED)
    }
    for rec in records:
        if isinstance(rec, ScoutFinding) and rec.order_id in bundles_by_order:
            errors += [
                f"{rec.finding_id}: {p}"
                for p in rules.check_finding_grounded(rec, bundles_by_order[rec.order_id])
            ]
        if isinstance(rec, ScoutRequest):
            if rec.bundle_ref in bundles_by_id:
                errors += [
                    f"{rec.order_id}: {p}"
                    for p in rules.check_request_matches_bundle(rec, bundles_by_id[rec.bundle_ref])
                ]
            errors += [
                f"{rec.order_id}: {p}" for p in rules.check_assumptions_closed(rec, accepted)
            ]
    return records, errors


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    try:
        raw = _read_records(path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 1
    records, errors = validate_records(raw)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    counts: dict[str, int] = {}
    for r in records:
        counts[type(r).__name__] = counts.get(type(r).__name__, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    print(f"{'FAIL' if errors else 'OK'}: {len(records)}/{len(raw)} records decoded ({summary})")
    return 1 if errors else 0


def cmd_not_yet(stage: str):
    def run(_args: argparse.Namespace) -> int:
        print(
            f"not implemented yet: arrives in Stage {stage} (docs/context_management.md §6)",
            file=sys.stderr,
        )
        return 2

    return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repobridge", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"repobridge {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("schemas", help="list, export or check contract JSON Schemas")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--export", metavar="DIR")
    g.add_argument("--check", metavar="DIR")
    p.set_defaults(func=cmd_schemas)

    p = sub.add_parser("validate", help="validate a .json/.jsonl file of contract records")
    p.add_argument("file")
    p.set_defaults(func=cmd_validate)

    from repobridge.graph.cli import add_graph_commands

    add_graph_commands(sub)

    for name, stage, help_ in [
        ("bundle", "C", "build a context bundle for a question"),
    ]:
        p = sub.add_parser(name, help=f"{help_} (Stage {stage})")
        p.set_defaults(func=cmd_not_yet(stage))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
