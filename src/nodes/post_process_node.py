"""AgentCore Platform v1.0 - INS-C2-013 OutputGateNode (outer post_process slot).

Final, non-suppressible S-3 output gate. Re-derives advice_blocked at the
point closest to the final output (does not trust the inner-subgraph-merged
flag alone — GraphNode.extract_input() only forwards a JSON envelope across
the subgraph boundary, so this is the safest place to re-check). When
blocked, the scope-advisory disclaimer replaces any inner-composed answer.
When not blocked, verifies the TCFD/FSA/IAIS methodology citation is present
in every answer.

Sets both `answer_text` (domain field) and `result` (AgentState shared
field) — AgentBaseGraph.get_output() derives the top-level invoke() "output"
key from `formatted_output` or `result`, not from domain-specific fields.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import SCOPE_ADVISORY_DISCLAIMER, detect_portfolio_quantification


class OutputGateNode(FunctionNode):
    """Enforce the non-suppressible scope-advisory gate and the citation requirement."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Non-suppressible re-derivation, closest point to final output — do
        # not trust the inner-subgraph-forwarded advice_blocked flag alone.
        advice_blocked = bool(state.get("advice_blocked")) or detect_portfolio_quantification(
            state.get("user_input", "")
        )

        if advice_blocked:
            emit_trace_event(
                "output_gate_scope_advisory_blocked", {"correlation_id": state.get("correlation_id", "")}, state
            )
            return {
                "answer_text": SCOPE_ADVISORY_DISCLAIMER,
                "result": SCOPE_ADVISORY_DISCLAIMER,
                "advice_blocked": True,
                "status": AgentStatus.SUCCESS.value,
            }

        answer_text = state.get("answer_text", "")
        methodology_citation = state.get("methodology_citation", "")
        if methodology_citation and methodology_citation not in answer_text:
            answer_text = f"{answer_text} [{methodology_citation}]"

        emit_trace_event("output_gate_citation_verified", {"has_citation": bool(methodology_citation)}, state)

        return {
            "answer_text": answer_text,
            "result": answer_text,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Non-suppressible re-check on the output dict's own field: the
        disclaimer must be present when advice_blocked, else the methodology
        citation must be present. Filter/re-check only — never raises."""
        answer_text = state.get("answer_text", "")

        if state.get("advice_blocked"):
            if SCOPE_ADVISORY_DISCLAIMER not in answer_text:
                emit_trace_event("output_gate_disclaimer_recheck_blocked", {}, state)
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [
                        "OutputGateNode: S-3 re-check — advice_blocked answer missing the scope-advisory disclaimer"
                    ],
                }
            return state

        methodology_citation = state.get("methodology_citation", "")
        if methodology_citation and methodology_citation not in answer_text:
            emit_trace_event("output_gate_citation_recheck_blocked", {}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputGateNode: S-3 re-check — answer missing required methodology citation"],
            }
        return state
