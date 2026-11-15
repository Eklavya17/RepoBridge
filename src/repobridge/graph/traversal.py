"""Queries over one snapshot of the repository graph.

    graph = Graph(GraphStore("graph.sqlite"))          # latest indexed snapshot
    graph.callers("shop.pricing.apply_rate")
    graph.call_chains("test_checkout_without_discount", "shop.config.parse")

Entity arguments may be an entity ID, a qualified name, or a unique name suffix. Results are
sorted by qualified name so they are deterministic. Only resolved edges are traversed;
unresolved calls are reported separately and never guessed.
"""

import ast
from collections import deque
from pathlib import Path

from repobridge.core import ids
from repobridge.core.schemas import EntityKind, GraphEdge, ProgramEntity, Relation
from repobridge.graph.slicing import SliceResult, backward_slice, find_function
from repobridge.graph.store import GraphStore


class GraphQueryError(LookupError):
    pass


def _by_name(entities):
    return sorted(entities, key=lambda e: e.qualified_name)


class Graph:
    def __init__(self, store: GraphStore, snapshot: str | None = None) -> None:
        self.store = store
        self.snapshot = snapshot or store.latest_snapshot()
        if self.snapshot is None:
            raise GraphQueryError("the store has no indexed snapshot; run `repobridge index`")
        info = store.snapshot_info(self.snapshot)
        if info is None:
            raise GraphQueryError(f"snapshot {self.snapshot} is not indexed in {store.path}")
        self.root = Path(info["root"])

    # ------------------------------------------------------------------ lookup
    def entity(self, ref: str) -> ProgramEntity:
        if ids.is_entity_id(ref):
            e = self.store.entity(ref)
            if e is None or e.snapshot != self.snapshot:
                raise GraphQueryError(f"{ref} is not in snapshot {self.snapshot}")
            return e
        hits = self.store.find(self.snapshot, ref)
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise GraphQueryError(f"no entity named {ref!r}")
        raise GraphQueryError(f"{ref!r} is ambiguous: " + ", ".join(h.qualified_name for h in hits))

    def find_symbol(self, name: str) -> list[ProgramEntity]:
        return self.store.find(self.snapshot, name)

    def _ids_to_entities(self, entity_ids) -> list[ProgramEntity]:
        return _by_name(e for e in (self.store.entity(i) for i in set(entity_ids)) if e)

    # ------------------------------------------------------------------ neighbours
    def callers(self, ref: str) -> list[ProgramEntity]:
        e = self.entity(ref)
        return self._ids_to_entities(
            g.src for g in self.store.edges_to(e.entity_id, Relation.CALLS, resolved=True)
        )

    def callees(self, ref: str) -> list[ProgramEntity]:
        e = self.entity(ref)
        return self._ids_to_entities(
            g.dst for g in self.store.edges_from(e.entity_id, Relation.CALLS, resolved=True)
        )

    def unresolved_callees(self, ref: str) -> list[str]:
        e = self.entity(ref)
        return sorted(
            g.dst.removeprefix(ids.UNRESOLVED_PREFIX)
            for g in self.store.edges_from(e.entity_id, Relation.CALLS, resolved=False)
        )

    def imports(self, ref: str) -> list[ProgramEntity]:
        e = self.entity(ref)
        return self._ids_to_entities(
            g.dst for g in self.store.edges_from(e.entity_id, Relation.IMPORTS, resolved=True)
        )

    def bases(self, ref: str) -> list[ProgramEntity]:
        e = self.entity(ref)
        return self._ids_to_entities(
            g.dst for g in self.store.edges_from(e.entity_id, Relation.INHERITS)
        )

    # ------------------------------------------------------------------ multi-hop
    def tests_for(self, ref: str, max_depth: int = 8) -> list[ProgramEntity]:
        """Tests that reach ``ref`` through resolved calls (reverse BFS)."""
        start = self.entity(ref).entity_id
        seen, tests = {start}, []
        queue = deque([(start, 0)])
        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for g in self.store.edges_to(node, Relation.CALLS, resolved=True):
                if g.src in seen:
                    continue
                seen.add(g.src)
                src = self.store.entity(g.src)
                if src and src.kind is EntityKind.TEST:
                    tests.append(src)
                queue.append((g.src, depth + 1))
        return _by_name(tests)

    def call_chains(
        self, src: str, dst: str, max_depth: int = 8, max_paths: int = 20
    ) -> list[list[ProgramEntity]]:
        """Simple call paths from ``src`` to ``dst``, shortest first."""
        a, b = self.entity(src).entity_id, self.entity(dst).entity_id
        found: list[list[str]] = []

        def dfs(node: str, path: list[str]) -> None:
            if len(found) >= max_paths:
                return
            if node == b:
                found.append(path)
                return
            if len(path) > max_depth:
                return
            for g in self.store.edges_from(node, Relation.CALLS, resolved=True):
                if g.dst not in path:
                    dfs(g.dst, [*path, g.dst])

        dfs(a, [a])
        found.sort(key=lambda p: (len(p), p))
        return [[self.store.entity(i) for i in p] for p in found]

    def ego_graph(
        self,
        ref: str,
        k: int = 2,
        relations: tuple[Relation, ...] = (Relation.CALLS,),
        max_nodes: int = 200,
    ) -> tuple[list[ProgramEntity], list[GraphEdge]]:
        """Entities within ``k`` hops in either direction over resolved ``relations``."""
        start = self.entity(ref).entity_id
        seen, edges = {start: 0}, {}
        queue = deque([start])
        while queue and len(seen) < max_nodes:
            node = queue.popleft()
            if seen[node] >= k:
                continue
            for rel in relations:
                for g in [
                    *self.store.edges_from(node, rel, resolved=True),
                    *self.store.edges_to(node, rel, resolved=True),
                ]:
                    edges[g.edge_id] = g
                    other = g.dst if g.src == node else g.src
                    if other not in seen and len(seen) < max_nodes:
                        seen[other] = seen[node] + 1
                        queue.append(other)
        nodes = self._ids_to_entities(seen)
        kept = {e.entity_id for e in nodes}
        return nodes, sorted(
            (g for g in edges.values() if g.src in kept and g.dst in kept),
            key=lambda g: (g.src, g.dst),
        )

    # ------------------------------------------------------------------ slicing
    def source_lines(self, entity: ProgramEntity) -> list[str]:
        return (self.root / entity.path).read_text(encoding="utf-8").splitlines()

    def backward_slice(self, ref: str, criterion: str = "return") -> SliceResult:
        e = self.entity(ref)
        if e.kind not in (EntityKind.FUNCTION, EntityKind.METHOD, EntityKind.TEST):
            raise GraphQueryError(f"can only slice functions, {e.qualified_name} is a {e.kind}")
        path = self.root / e.path
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node = find_function(tree, self._def_path(e))
        if node is None or not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            raise GraphQueryError(f"cannot find the definition of {e.qualified_name} in {e.path}")
        result = backward_slice(node, criterion, entity_id=e.entity_id)
        lines = set(result.lines)
        calls = sorted(
            g.dst
            for g in self.store.edges_from(e.entity_id, Relation.CALLS, resolved=True)
            if lines & set(g.attrs.get("lines", []))
        )
        return SliceResult(
            entity_id=e.entity_id,
            criterion=criterion,
            lines=result.lines,
            params=result.params,
            calls=tuple(calls),
        )

    def _def_path(self, e: ProgramEntity) -> list[str]:
        """Name path of ``e`` inside its module, e.g. ['PriceEngine', 'quote']."""
        module = next(
            m for m in self.store.entities(self.snapshot, EntityKind.MODULE) if m.path == e.path
        )
        return e.qualified_name[len(module.qualified_name) + 1 :].split(".")
