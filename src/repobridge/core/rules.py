"""Rules that span several records (docs/contracts.md, "Invariants").

Checks return a list of human-readable violations (empty means OK) so the acceptance gate
(Stage E) can send the reasons back to a scout.
"""

import dataclasses
from collections.abc import Iterable, Mapping

from repobridge.core.schemas import (
    ContextBundle,
    ScoutFinding,
    ScoutRequest,
    Status,
    Summary,
)

REUSE_MIN_STATUS = Status.CHECKED


def check_finding_grounded(finding: ScoutFinding, bundle: ContextBundle) -> list[str]:
    """A finding may only cite items that were in the bundle its scout received."""
    problems = []
    if finding.order_id != bundle.order_id:
        problems.append(
            f"finding answers {finding.order_id} but bundle belongs to {bundle.order_id}"
        )
    unseen = sorted(set(finding.cites) - bundle.item_refs)
    if unseen:
        problems.append(f"cites items not in bundle {bundle.bundle_id}: {unseen}")
    return problems


def check_request_matches_bundle(request: ScoutRequest, bundle: ContextBundle) -> list[str]:
    problems = []
    if request.bundle_ref != bundle.bundle_id:
        problems.append(f"request points at {request.bundle_ref}, not {bundle.bundle_id}")
    if request.order_id != bundle.order_id:
        problems.append(f"bundle was built for {bundle.order_id}, not {request.order_id}")
    if bundle.tokens_used > request.budget.input_tokens:
        problems.append(
            f"bundle uses {bundle.tokens_used} tokens, over the request's input "
            f"budget of {request.budget.input_tokens}"
        )
    return problems


def check_assumptions_closed(request: ScoutRequest, accepted: Iterable[str]) -> list[str]:
    """Every assumption a work order relies on must already be an accepted record."""
    missing = sorted(set(request.assumptions) - set(accepted))
    return [f"assumptions not yet accepted: {missing}"] if missing else []


def is_reusable(summary: Summary) -> bool:
    """Only summaries at ``checked`` or above are served across investigations."""
    return summary.status.at_least(REUSE_MIN_STATUS)


def stale_entities(summary: Summary, current: Mapping[str, str]) -> list[str]:
    """Entities whose current fingerprint differs from (or is missing versus) the summary's."""
    return sorted(e for e, fp in summary.fingerprints.items() if current.get(e) != fp)


def invalidate(summary: Summary, current: Mapping[str, str]) -> Summary:
    """Send a summary back to ``proposed`` if any source it relies on has changed.

    This is the only way a record moves *down* the status lattice. A refuted summary stays
    refuted."""
    if summary.status is Status.REFUTED or not stale_entities(summary, current):
        return summary
    return dataclasses.replace(summary, status=Status.PROPOSED)
