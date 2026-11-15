# Repository graph (L1, Stage B)

The repository graph is a map of how the code in a repository connects: what is defined where, what calls what, what imports what and which tests reach which functions. Every later layer asks it questions instead of reading raw files. See [`context_management.md`](context_management.md) §3, layer L1.

| Code | Role |
|---|---|
| [`ingestion/python_ast.py`](../src/repobridge/ingestion/python_ast.py) | Parse Python into `ProgramEntity` and `GraphEdge` records |
| [`ingestion/snapshot.py`](../src/repobridge/ingestion/snapshot.py) | Commit SHA (plus a dirty marker) from git |
| [`graph/store.py`](../src/repobridge/graph/store.py) | SQLite storage. Snapshots live side by side; re-indexing a snapshot replaces it |
| [`graph/traversal.py`](../src/repobridge/graph/traversal.py) | `Graph` queries |
| [`graph/slicing.py`](../src/repobridge/graph/slicing.py) | Backward slices inside one function, computed on demand |
| [`graph/cli.py`](../src/repobridge/graph/cli.py) | `repobridge index` and `repobridge query` |

## What is extracted

All of this is static analysis with no LLM.

| Item | Details |
|---|---|
| Entities | Modules, classes, functions, methods, tests (`test*` in test modules, and `Test*.test*`). Each has a span and a fingerprint |
| `CONTAINS` | module → class/function, class → method, function → nested function |
| `IMPORTS` | module → module. Modules outside the repo become `unresolved:<name>` with `reason=external` |
| `INHERITS` | class → base class defined in the repo |
| `CALLS` | Resolved through absolute, relative and aliased imports; re-exports from `__init__`; star imports; nested scopes; constructors (`Cls()` → `Cls.__init__`, else the class); and `self.`/`cls.`/`super()` lookups along in-repo base classes. Call lines are kept in `attrs.lines` |
| `TESTS` | test → non-test entity it calls directly |

**Not guessed.** Calls the analysis can't pin down become `unresolved:<call as written>`, with `reason` set to one of:
- `dynamic`: a callable parameter, a method on a local value, or a call on a call result
- `external`: a library outside the repo
- `unknown`: anything else

Calls to Python builtins are skipped and only counted. `src/` layouts are detected. Files that fail to parse or don't have importable names are listed under `skipped`, without stopping the run.

**Slicing.** `backward_slice(fn, "rate" | "return")` collects, within one function:
- the statements that can affect the variable,
- the enclosing `if`/`for`/`while`/`with`/`try` headers, which expose early exits like `if not text.strip(): return {}`,
- the parameters the value depends on (`params`), where the value comes from callers and the next question goes,
- the resolved calls made on slice lines.

## Queries

| Query | `Graph` method | CLI |
|---|---|---|
| Find a definition | `find_symbol(name)` | `repobridge query find NAME` |
| Who calls it | `callers(ref)` | `query callers REF` |
| What it calls | `callees(ref)`, `unresolved_callees(ref)` | `query callees REF` |
| Tests that reach it | `tests_for(ref)` | `query tests REF` |
| Call paths | `call_chains(src, dst)` | `query chains SRC DST` |
| Neighbourhood | `ego_graph(ref, k)` | `query ego REF -k 2` |
| Backward slice | `backward_slice(ref, criterion)` | `query slice REF --criterion rate` |

`REF` may be an entity ID, a qualified name, or a unique name suffix such as `lookup_rate`. Results are sorted, so they're deterministic. Add `--json` to get contract records.

```bash
uv run repobridge index testing/fixtures/cross_file_none/repo
```
```bash
uv run repobridge query chains test_checkout_without_discount shop.config.parse
```

## Ground truth (`testing/fixtures/cross_file_none/`)

The fixture is a small shop package with a real bug, focused on debugging first:
- A settings text without `discount` makes `lookup_rate` return `None`, which crashes in `apply_rate`.
- The chain from the test to the parser is **5 hops**, longer than RepoAudit's K = 4.
- [`ground_truth.toml`](../testing/fixtures/cross_file_none/ground_truth.toml) lists the exact callers, callees, unresolved calls, imports, inheritance, tests, call chains and slices. [`tests/unit/test_graph.py`](../tests/unit/test_graph.py) checks every one.
- One test shows retrieval dilution directly: grep for `apply_rate` hits the decoy `legacy_pricing.py`, but the 3-hop call neighbourhood does not.

## Known limits (by design for Stage B)

- **Python only.** Concurrency benchmarks (Java) need a tree-sitter front end later.
- **No type inference.** `obj.method()` on a local or parameter stays unresolved. In the fixture, `TestEngine.test_quote` therefore doesn't statically reach `apply_rate`. Runtime traces (the debugging overlay) will add these as `observed` edges.
- **Slices stay inside one function.** Following data across functions is the coordinator's job, using `params` and `callers`.
- **Duplicate definitions** (e.g. a property setter) keep the first definition.
