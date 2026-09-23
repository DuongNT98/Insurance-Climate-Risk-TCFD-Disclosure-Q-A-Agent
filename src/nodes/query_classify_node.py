"""AgentCore Platform v1.0 - INS-C2-013 QueryClassifyNode (inner node, LLM-enhanced).

Classify the query into one of six TCFD/IAIS categories. Re-derives the
category and the scope-advisory flag from the raw query rather than trusting
the outer InputSanitizeNode's flags blindly — the inner subgraph only
receives the JSON envelope via GraphNode.extract_input(), and pre_process ->
main is an unconditional edge in AgentBaseGraph, so an outer rejection alone
does not stop the pipeline from reaching this node.

LLM refinement (Azure OpenAI) is a best-effort enhancement over the
deterministic classifier, never a hard dependency: any failure to resolve
secrets, build the client, or get a usable response degrades silently to
classify_query_category(query) — this node must always produce a category.
"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import classify_query_category, detect_portfolio_quantification, needs_insurance_overlay


class QueryClassifyNode(FunctionNode):
    """LLM-assisted classification into the six TCFD/IAIS query categories."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        super().__init__()
        # Test-double seam only — production wiring (register_nodes()) never
        # passes a real client here; _resolve_llm() builds one per invocation
        # from ctx.secrets instead (a node instance is constructed once and
        # reused across every invocation via the registry's LRU cache, so a
        # client cached on self would leak across callers/secrets).
        self._llm = llm

    @staticmethod
    def _extract_text(raw: Any) -> str:
        """Normalise BaseLLM.complete() response — canonical shape is a dict
        {"content": str, ...}; some fakes still return a bare string."""
        if isinstance(raw, dict):
            content = raw.get("content", "")
            return content if isinstance(content, str) else ""
        if isinstance(raw, str):
            return raw
        return ""

    def _resolve_llm(self, state: dict[str, Any]) -> Any:
        if self._llm is not None:
            return self._llm
        try:
            from shared.services.llm.azure_openai_client import AzureOpenAIClient

            ctx = InvocationContext.from_state(state)
            return AzureOpenAIClient(
                {
                    "api_key": ctx.secrets.require("AZURE_OPENAI_API_KEY"),
                    "azure_endpoint": ctx.secrets.require("AZURE_OPENAI_ENDPOINT"),
                    "azure_deployment": ctx.secrets.require("AZURE_OPENAI_DEPLOYMENT"),
                }
            )
        except Exception:  # noqa: BLE001 - any resolution failure degrades to the deterministic classifier
            return None

    def _llm_classify(self, query: str, state: dict[str, Any]) -> str | None:
        """Best-effort LLM category — returns None (never raises) on any failure."""
        llm = self._resolve_llm(state)
        if llm is None:
            return None
        try:
            raw = llm.complete([{"role": "user", "content": f"classify_tcfd_query_category: {query}"}])
            text = self._extract_text(raw).strip()
        except Exception as exc:  # noqa: BLE001 - degrade, never propagate a provider error
            emit_trace_event(
                "ins_tcfd_query_classify_llm_degraded",
                {"correlation_id": state.get("correlation_id", ""), "error": str(exc)},
                state,
            )
            return None
        if not text:
            emit_trace_event(
                "ins_tcfd_query_classify_llm_degraded",
                {"correlation_id": state.get("correlation_id", ""), "error": "empty LLM response"},
                state,
            )
            return None
        return text if text in _VALID_CATEGORIES else None

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # BaseGraph.invoke() (inner subgraph entry) seeds "user_input" with
        # whatever GraphNode.extract_input() returned - the outer
        # validated_input JSON envelope, not the outer state's own fields.
        raw = state.get("user_input", "")
        try:
            envelope = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            envelope = {}

        query = envelope.get("query") or raw
        if not query:
            emit_trace_event(
                "ins_tcfd_query_classify_rejected",
                {"correlation_id": state.get("correlation_id", "")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["QueryClassifyNode: empty query — upstream not trusted blindly"],
            }

        # Re-check the scope-advisory gate here too (defense-in-depth):
        # don't trust the outer envelope's advice_blocked flag alone.
        advice_blocked = bool(envelope.get("advice_blocked")) or detect_portfolio_quantification(query)

        # LLM refines/confirms the deterministic category on a best-effort basis —
        # any failure (no secrets configured, provider error, malformed/wrong-shape
        # response) silently degrades to the deterministic classifier below.
        llm_category = self._llm_classify(query, state)
        category = llm_category or envelope.get("query_category") or classify_query_category(query)

        overlay = needs_insurance_overlay(category)

        emit_trace_event(
            "ins_tcfd_query_classified",
            {"query_category": category, "advice_blocked": advice_blocked, "needs_insurance_overlay": overlay},
            state,
        )

        return {
            "query_category": category,
            "advice_blocked": advice_blocked,
            "needs_insurance_overlay": overlay,
            "status": AgentStatus.SUCCESS.value,
        }


_VALID_CATEGORIES = (
    "physical_risk",
    "transition_risk",
    "scenario_analysis",
    "disclosure_format",
    "insurance_sector_specific",
    "iais_supervision",
)
