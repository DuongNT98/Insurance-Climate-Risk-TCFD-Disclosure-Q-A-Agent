# INS-C2-013 - Unit tests: per-node success + error/edge paths.

import json

from framework.schemas.agent_status import AgentStatus

import src.nodes.insurance_sector_overlay_node as insurance_sector_overlay_node
import src.nodes.pre_process_node as pre_process_node
import src.nodes.query_classify_node as query_classify_node
import src.nodes.tcfd_retrieve_node as tcfd_retrieve_node
from src.nodes.insurance_sector_overlay_node import InsuranceSectorOverlayNode
from src.nodes.post_process_node import OutputGateNode
from src.nodes.pre_process_node import InputSanitizeNode
from src.nodes.query_classify_node import QueryClassifyNode
from src.nodes.tcfd_retrieve_node import TCFDRetrieveNode
from src.schemas.state import from_json, to_json
from src.services.service import SCOPE_ADVISORY_DISCLAIMER

TCFD_KB = [
    {
        "category": "physical_risk",
        "provision_id": "TCFD-2017-PhysicalRisk-1",
        "summary": "physical risk disclosure",
        "source": "TCFD Final Recommendations (2017)",
    },
]

IAIS_KB = [
    {
        "category": "iais_supervision",
        "provision_id": "IAIS-AppPaper-2021-Supervision-1",
        "summary": "supervisory expectations",
        "source": "IAIS Application Paper on Climate Risk to Insurance (2021)",
    },
]


class TestInputSanitizeNode:
    def test_success_methodology_question(self):
        state = {"user_input": "物理的リスクの開示について教えてください"}
        r = InputSanitizeNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["advice_blocked"] is False
        envelope = json.loads(r["validated_input"])
        assert envelope["query_category"] == "physical_risk"

    def test_empty_query_error(self):
        assert InputSanitizeNode().execute({"user_input": ""})["status"] == AgentStatus.ERROR

    def test_portfolio_quantification_flagged_blocked(self):
        state = {"user_input": "自社ポートフォリオのリスク量を算出してください"}
        r = InputSanitizeNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["advice_blocked"] is True


class TestQueryClassifyNode:
    def test_success_from_envelope(self):
        envelope = json.dumps({"query": "移行リスクについて", "advice_blocked": False, "query_category": "transition_risk"})
        r = QueryClassifyNode().execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["query_category"] == "transition_risk"
        assert r["needs_insurance_overlay"] is False

    def test_insurance_sector_routes_overlay(self):
        envelope = json.dumps({"query": "IAIS 保険監督の期待について", "advice_blocked": False, "query_category": "iais_supervision"})
        r = QueryClassifyNode().execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["needs_insurance_overlay"] is True

    def test_empty_query_error(self):
        assert QueryClassifyNode().execute({"user_input": ""})["status"] == AgentStatus.ERROR

    def test_recheck_blocks_even_if_envelope_says_false(self):
        envelope = json.dumps({"query": "自社ポートフォリオの気候VaRを計算してください", "advice_blocked": False, "query_category": "disclosure_format"})
        r = QueryClassifyNode().execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["advice_blocked"] is True

    def test_llm_canonical_dict_response_consumed(self):
        """3m: BaseLLM.complete() returns a dict — must be extracted, not discarded."""

        class DictLLM:
            def complete(self, messages):
                assert isinstance(messages, list)
                return {"content": "scenario_analysis"}

        envelope = json.dumps({"query": "シナリオ分析について", "advice_blocked": False})
        r = QueryClassifyNode(llm=DictLLM()).execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["query_category"] == "scenario_analysis"

    def test_llm_failure_degrades_to_deterministic_fallback(self):
        """A configured-but-failing LLM (Step 8e contract) must degrade, never error."""

        class RaisingLLM:
            def complete(self, messages):
                raise RuntimeError("provider timeout")

        envelope = json.dumps({"query": "物理的リスクについて", "advice_blocked": False})
        r = QueryClassifyNode(llm=RaisingLLM()).execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["query_category"] == "physical_risk"

    def test_llm_empty_response_degrades_to_deterministic_fallback(self):
        class EmptyLLM:
            def complete(self, messages):
                return {"content": ""}

        envelope = json.dumps({"query": "物理的リスクについて", "advice_blocked": False})
        r = QueryClassifyNode(llm=EmptyLLM()).execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["query_category"] == "physical_risk"

    def test_llm_wrong_shape_response_degrades_to_deterministic_fallback(self):
        """A non-category free-text response is not one of _VALID_CATEGORIES — degrade, don't error."""

        class ProseLLM:
            def complete(self, messages):
                return {"content": "I think this question is about physical climate risk, broadly."}

        envelope = json.dumps({"query": "物理的リスクについて", "advice_blocked": False})
        r = QueryClassifyNode(llm=ProseLLM()).execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["query_category"] == "physical_risk"

    def test_no_llm_configured_uses_deterministic_fallback(self):
        """No test-double injected and no secret bound (NullProvider) — degrades cleanly."""
        envelope = json.dumps({"query": "移行リスクについて", "advice_blocked": False, "query_category": "transition_risk"})
        r = QueryClassifyNode(llm=None).execute({"user_input": envelope})
        assert r["status"] == AgentStatus.SUCCESS
        assert r["query_category"] == "transition_risk"

    def test_llm_build_missing_lifecycle_fields_degrades_not_raises(self):
        """PB-6 safety: InvocationContext.from_state() indexes lifecycle fields that a
        bare state (no correlation_id/session_id/thread_id/trace_id) won't have —
        _resolve_llm() must swallow that KeyError, not let it escape execute()."""
        envelope = json.dumps({"query": "物理的リスクについて", "advice_blocked": False})
        r = QueryClassifyNode().execute({"user_input": envelope})  # no llm=, no lifecycle fields
        assert r["status"] == AgentStatus.SUCCESS
        assert r["query_category"] == "physical_risk"


class TestTCFDRetrieveNode:
    def test_success(self):
        state = {"query_category": "physical_risk"}
        r = TCFDRetrieveNode(kb=TCFD_KB).execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        provisions = from_json(r["retrieved_tcfd_provisions"], [])
        assert len(provisions) == 1

    def test_missing_category_error(self):
        assert TCFDRetrieveNode(kb=TCFD_KB).execute({"query_category": ""})["status"] == AgentStatus.ERROR


class TestInsuranceSectorOverlayNode:
    def test_success_no_overlay(self):
        state = {
            "query_category": "physical_risk",
            "needs_insurance_overlay": False,
            "retrieved_tcfd_provisions": to_json(TCFD_KB),
        }
        r = InsuranceSectorOverlayNode(kb=IAIS_KB).execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert "TCFD-2017-PhysicalRisk-1" in r["answer_text"]

    def test_success_with_iais_overlay(self):
        state = {
            "query_category": "iais_supervision",
            "needs_insurance_overlay": True,
            "retrieved_tcfd_provisions": to_json([]),
        }
        r = InsuranceSectorOverlayNode(kb=IAIS_KB).execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert "IAIS-AppPaper-2021-Supervision-1" in r["answer_text"]
        assert "IAIS" in r["methodology_citation"]

    def test_missing_category_error(self):
        state = {"query_category": "", "needs_insurance_overlay": False, "retrieved_tcfd_provisions": to_json([])}
        assert InsuranceSectorOverlayNode(kb=IAIS_KB).execute(state)["status"] == AgentStatus.ERROR


class TestOutputGateNode:
    def test_success_appends_citation(self):
        state = {
            "answer_text": "physical risk answer",
            "methodology_citation": "TCFD Recommendations v2017; FSA Guidance 2025",
            "advice_blocked": False,
            "user_input": "物理的リスクについて",
        }
        r = OutputGateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert "TCFD Recommendations v2017" in r["answer_text"]

    def test_advice_blocked_returns_disclaimer(self):
        state = {"answer_text": "should not matter", "advice_blocked": True, "user_input": "自社ポートフォリオの気候VaRを計算して"}
        r = OutputGateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["answer_text"] == SCOPE_ADVISORY_DISCLAIMER

    def test_recheck_blocks_when_inner_flag_missed_a_portfolio_query(self):
        # advice_blocked False from upstream, but the raw user_input is itself
        # a portfolio-quantification request - the outer gate must catch it.
        state = {"answer_text": "some answer", "advice_blocked": False, "user_input": "自社ポートフォリオのリスク量を算出してください"}
        r = OutputGateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["answer_text"] == SCOPE_ADVISORY_DISCLAIMER

    def test_extra_gate_blocks_missing_disclaimer(self):
        bad_state = {"answer_text": "not the disclaimer", "advice_blocked": True}
        out = OutputGateNode()._extra_security_gate_output(bad_state)
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_blocks_missing_citation(self):
        bad_state = {"answer_text": "answer without citation", "advice_blocked": False, "methodology_citation": "TCFD Recommendations v2017; FSA Guidance 2025"}
        out = OutputGateNode()._extra_security_gate_output(bad_state)
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_passthrough_clean_answer(self):
        good_state = {"answer_text": "answer [TCFD Recommendations v2017; FSA Guidance 2025]", "advice_blocked": False, "methodology_citation": "TCFD Recommendations v2017; FSA Guidance 2025"}
        assert OutputGateNode()._extra_security_gate_output(good_state) is good_state


class TestS4EmitTraceEvent:
    """S-4 (proactive audit #396): every execute() path — success AND early-return
    reject — must emit a domain event. Patch emit_trace_event in each node's OWN
    module namespace (the node imported the symbol there), not audit_logger."""

    def _assert_non_sensitive(self, events):
        assert events, "expected at least one emit_trace_event call"
        for _name, payload, _state in events:
            for key, value in payload.items():
                assert not isinstance(value, str) or len(value) < 200, f"payload key {key!r} looks like raw content, not a count/flag"

    def test_pre_process_success_and_error_both_emit(self, monkeypatch):
        events = []
        monkeypatch.setattr(pre_process_node, "emit_trace_event", lambda name, payload, state: events.append((name, payload, state)))

        InputSanitizeNode().execute({"user_input": "物理的リスクの開示について教えてください"})
        InputSanitizeNode().execute({"user_input": ""})

        assert len(events) == 2
        self._assert_non_sensitive(events)

    def test_query_classify_success_and_error_both_emit(self, monkeypatch):
        events = []
        monkeypatch.setattr(query_classify_node, "emit_trace_event", lambda name, payload, state: events.append((name, payload, state)))

        envelope = json.dumps({"query": "移行リスクについて", "advice_blocked": False, "query_category": "transition_risk"})
        QueryClassifyNode().execute({"user_input": envelope})
        QueryClassifyNode().execute({"user_input": ""})

        assert len(events) == 2
        self._assert_non_sensitive(events)

    def test_tcfd_retrieve_success_and_error_both_emit(self, monkeypatch):
        events = []
        monkeypatch.setattr(tcfd_retrieve_node, "emit_trace_event", lambda name, payload, state: events.append((name, payload, state)))

        TCFDRetrieveNode(kb=TCFD_KB).execute({"query_category": "physical_risk"})
        TCFDRetrieveNode(kb=TCFD_KB).execute({"query_category": ""})

        assert len(events) == 2
        self._assert_non_sensitive(events)

    def test_insurance_sector_overlay_success_and_error_both_emit(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            insurance_sector_overlay_node, "emit_trace_event", lambda name, payload, state: events.append((name, payload, state))
        )

        InsuranceSectorOverlayNode(kb=IAIS_KB).execute(
            {"query_category": "physical_risk", "needs_insurance_overlay": False, "retrieved_tcfd_provisions": to_json(TCFD_KB)}
        )
        InsuranceSectorOverlayNode(kb=IAIS_KB).execute(
            {"query_category": "", "needs_insurance_overlay": False, "retrieved_tcfd_provisions": to_json([])}
        )

        assert len(events) == 2
        self._assert_non_sensitive(events)
