# Test Specification

## Test Strategy
- Coverage target: all BL paths (unit + integration); hard % threshold enforced by CI gate
- Test types: Unit / Integration / Proof-of-Boundary

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | PASS |
| TC-02 | SecurityViolationError fires on invalid input | Error raised | PASS |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | PASS |
| TC-04 | InvocationContext via configurable only | Direct access raises error | PASS |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | PASS |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial when domain checks needed | N/A — scope-advisory check implemented as raise-free business logic in `execute()`, not as an input-gate hook (documented in docs/02_design.md) | N/A |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial when domain checks needed | `OutputGateNode._extra_security_gate_output()` re-checks disclaimer/citation presence | PASS |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path | ≥1 per node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | PASS |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | PASS |
| PB-3 | Level 2 → External service | Mock KB retrieval (in-repo, no live external service in this template) | Data retrieved from mock KB | PASS |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | PASS |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | PASS |
| PB-6 | Invoke execution order | `__call__()`: S-1 → S-4 `node_start` → S-2 → `execute()` → S-3 → S-4 `node_complete` | Order verified for every `src/nodes/` class | PASS |
| PB-7 | HITL interrupt propagation | N/A — `hitl.enabled` is not set (no `interrupt()` in this template); stub auto-skips | Auto-skip | SKIP (by design) |

## LLM Refinement Tests (`QueryClassifyNode` — Azure OpenAI, best-effort)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| LLM-01 | Well-formed LLM category response | Overrides the deterministic classifier | PASS (`test_llm_canonical_dict_response_consumed`) |
| LLM-02 | LLM `complete()` raises | Degrades to deterministic classifier; `status=success`, never `error` | PASS (`test_llm_failure_degrades_to_deterministic_fallback`) |
| LLM-03 | LLM returns an empty response | Degrades to deterministic classifier | PASS (`test_llm_empty_response_degrades_to_deterministic_fallback`) |
| LLM-04 | LLM returns free text not in `_VALID_CATEGORIES` | Degrades to deterministic classifier | PASS (`test_llm_wrong_shape_response_degrades_to_deterministic_fallback`) |
| LLM-05 | No test-double injected, no secret bound (`NullProvider`) | Degrades to deterministic classifier | PASS (`test_no_llm_configured_uses_deterministic_fallback`) |
| LLM-06 | PB-6-style bare state (no `correlation_id`/`session_id`/`thread_id`/`trace_id`) | `_resolve_llm()` swallows the `KeyError`; `execute()` never raises | PASS (`test_llm_build_missing_lifecycle_fields_degrades_not_raises`) |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Physical-risk methodology question | "物理的リスクの開示について教えてください" | `answer_text` with TCFD physical-risk citation | PASS |
| BL-02 | IAIS supervision question triggers insurance overlay | "IAIS の保険監督上の期待について教えてください" | `answer_text` includes IAIS Application Paper citation | PASS |
| BL-03 | Portfolio-specific quantification request | "自社ポートフォリオのリスク量を算出してください" | `answer_text` == the scope-advisory disclaimer (non-suppressible) | PASS |
| BL-04 | Empty query | "" | `status` in (error, cancelled) | PASS |

## Test Execution Summary
- Execution date: 2026-07-12
- Total tests: 5 node unit test classes (18 cases) + 4 integration cases + PB-4/PB-5/PB-6/PB-7 + 09_process_metrics
- Pass: all local-runnable cases / Fail: 0 / Skip: PB-7 (by design, HITL not enabled)
- Coverage: all BL paths (unit + integration); hard % threshold enforced by CI gate
- Note: PB-6 requires the CI wheel `agenticstar-agentcore==1.0.0` (`emit_trace_event` on
  `framework.nodes.base_node`) — local environments on an older stub mirror skip PB-6 by
  design; this is an expected local adaptation, not a test failure. CI is the gate of record.
