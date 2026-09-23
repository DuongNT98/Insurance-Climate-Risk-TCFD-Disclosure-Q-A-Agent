"""AgentCore Platform v1.0 - INS-C2-013 InsuranceSectorOverlayNode (inner node, last step).

For insurance_sector_specific / iais_supervision queries, retrieve from the
iais_ins_climate KB namespace (TCFD Insurance Working Group outputs + IAIS
Application Paper on Climate Risk to Insurance 2021 + IAIS supervisory
material) — this is the INS-specific differentiator versus a generic FIN
TCFD template. This node also composes the final answer text (last inner
step before the outer post_process gate re-checks it).
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import IAIS_INS_CLIMATE_KB, compose_answer, retrieve_iais_provisions


class InsuranceSectorOverlayNode(FunctionNode):
    """Overlay IAIS/insurance-sector provisions (when applicable) and compose the final answer."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(
        self,
        kb: list[dict[str, Any]] | None = None,
        tcfd_recommendation_version: str = "2017",
        fsa_guidance_vintage: str = "2025",
    ) -> None:
        super().__init__()
        self._kb = kb if kb is not None else IAIS_INS_CLIMATE_KB
        self._tcfd_recommendation_version = tcfd_recommendation_version
        self._fsa_guidance_vintage = fsa_guidance_vintage

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        category = state.get("query_category", "")
        tcfd_provisions = from_json(state.get("retrieved_tcfd_provisions"), [])

        if not category:
            emit_trace_event(
                "ins_sector_overlay_rejected",
                {"correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InsuranceSectorOverlayNode: missing query_category — upstream not trusted blindly"],
            }

        overlay = bool(state.get("needs_insurance_overlay"))
        iais_provisions = retrieve_iais_provisions(category, self._kb) if overlay else []

        answer_text, scenario_applicable, disclosure_format_guidance, methodology_citation, kb_source_ref = (
            compose_answer(
                category,
                tcfd_provisions,
                iais_provisions,
                self._tcfd_recommendation_version,
                self._fsa_guidance_vintage,
            )
        )

        emit_trace_event(
            "ins_sector_overlay_applied",
            {"query_category": category, "overlay_applied": overlay, "iais_provision_count": len(iais_provisions)},
            state,
        )

        return {
            "answer_text": answer_text,
            "scenario_applicable": to_json(scenario_applicable),
            "disclosure_format_guidance": disclosure_format_guidance,
            "methodology_citation": methodology_citation,
            "kb_source_ref": to_json(kb_source_ref),
            "status": AgentStatus.SUCCESS.value,
        }
