"""Intra-procedural backward slicing on demand (ARISE-style def-use, Python ``ast``).

Given a function and a criterion (a variable name, or ``"return"``), collect the statements
that can affect it inside that function:

1. Seed with the statements that define the variable (or every ``return``).
2. Repeatedly add statements that define any name the slice uses.
3. Add the headers of enclosing ``if``/``while``/``for``/``with``/``try`` statements, which is
   what exposes early exits such as ``if not cfg: return None``.

The analysis is flow-insensitive within the function, so it may over-include but should not
miss a local data dependency. Names that reach a parameter are reported in ``params``. They are
the escape points where the value comes from callers (the next frontier for the coordinator).
"""

import ast
from dataclasses import dataclass

_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass(frozen=True)
class SliceResult:
    entity_id: str
    criterion: str
    lines: tuple[int, ...]
    params: tuple[str, ...]
    calls: tuple[str, ...] = ()  # resolved callee entity IDs on slice lines (filled by Graph)


@dataclass
class _Stmt:
    node: ast.stmt
    line: int
    defs: set[str]
    uses: set[str]
    parents: list["_Stmt"]


def _walk(nodes):
    stack = list(nodes)
    while stack:
        n = stack.pop()
        yield n
        stack.extend(c for c in ast.iter_child_nodes(n) if not isinstance(c, ast.stmt))


def _header(stmt: ast.stmt) -> list[ast.AST]:
    if isinstance(stmt, ast.If | ast.While):
        return [stmt.test]
    if isinstance(stmt, ast.For | ast.AsyncFor):
        return [stmt.target, stmt.iter]
    if isinstance(stmt, ast.With | ast.AsyncWith):
        return list(stmt.items)
    if isinstance(stmt, ast.Try):
        return [h.type for h in stmt.handlers if h.type is not None]
    if isinstance(stmt, ast.Match):
        return [stmt.subject]
    return [stmt]


def _statements(func: ast.AST) -> list[_Stmt]:
    out: list[_Stmt] = []

    def visit(body: list[ast.stmt], parents: list[_Stmt]) -> None:
        for s in body:
            if isinstance(s, _DEFS):
                continue
            names = [n for n in _walk(_header(s)) if isinstance(n, ast.Name)]
            rec = _Stmt(
                node=s,
                line=s.lineno,
                defs={n.id for n in names if isinstance(n.ctx, ast.Store)},
                uses={n.id for n in names if isinstance(n.ctx, ast.Load)},
                parents=parents,
            )
            if isinstance(s, ast.Try):
                rec.defs |= {h.name for h in s.handlers if h.name}
            out.append(rec)
            for attr in ("body", "orelse", "finalbody"):
                visit(getattr(s, attr, []) or [], [*parents, rec])
            for h in getattr(s, "handlers", []) or []:
                visit(h.body, [*parents, rec])
            for c in getattr(s, "cases", []) or []:
                visit(c.body, [*parents, rec])

    visit(func.body, [])
    return out


def _params(func: ast.AST) -> list[str]:
    a = func.args
    names = [x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]]
    names += [x.arg for x in (a.vararg, a.kwarg) if x is not None]
    return names


def backward_slice(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    criterion: str,
    entity_id: str = "",
    at_line: int | None = None,
) -> SliceResult:
    stmts = _statements(func)
    limit = at_line if at_line is not None else (func.end_lineno or func.lineno) + 1
    if criterion == "return":
        seeds = [s for s in stmts if isinstance(s.node, ast.Return) and s.line <= limit]
    else:
        seeds = [s for s in stmts if criterion in s.defs and s.line < limit]
    wanted: set[str] = set() if criterion == "return" else {criterion}
    chosen: dict[int, _Stmt] = {id(s): s for s in seeds}
    changed = True
    while changed:  # fixpoint: enclosing headers, then definitions of anything used
        changed = False
        for s in list(chosen.values()):
            for p in s.parents:
                if id(p) not in chosen:
                    chosen[id(p)] = p
                    changed = True
        for s in chosen.values():
            wanted |= s.uses
        for t in stmts:
            if id(t) not in chosen and t.line < limit and t.defs & wanted:
                chosen[id(t)] = t
                changed = True
    params = [p for p in _params(func) if p in wanted]
    lines = {s.line for s in chosen.values()}
    if params:
        lines.add(func.lineno)
    return SliceResult(
        entity_id=entity_id, criterion=criterion, lines=tuple(sorted(lines)), params=tuple(params)
    )


def find_function(tree: ast.Module, qualname_tail: list[str]) -> ast.AST | None:
    """Locate a def by its name path inside a module, e.g. ['PriceEngine', 'quote']."""
    body, node = tree.body, None
    for part in qualname_tail:
        node = next((s for s in _iter_defs(body) if s.name == part), None)
        if node is None:
            return None
        body = node.body
    return node


def _iter_defs(body: list[ast.stmt]):
    for s in body:
        if isinstance(s, _DEFS):
            yield s
            continue
        for attr in ("body", "orelse", "finalbody"):
            yield from _iter_defs(getattr(s, attr, []) or [])
        for h in getattr(s, "handlers", []) or []:
            yield from _iter_defs(h.body)
