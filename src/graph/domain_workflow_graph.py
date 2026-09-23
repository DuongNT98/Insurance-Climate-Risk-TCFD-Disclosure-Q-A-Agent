"""AgentCore Platform v1.0 - INS-C2-013 inner domain workflow graph.

Cat 2 inner graph: query classification -> TCFD/FSA KB retrieval ->
insurance-sector IAIS overlay + answer composition. Instantiated by
TCFDGraphNode.get_subgraph() in graph.py.

Pipeline (linear, fail-fast on ERROR):
    START -> query_classify -> tcfd_retrieve -> insurance_sector_overlay -> END
"""

from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.insurance_sector_overlay_node import InsuranceSectorOverlayNode
from src.nodes.query_classify_node import QueryClassifyNode
from src.nodes.tcfd_retrieve_node import TCFDRetrieveNode
from src.schemas.state import State


class TCFDDisclosureWorkflowGraph(BaseGraph):
    """Inner graph for the INS-C2-013 TCFD/IAIS climate-disclosure Q&A workflow."""

    @property
    def name(self) -> str:
        return "tcfd-disclosure-workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config: kb/llm are optional (empty KB -> "not found" answer).
        pass

    def register_nodes(self) -> None:
        # No super() - BaseGraph.register_nodes() is abstract.
        tcfd_kb = self.config.get("tcfd_kb")
        iais_kb = self.config.get("iais_kb")
        llm = self.config.get("llm")
        tcfd_version = self.config.get("tcfd_recommendation_version", "2017")
        fsa_vintage = self.config.get("fsa_guidance_vintage", "2025")

        self._nodes["query_classify"] = QueryClassifyNode(llm=llm)
        self._nodes["tcfd_retrieve"] = TCFDRetrieveNode(kb=tcfd_kb)
        self._nodes["insurance_sector_overlay"] = InsuranceSectorOverlayNode(
            kb=iais_kb, tcfd_recommendation_version=tcfd_version, fsa_guidance_vintage=fsa_vintage
        )

    def add_edges(self) -> None:
        self._sg.add_edge(START, "query_classify")
        self._sg.add_conditional_edges(
            "query_classify",
            lambda s: END if self._is_error(s) else "tcfd_retrieve",
            {"tcfd_retrieve": "tcfd_retrieve", END: END},
        )
        self._sg.add_conditional_edges(
            "tcfd_retrieve",
            lambda s: END if self._is_error(s) else "insurance_sector_overlay",
            {"insurance_sector_overlay": "insurance_sector_overlay", END: END},
        )
        self._sg.add_edge("insurance_sector_overlay", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        return state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value)

    def route(self, state: AgentState) -> str:
        return END if self._is_error(state) else "insurance_sector_overlay"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "query_category": state.get("query_category"),
            "advice_blocked": state.get("advice_blocked"),
            "needs_insurance_overlay": state.get("needs_insurance_overlay"),
            "answer_text": state.get("answer_text"),
            "scenario_applicable": state.get("scenario_applicable"),
            "disclosure_format_guidance": state.get("disclosure_format_guidance"),
            "methodology_citation": state.get("methodology_citation"),
            "kb_source_ref": state.get("kb_source_ref"),
            "output": state.get("answer_text"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
