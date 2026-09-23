"""AgentCore Platform v1.0 - INS-C2-013 state schema.

Insurance Climate Risk & TCFD Disclosure Q&A Agent.
Flat TypedDict extension of AgentState (ADR-005). All domain payloads that are
structured (list/dict) are JSON-string-encoded before being stored in state
fields, per the workspace's flat-TypedDict + msgpack-safety convention. Every
agent-specific field is wrapped in NotRequired[...] (CoE C8): a checkpoint
resumed mid-pipeline, or a node reached before an upstream field was written,
must never KeyError on a bare field.
"""

import json
from typing import Any, NotRequired

from framework.schemas.agent_state import AgentState


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class State(AgentState):
    """Agent state for INS-C2-013.

    query_category: "physical_risk" | "transition_risk" | "scenario_analysis" |
        "disclosure_format" | "insurance_sector_specific" | "iais_supervision" | "unclassified"
    advice_blocked: True when the query asked for portfolio-specific climate risk
        quantification — out of scope for this methodology/compliance Q&A agent.
    needs_insurance_overlay: True when query_category is insurance_sector_specific
        or iais_supervision — routes the inner pipeline through the IAIS overlay.
    answer_text: final composed answer (TCFD/IAIS citations inline), or the
        non-suppressible scope-advisory disclaimer when advice_blocked is True.
    scenario_applicable: JSON list[str] of applicable IPCC AR6 / NGFS scenarios (may be empty).
    disclosure_format_guidance: TCFD-recommended disclosure format guidance text.
    methodology_citation: TCFD recommendation version + FSA/IAIS guidance citation.
    kb_source_ref: JSON list[str] of KB namespace/provision identifiers actually used.
    retrieved_tcfd_provisions: JSON list[dict] handoff of TCFDRetrieveNode's raw matches,
        consumed by InsuranceSectorOverlayNode to compose the final answer (internal,
        inner-subgraph-only field).
    """

    # mypy can't see that AgentState is a TypedDict at runtime without SDK-side
    # stubs (agenticstar-agentcore ships no py.typed marker), so it rejects
    # NotRequired[...] as used outside a recognised TypedDict definition —
    # a stub-visibility limitation, not a code error; these fields really are
    # optional/JSON-safe at runtime (State extends AgentState, itself a TypedDict).
    query_category: NotRequired[str]  # type: ignore[valid-type]
    advice_blocked: NotRequired[bool]  # type: ignore[valid-type]
    needs_insurance_overlay: NotRequired[bool]  # type: ignore[valid-type]
    answer_text: NotRequired[str]  # type: ignore[valid-type]
    scenario_applicable: NotRequired[str]  # type: ignore[valid-type]
    disclosure_format_guidance: NotRequired[str]  # type: ignore[valid-type]
    methodology_citation: NotRequired[str]  # type: ignore[valid-type]
    kb_source_ref: NotRequired[str]  # type: ignore[valid-type]
    retrieved_tcfd_provisions: NotRequired[str]  # type: ignore[valid-type]
