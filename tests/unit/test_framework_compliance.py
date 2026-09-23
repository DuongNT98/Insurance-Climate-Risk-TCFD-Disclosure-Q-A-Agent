# INS-C2-013 - Framework compliance tests TC-01..TC-08 (proactive code review, ticket #396).
# Reference shape: an established sibling Cat 2 template's framework compliance test suite,
# adapted to this template's real architecture (Cat 2: outer pre/post + GraphNode-wrapped inner nodes).

import os
import re
import typing
from typing import NotRequired

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import post_process_node, pre_process_node, query_classify_node
from src.schemas.state import State

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.VERIFIED_EXTERNAL.value


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def _unwrap(ann):
    """Strip NotRequired[...] so the underlying primitive type can be checked."""
    if typing.get_origin(ann) is NotRequired:
        args = typing.get_args(ann)
        return args[0] if args else ann
    return ann


# TC-01 - State is a flat TypedDict extending AgentState, added fields are JSON-safe primitives.
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "user_input" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_json_safe(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        allowed = {"str", "int", "bool", "float", "list", "dict"}
        for name in added:
            ann = _unwrap(State.__annotations__[name])
            origin = typing.get_origin(ann)
            ann_str = getattr(origin or ann, "__name__", str(ann))
            assert ann_str in allowed, f"{name}: {ann_str} - must be msgpack-safe (no Pydantic/dataclass)"


# TC-02 - Empty/missing input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        node = pre_process_node.InputSanitizeNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_missing_query_category_no_raise(self):
        node = query_classify_node.QueryClassifyNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads (the
# entry-point caller-auth token in the standalone API adapter is the sole
# allowed exception, per the framework's documented entry-point auth exception).
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []

    def test_no_os_environ_secret_reads_outside_entrypoint(self):
        entrypoint = os.path.join(_SRC, "api", "server.py")
        offenders = []
        for fp in _src_files():
            if os.path.abspath(fp) == os.path.abspath(entrypoint):
                continue
            with open(fp, encoding="utf-8") as f:
                if "os.environ" in f.read():
                    offenders.append(fp)
        assert offenders == []


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        agent = Graph()
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="agent-tc04")
        result = agent.invoke("What TCFD disclosure format applies to physical risk?", ctx=ctx)
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: every node emits >=1 domain event on its success path;
# no node under src/nodes/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_pre_process_node_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(pre_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = pre_process_node.InputSanitizeNode().execute({"user_input": "物理的リスクの開示について教えてください"})
        assert out["status"] == AgentStatus.SUCCESS
        assert len(events) >= 1
        assert "ins_tcfd_query_sanitized" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_post_process_node_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(post_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = post_process_node.OutputGateNode().execute(
            {"answer_text": "answer", "methodology_citation": "TCFD Recommendations v2017", "advice_blocked": False, "user_input": "物理的リスクについて"}
        )
        assert out["status"] == AgentStatus.SUCCESS
        assert len(events) >= 1
        assert "output_gate_citation_verified" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-06 / TC-07 - S-2/S-3 gates are @final on FunctionNode (overriding raises TypeError at class def).
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_hook_is_overridable(self):
        assert post_process_node.OutputGateNode._extra_security_gate_output is not FunctionNode._extra_security_gate_output

    def test_output_gate_blocks_missing_disclaimer(self):
        # The @final S-3 preservation gate actually fires (not vacuous): output
        # missing the mandatory scope-advisory disclaimer is blocked, never
        # returned as-is, when advice_blocked is set.
        node = post_process_node.OutputGateNode()
        out = node._extra_security_gate_output({"answer_text": "not the disclaimer", "advice_blocked": True})
        assert out["status"] == AgentStatus.ERROR


# TC-08 - required_trust_level enforced: insufficient trust -> ERROR state, no raise.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        from src.graph.graph import TCFDGraphNode

        for cls in (
            pre_process_node.InputSanitizeNode,
            post_process_node.OutputGateNode,
            TCFDGraphNode,
            query_classify_node.QueryClassifyNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        from src.graph.graph import TCFDGraphNode

        node = TCFDGraphNode(tcfd_kb=None, iais_kb=None, llm=None)
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "validated_input": "{}"})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = pre_process_node.InputSanitizeNode()
        out = node(
            {
                "caller_trust_level": TRUST,
                "user_input": "物理的リスクの開示について教えてください",
            }
        )
        assert out["status"] == AgentStatus.SUCCESS
