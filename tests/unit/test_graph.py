"""Stage B: the repository graph must reproduce the fixture's ground truth exactly."""

import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

from repobridge import cli
from repobridge.core import ids
from repobridge.core.schemas import EntityKind, Relation
from repobridge.graph.store import GraphStore
from repobridge.graph.traversal import Graph, GraphQueryError
from repobridge.ingestion.python_ast import index_repository

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testing" / "fixtures" / "cross_file_none"
REPO = FIXTURE / "repo"
TRUTH = tomllib.loads((FIXTURE / "ground_truth.toml").read_text(encoding="utf-8"))
SNAP = ids.make_snapshot("a1b2c3d4e5f6" + "0" * 28)


def names(entities):
    return [e.qualified_name for e in entities]


@pytest.fixture(scope="module")
def result():
    return index_repository(REPO, SNAP)


@pytest.fixture(scope="module")
def graph(result):
    store = GraphStore()
    store.save(result)
    yield Graph(store)
    store.close()


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text), encoding="utf-8")
    return tmp_path


# ----------------------------------------------------------------- the fixture itself


def test_fixture_bug_reproduces():
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from tests.test_checkout import test_checkout_without_discount as t; t()"
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert run.returncode != 0 and TRUTH["task"]["error"] in run.stderr


# ----------------------------------------------------------------- ingestion


def test_counts_and_required_entities(result, graph):
    kinds = [e.kind for e in result.entities]
    assert kinds.count(EntityKind.MODULE) == TRUTH["counts"]["modules"]
    assert kinds.count(EntityKind.CLASS) == TRUTH["counts"]["classes"]
    assert kinds.count(EntityKind.TEST) == TRUTH["counts"]["tests"]
    for qn in TRUTH["required_entities"]:
        assert graph.entity(qn).qualified_name == qn
    assert result.skipped == []


def test_indexing_is_deterministic(result):
    again = index_repository(REPO, SNAP)
    assert again.entities == result.entities and again.edges == result.edges


def test_records_are_valid_contracts(result):
    from repobridge.core.schemas import load

    for rec in [*result.entities, *result.edges]:
        assert load(rec.to_dict()) == rec


def test_spans_and_fingerprints(graph):
    e = graph.entity("shop.pricing.apply_rate")
    src = graph.source_lines(e)
    assert src[e.span.start_line - 1].startswith("def apply_rate")
    body = "\n".join(src[e.span.start_line - 1 : e.span.end_line])
    assert e.fingerprint == ids.fingerprint(body)


# ----------------------------------------------------------------- ground-truth queries


@pytest.mark.parametrize("qn", sorted(TRUTH["callers"]))
def test_callers(graph, qn):
    assert names(graph.callers(qn)) == TRUTH["callers"][qn]


@pytest.mark.parametrize("qn", sorted(TRUTH["callees"]))
def test_callees(graph, qn):
    assert names(graph.callees(qn)) == TRUTH["callees"][qn]


@pytest.mark.parametrize("qn", sorted(TRUTH["unresolved_callees"]))
def test_unresolved_calls_are_explicit(graph, qn):
    assert graph.unresolved_callees(qn) == TRUTH["unresolved_callees"][qn]


@pytest.mark.parametrize("qn", sorted(TRUTH["imports"]))
def test_imports(graph, qn):
    assert names(graph.imports(qn)) == TRUTH["imports"][qn]


@pytest.mark.parametrize("qn", sorted(TRUTH["inherits"]))
def test_inherits(graph, qn):
    assert names(graph.bases(qn)) == TRUTH["inherits"][qn]


@pytest.mark.parametrize("qn", sorted(TRUTH["tests_for"]))
def test_tests_for(graph, qn):
    assert names(graph.tests_for(qn)) == TRUTH["tests_for"][qn]


@pytest.mark.parametrize("chain", TRUTH["chains"], ids=lambda c: f"{c['src']}->{c['dst']}")
def test_call_chains(graph, chain):
    paths = [names(p) for p in graph.call_chains(chain["src"], chain["dst"])]
    assert paths == chain["paths"]


def test_root_cause_is_more_than_four_hops_from_the_test(graph):
    longest = max(len(p) - 1 for c in TRUTH["chains"] for p in c["paths"])
    assert longest > 4


@pytest.mark.parametrize("sl", TRUTH["slices"], ids=lambda s: f"{s['entity']}:{s['criterion']}")
def test_backward_slices(graph, sl):
    e = graph.entity(sl["entity"])
    res = graph.backward_slice(sl["entity"], sl["criterion"])
    src = graph.source_lines(e)
    assert [src[n - 1].strip() for n in res.lines] == sl["lines"]
    assert list(res.params) == sl["params"]
    assert [graph.store.entity(c).qualified_name for c in res.calls] == sl["calls"]


@pytest.mark.parametrize("nc", TRUTH["not_connected"], ids=lambda n: n["decoy"])
def test_text_search_finds_decoy_but_graph_does_not(graph, nc):
    """Retrieval dilution in one test: grep for the crash-site name hits the decoy file."""
    crash = nc["entity"].rsplit(".", 1)[-1]
    grep_hits = sorted(
        p.relative_to(REPO).as_posix()
        for p in REPO.rglob("*.py")
        if crash in p.read_text(encoding="utf-8")
    )
    assert "shop/legacy_pricing.py" in grep_hits
    nodes, _ = graph.ego_graph(nc["entity"], k=nc["k"])
    assert nc["decoy"] not in names(nodes)
    assert nc["entity"] in names(nodes)


# ----------------------------------------------------------------- store behaviour


def test_store_round_trip_and_reindex(result, tmp_path):
    db = tmp_path / "g.sqlite"
    with GraphStore(db) as store:
        store.save(result)
        store.save(result)  # re-indexing the same snapshot replaces, does not duplicate
        assert len(store.entities(SNAP)) == len(result.entities)
        assert len(store.edges(SNAP)) == len(result.edges)
        e = result.entities[3]
        assert store.entity(e.entity_id) == e


def test_two_snapshots_side_by_side_and_fingerprint_change(tmp_path):
    repo = make_repo(tmp_path / "r", {"m.py": "def f(x):\n    return x + 1\n"})
    s1, s2 = ids.make_snapshot("1" * 40), ids.make_snapshot("2" * 40)
    store = GraphStore()
    store.save(index_repository(repo, s1))
    (repo / "m.py").write_text("def f(x):\n    return x + 2\n", encoding="utf-8")
    store.save(index_repository(repo, s2))
    f1, f2 = Graph(store, s1).entity("m.f"), Graph(store, s2).entity("m.f")
    assert f1.entity_id != f2.entity_id and f1.fingerprint != f2.fingerprint


def test_ambiguous_and_missing_names(graph):
    with pytest.raises(GraphQueryError, match="no entity"):
        graph.entity("does_not_exist")
    assert graph.entity("lookup_rate").qualified_name == "shop.discount.lookup_rate"


# ----------------------------------------------------------------- resolution features


def test_resolution_features(tmp_path):
    repo = make_repo(
        tmp_path,
        {
            "src/pkg/__init__.py": "from .core import helper\n",
            "src/pkg/core.py": """
            def helper():
                return 1
            """,
            "src/pkg/sub/__init__.py": "",
            "src/pkg/sub/deep.py": """
            from ..core import helper as h
            from pkg import helper as reexported
            from pkg.core import *


            class Base:
                def run(self):
                    return 0


            class Child(Base):
                def run(self):
                    return super().run() + self.extra()

                def extra(self):
                    def inner():
                        return h()
                    return inner() + reexported() + helper()

                @staticmethod
                def static(self):
                    return self.run()
            """,
            "src/pkg/broken.py": "def oops(:\n",
            "scripts/my-tool.py": "print('hi')\n",
        },
    )
    store = GraphStore()
    res = index_repository(repo, SNAP)
    store.save(res)
    g = Graph(store)
    assert any("broken.py: syntax error" in s for s in res.skipped)
    assert any("my-tool.py" in s for s in res.skipped)
    assert names(g.callees("pkg.sub.deep.Child.run")) == [
        "pkg.sub.deep.Base.run",
        "pkg.sub.deep.Child.extra",
    ]
    # nested def, re-export through pkg/__init__, and a star import all resolve to the same helper
    assert names(g.callees("pkg.sub.deep.Child.extra")) == [
        "pkg.core.helper",
        "pkg.sub.deep.Child.extra.inner",
    ]
    assert names(g.callees("pkg.sub.deep.Child.extra.inner")) == ["pkg.core.helper"]
    # a staticmethod's first parameter is not `self`
    assert g.unresolved_callees("pkg.sub.deep.Child.static") == ["self.run"]
    assert names(g.imports("pkg")) == ["pkg.core"]


def test_self_index_of_repobridge_source():
    """Smoke test on a real codebase: our own package."""
    res = index_repository(ROOT / "src", SNAP)
    store = GraphStore()
    store.save(res)
    g = Graph(store)
    assert "repobridge.core.schemas._req_id" in names(g.callers("repobridge.core.ids.is_record_id"))
    assert res.stats["kind.class"] > 20 and not res.skipped
    edges = store.edges(SNAP)
    assert any(e.relation is Relation.INHERITS for e in edges)


# ----------------------------------------------------------------- CLI


def test_cli_index_and_query(tmp_path, capsys):
    db = str(tmp_path / "g.sqlite")
    assert cli.main(["index", str(REPO), "--db", db, "--snapshot", "a" * 40]) == 0
    assert "7 modules" in capsys.readouterr().out
    assert (
        cli.main(
            ["query", "--db", db, "chains", "test_checkout_without_discount", "shop.config.parse"]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "[5 hops]" in out and out.strip().endswith("shop.config.parse")
    assert cli.main(["query", "--db", db, "callees", "lookup_rate"]) == 0
    assert "unresolved: settings.get" in capsys.readouterr().out
    assert cli.main(["query", "--db", db, "callers", "nope"]) == 1


def test_cli_query_without_index(tmp_path, capsys):
    assert cli.main(["query", "--db", str(tmp_path / "none.sqlite"), "stats"]) == 1
    assert "run `repobridge index" in capsys.readouterr().err
