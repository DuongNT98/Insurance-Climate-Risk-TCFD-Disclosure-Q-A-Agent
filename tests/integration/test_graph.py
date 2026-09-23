# INS-C2-013 - Integration test: full graph compile + invoke (Cat 2 outer + inner).
#
# AgentBaseGraph.get_output() derives the top-level invoke() "output" key
# from formatted_output/result (not from domain-specific state fields such
# as answer_text) - assert against result["output"].

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph

PHYSICAL_RISK_QUERY = "物理的リスクの開示について教えてください"
IAIS_QUERY = "IAIS の保険監督上の期待について教えてください"
EMPTY_QUERY = ""
PORTFOLIO_QUANT_QUERY = "自社ポートフォリオのリスク量を算出してください"


class TestAgentIntegration:
    def test_physical_risk_question_with_kb_match(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="agent-001")
        result = agent.invoke(PHYSICAL_RISK_QUERY, ctx=ctx)

        assert result["status"] == "success"
        assert len(result.get("node_history", [])) >= 5

    def test_iais_supervision_question_gets_insurance_overlay(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-2", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="agent-001")
        result = agent.invoke(IAIS_QUERY, ctx=ctx)

        assert result["status"] == "success"
        assert "IAIS" in (result.get("output") or "")

    def test_empty_query_error(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-3", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="agent-001")
        result = agent.invoke(EMPTY_QUERY, ctx=ctx)
        assert result["status"] in ("error", "cancelled")

    def test_portfolio_quantification_request_blocked_with_disclaimer(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-4", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="agent-001")
        result = agent.invoke(PORTFOLIO_QUANT_QUERY, ctx=ctx)

        assert result["status"] == "success"
        answer = result.get("output") or ""
        assert "専門家にご相談ください" in answer
