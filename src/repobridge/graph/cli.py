"""`repobridge index` and `repobridge query` subcommands (Stage B)."""

import argparse
import json
import sys
from pathlib import Path

from repobridge.core import ids
from repobridge.core.schemas import ProgramEntity
from repobridge.graph.store import GraphStore
from repobridge.graph.traversal import Graph, GraphQueryError
from repobridge.ingestion.python_ast import index_repository
from repobridge.ingestion.snapshot import SnapshotError, git_snapshot

DEFAULT_DB = Path(".repobridge") / "graph.sqlite"


def _line(e: ProgramEntity) -> str:
    return f"{e.qualified_name:<55} {e.kind.value:<8} {e.path}:{e.span.start_line}"


def _print_entities(entities: list[ProgramEntity], as_json: bool) -> None:
    if as_json:
        print(json.dumps([e.to_dict() for e in entities], indent=1))
    else:
        for e in entities:
            print(_line(e))
        if not entities:
            print("(none)")


def cmd_index(args: argparse.Namespace) -> int:
    root = Path(args.path)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    if args.snapshot:
        try:
            snapshot = ids.make_snapshot(args.snapshot)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    else:
        try:
            snapshot = git_snapshot(root)
        except SnapshotError as exc:
            print(
                f"{exc}\npass --snapshot <40-hex sha> for a directory outside git", file=sys.stderr
            )
            return 1
    result = index_repository(root, snapshot)
    with GraphStore(args.db) as store:
        store.save(result)
    s = result.stats
    print(
        f"indexed {s['modules']} modules, {s['entities']} entities, {s['edges']} edges "
        f"({s['unresolved_edges']} unresolved) at {ids.rev_tag(snapshot)} into {args.db}"
    )
    for skip in result.skipped:
        print(f"  skipped {skip}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print(f"no graph at {args.db}; run `repobridge index <path>` first", file=sys.stderr)
        return 1
    with GraphStore(args.db) as store:
        try:
            graph = Graph(store, args.snapshot)
            return _run_query(graph, args)
        except GraphQueryError as exc:
            print(exc, file=sys.stderr)
            return 1


def _run_query(g: Graph, args: argparse.Namespace) -> int:
    q = args.query
    if q == "stats":
        info = g.store.snapshot_info(g.snapshot)
        print(json.dumps({"snapshot": g.snapshot, "root": info["root"], **info["stats"]}, indent=1))
    elif q == "find":
        _print_entities(g.find_symbol(args.name), args.json)
    elif q == "callers":
        _print_entities(g.callers(args.ref), args.json)
    elif q == "callees":
        _print_entities(g.callees(args.ref), args.json)
        if not args.json:
            for name in g.unresolved_callees(args.ref):
                print(f"unresolved: {name}")
    elif q == "tests":
        _print_entities(g.tests_for(args.ref), args.json)
    elif q == "chains":
        paths = g.call_chains(args.src, args.dst, max_depth=args.max_depth)
        if args.json:
            print(json.dumps([[e.qualified_name for e in p] for p in paths], indent=1))
        else:
            for p in paths:
                print(f"[{len(p) - 1} hops] " + "\n    -> ".join(e.qualified_name for e in p))
            if not paths:
                print("(no call path)")
    elif q == "ego":
        nodes, edges = g.ego_graph(args.ref, k=args.k)
        _print_entities(nodes, args.json)
        if not args.json:
            print(f"({len(nodes)} entities, {len(edges)} CALLS edges within {args.k} hops)")
    elif q == "slice":
        e = g.entity(args.ref)
        result = g.backward_slice(args.ref, args.criterion)
        src = g.source_lines(e)
        if args.json:
            print(
                json.dumps(
                    {
                        "entity": e.entity_id,
                        "criterion": result.criterion,
                        "lines": list(result.lines),
                        "params": list(result.params),
                        "calls": list(result.calls),
                    },
                    indent=1,
                )
            )
        else:
            for n in result.lines:
                print(f"{e.path}:{n:<5} {src[n - 1].rstrip()}")
            print(f"params reached (value comes from callers): {list(result.params) or '-'}")
            print(
                "calls on slice lines: "
                + (", ".join(c.split("@")[0].removeprefix("py:") for c in result.calls) or "-")
            )
    return 0


def add_graph_commands(sub) -> None:
    p = sub.add_parser("index", help="index a Python repository into the graph (Stage B)")
    p.add_argument("path", help="repository root")
    p.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite file (default {DEFAULT_DB})")
    p.add_argument("--snapshot", help="commit SHA to record (default: from git)")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("query", help="query the repository graph")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--snapshot", help="snapshot to query (default: latest indexed)")
    p.add_argument("--json", action="store_true", help="print contract records as JSON")
    qs = p.add_subparsers(dest="query", required=True)
    qs.add_parser("stats", help="counts for the snapshot")
    qs.add_parser("find", help="find entities by (suffix of) name").add_argument("name")
    for name, help_ in [
        ("callers", "who calls REF"),
        ("callees", "what REF calls"),
        ("tests", "tests that reach REF through calls"),
    ]:
        qs.add_parser(name, help=help_).add_argument("ref")
    c = qs.add_parser("chains", help="call paths from SRC to DST")
    c.add_argument("src")
    c.add_argument("dst")
    c.add_argument("--max-depth", type=int, default=8)
    e = qs.add_parser("ego", help="entities within k call hops of REF")
    e.add_argument("ref")
    e.add_argument("-k", type=int, default=2)
    s = qs.add_parser("slice", help="backward slice inside a function")
    s.add_argument("ref")
    s.add_argument("--criterion", default="return", help="variable name, or 'return'")
    p.set_defaults(func=cmd_query)
