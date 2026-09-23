"""AgentCore Platform v1.0 - INS-C2-013 InputSanitizeNode (outer pre_process slot).

Validate the incoming query, extract a preliminary query_category, and apply
the non-suppressible scope-advisory gate: this agent answers TCFD/IAIS
methodology and compliance questions only — it must never attempt
portfolio-specific climate risk quantification, which requires a qualified
climate risk specialist.
"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import classify_query_category, detect_portfolio_quantification, normalize_query


class InputSanitizeNode(FunctionNode):
    """Validate input, classify preliminary category, and gate portfolio-specific quantification requests."""

    # S-1: outer boundary node — matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = state.get("user_input", "")

        normalized, error = normalize_query(user_input)
        if error:
            emit_trace_event(
                "ins_tcfd_query_rejected",
                {"correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"InputSanitizeNode: {error}"],
            }

        advice_blocked = detect_portfolio_quantification(normalized)
        query_category = classify_query_category(normalized)

        emit_trace_event(
            "ins_tcfd_query_sanitized",
            {
                "advice_blocked": advice_blocked,
                "query_category": query_category,
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )

        # Cat 2: GraphNode.extract_input() only forwards a string to the inner
        # subgraph — pass the JSON envelope through validated_input so the
        # inner pipeline's first node can re-derive advice_blocked/category
        # (defense-in-depth, per the GraphNode-boundary-drops-fields lesson).
        payload = json.dumps(
            {"query": normalized, "advice_blocked": advice_blocked, "query_category": query_category},
            ensure_ascii=False,
        )

        return {
            "validated_input": payload,
            "advice_blocked": advice_blocked,
            "query_category": query_category,
            "status": AgentStatus.SUCCESS.value,
        }
