"""AgentCore Platform v1.0 - INS-C2-013 TCFDRetrieveNode (inner node).

Dense retrieval from the tcfd_fsa_climate KB namespace (TCFD Final
Recommendations 2017 + Supplemental Guidance for the Financial Sector 2020 +
IPCC AR6 scenario summaries + Japan FSA/NGFS/TSE climate-disclosure
guidance), scoped by the query category resolved upstream.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.service import TCFD_FSA_CLIMATE_KB, retrieve_tcfd_provisions


class TCFDRetrieveNode(FunctionNode):
    """Retrieve applicable TCFD/FSA provisions for the resolved query category."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, kb: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._kb = kb if kb is not None else TCFD_FSA_CLIMATE_KB

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        category = state.get("query_category", "")
        if not category:
            emit_trace_event(
                "tcfd_provisions_retrieve_rejected",
                {"correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["TCFDRetrieveNode: missing query_category — upstream not trusted blindly"],
            }

        provisions = retrieve_tcfd_provisions(category, self._kb)

        emit_trace_event(
            "tcfd_provisions_retrieved",
            {"query_category": category, "provision_count": len(provisions)},
            state,
        )

        return {
            "retrieved_tcfd_provisions": to_json(provisions),
            "status": AgentStatus.SUCCESS.value,
        }
