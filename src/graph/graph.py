"""AgentCore Platform v1.0 - INS-C2-013 outer graph (Cat 2).

Cat 2: outer AgentBaseGraph with the fixed 5-node backbone. Domain complexity
(TCFD/FSA classification + retrieval + insurance-sector IAIS overlay) is
encapsulated in TCFDGraphNode (the `main` slot), which wraps the inner
TCFDDisclosureWorkflowGraph. Do NOT override add_edges().

Backbone: initialize -> pre_process(InputSanitizeNode) -> main(GraphNode)
          -> post_process(OutputGateNode) -> finalize

TCFDGraphNode lives here (not under src/nodes/) - the PB-6 invoke-order test
only discovers BaseNode subclasses under src/nodes/, and a GraphNode's
__call__ intentionally skips the standard S-2/S-4/S-3 lifecycle (gating is
delegated to the inner subgraph).
"""

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import OutputGateNode
from src.nodes.pre_process_node import InputSanitizeNode
from src.schemas.state import State


class TCFDGraphNode(GraphNode):
    """Wraps the inner TCFD/IAIS climate-disclosure Q&A workflow (Cat 2 composition)."""

    # S-1 (proactive audit #396): outer main-slot wrapper - first node in the
    # outer backbone receiving caller input. Matches agent.yaml
    # required_trust_level + sibling outer nodes (pre_process/post_process).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    # "propagate": re-raise inner errors as SubgraphError (fail fast - default).
    error_strategy: ClassVar[str] = "propagate"
    # No HITL in this template.
    propagate_hitl: ClassVar[bool] = False

    def __init__(
        self,
        tcfd_kb: Any = None,
        iais_kb: Any = None,
        llm: Any = None,
        tcfd_recommendation_version: str = "2017",
        fsa_guidance_vintage: str = "2025",
    ) -> None:
        super().__init__()
        self._tcfd_kb = tcfd_kb
        self._iais_kb = iais_kb
        self._llm = llm
        self._tcfd_recommendation_version = tcfd_recommendation_version
        self._fsa_guidance_vintage = fsa_guidance_vintage

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import TCFDDisclosureWorkflowGraph

        sg = TCFDDisclosureWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        emit_trace_event(
            "tcfd_disclosure_workflow_dispatched", {"correlation_id": state.get("correlation_id", "")}, state
        )
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "tcfd_disclosure_workflow_completed",
            {"correlation_id": state.get("correlation_id", ""), "status": str(sub_result.get("status"))},
            state,
        )
        return {
            "query_category": sub_result.get("query_category"),
            "advice_blocked": sub_result.get("advice_blocked"),
            "needs_insurance_overlay": sub_result.get("needs_insurance_overlay"),
            "answer_text": sub_result.get("answer_text"),
            "scenario_applicable": sub_result.get("scenario_applicable"),
            "disclosure_format_guidance": sub_result.get("disclosure_format_guidance"),
            "methodology_citation": sub_result.get("methodology_citation"),
            "kb_source_ref": sub_result.get("kb_source_ref"),
            "result": sub_result.get("output"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {
            "tcfd_kb": self._tcfd_kb,
            "iais_kb": self._iais_kb,
            "llm": self._llm,
            "tcfd_recommendation_version": self._tcfd_recommendation_version,
            "fsa_guidance_vintage": self._fsa_guidance_vintage,
        }


class TCFDClimateDisclosureAgent(AgentBaseGraph):
    """INS-C2-013 - Insurance Climate Risk & TCFD Disclosure Q&A Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "ins-c2-013"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize

        tcfd_kb = self.config.get("tcfd_kb")
        iais_kb = self.config.get("iais_kb")
        llm = self.config.get("llm")
        tcfd_version = self.config.get("tcfd_recommendation_version", "2017")
        fsa_vintage = self.config.get("fsa_guidance_vintage", "2025")

        self._nodes["pre_process"] = InputSanitizeNode()
        self._nodes["main"] = TCFDGraphNode(
            tcfd_kb=tcfd_kb,
            iais_kb=iais_kb,
            llm=llm,
            tcfd_recommendation_version=tcfd_version,
            fsa_guidance_vintage=fsa_vintage,
        )
        self._nodes["post_process"] = OutputGateNode()

    # add_edges() is NOT overridden - backbone wiring belongs to the framework.


# Alias for agent.yaml module:"src.graph" resolution (AgentRegistry / api/server.py).
Graph = TCFDClimateDisclosureAgent
