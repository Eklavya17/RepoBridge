"""Data contracts (docs/contracts.md). Fields are frozen in Stage A.

Each class is a placeholder whose docstring lists the agreed fields; Stage A replaces
these with real dataclasses and validation tests.
"""

from dataclasses import dataclass

STATUS_LATTICE = (
    "proposed",
    "checked",
    "observed",
    "reproduced",
    "regression_checked",
    "refuted",
)
PROVENANCE = ("static", "observed", "llm_inferred")
LEDGER_SECTIONS = ("postmortem", "strategy", "plan", "execution")


@dataclass
class ProgramEntity:
    """snapshot, entity_id, kind, qualified_name, path, span, fingerprint"""


@dataclass
class GraphEdge:
    """edge_id, src, dst, relation, resolved, provenance, snapshot, attrs"""


@dataclass
class Evidence:
    """evidence_id, task_id, entity_ids, artifact_ref, digest, producer, status, snapshot,
    depends_on"""


@dataclass
class LedgerEvent:
    """event_id, investigation_id, section, type, refs, producer, payload, ts"""


@dataclass
class ScoutRequest:
    """order_id, investigation_id, question, anchors, assumptions, budget, permitted_tools,
    bundle_ref, answer_schema"""


@dataclass
class ScoutFinding:
    """finding_id, order_id, claim, cites, status, confidence, needs"""


@dataclass
class ContextBundle:
    """bundle_id, order_id, token_budget, items, excluded, unresolved, missing_requirements,
    snapshot"""


@dataclass
class Summary:
    """summary_id, entity_rev, slot, property, conditions, status, fingerprint, depends_on"""


@dataclass
class StrategyEdge:
    """strategy_id, situation_sig, strategy, stats"""


@dataclass
class GhostHint:
    """hint_id, source_investigation, situation_sig, strategy_id, ephemeral, outcome"""


@dataclass
class Lesson:
    """lesson_id, kind, reason, applies_when, refs"""


CONTRACTS = (
    ProgramEntity,
    GraphEdge,
    Evidence,
    LedgerEvent,
    ScoutRequest,
    ScoutFinding,
    ContextBundle,
    Summary,
    StrategyEdge,
    GhostHint,
    Lesson,
)
