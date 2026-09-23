# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: TCFDClimateDisclosureAgent
- **L1 Base**: AgentBaseGraph (outer) — Cat 2 composition wraps an inner `BaseGraph` subgraph
- **Three-Layer Separation**:
  - State: flat TypedDict composition (`src/schemas/state.py`, `NotRequired[...]` on every agent-specific field)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition — outer `AgentBaseGraph` backbone + `GraphNode` (`main` slot) wrapping the
    inner `BaseGraph` (`TCFDDisclosureWorkflowGraph`)

## Architecture Overview

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | framework default | — | — | InitializeNode (default) |
| pre_process | `InputSanitizeNode` — validate query, preliminary category, non-suppressible scope-advisory gate | `user_input` | `validated_input`, `advice_blocked`, `query_category` | `FunctionNode` |
| main | `TCFDGraphNode` — dispatch inner subgraph (query_classify → tcfd_retrieve → insurance_sector_overlay) | `validated_input` | `answer_text`, `query_category`, `advice_blocked`, `methodology_citation`, `scenario_applicable`, `disclosure_format_guidance`, `kb_source_ref` | `GraphNode` |
| post_process | `OutputGateNode` — non-suppressible re-derivation of advice_blocked + citation enforcement | `answer_text`, `advice_blocked`, `methodology_citation` | `answer_text` (final) | `FunctionNode` |
| finalize | framework default | — | — | FinalizeNode (default) |

### Inner subgraph nodes (`TCFDDisclosureWorkflowGraph`)

| Inner node | Responsibility | LLM? |
|---|---|---|
| `query_classify` (`QueryClassifyNode`) | Classify into physical_risk / transition_risk / scenario_analysis / disclosure_format / insurance_sector_specific / iais_supervision; re-derives advice_blocked defensively | Yes (Azure OpenAI; deterministic fallback) |
| `tcfd_retrieve` (`TCFDRetrieveNode`) | Dense retrieval from `tcfd_fsa_climate` KB namespace | No |
| `insurance_sector_overlay` (`InsuranceSectorOverlayNode`) | Conditional retrieval from `iais_ins_climate` KB namespace + final answer composition | No |

**LLM wiring (`QueryClassifyNode`):** `AzureOpenAIClient` (`shared.services.llm.azure_openai_client`)
is built fresh inside `execute()` from `ctx.secrets.require(...)` — never at `__init__`/
`register_nodes()`, never cached on `self` (a node instance is reused across every invocation via
the registry's LRU cache; a cached client would leak one caller's secrets to the next). The
constructor's `llm=` parameter is a test-double seam only — production wiring never passes one.
Any failure to resolve secrets, build the client, call it, or get a response that is one of the
six valid categories degrades silently to `classify_query_category(query)` (the pre-existing
deterministic classifier) — never raises, never sets `status=error` for this reason alone. See
`docs/07_operation_guide.md` for the three secrets this requires.

### Data Flow

```
START → initialize → pre_process → main(GraphNode) → post_process → finalize → END
                                       │
                                       ▼ (inner subgraph)
                        query_classify → tcfd_retrieve → insurance_sector_overlay → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `query_category` | `NotRequired[str]` | Resolved TCFD/IAIS category | No |
| `advice_blocked` | `NotRequired[bool]` | Non-suppressible scope-advisory flag (portfolio-specific quantification request) | No |
| `needs_insurance_overlay` | `NotRequired[bool]` | Routes inner pipeline through IAIS overlay | No |
| `answer_text` | `NotRequired[str]` | Final composed answer or disclaimer | No |
| `scenario_applicable` | `NotRequired[str]` | JSON list of applicable IPCC AR6/NGFS scenarios | No |
| `disclosure_format_guidance` | `NotRequired[str]` | TCFD disclosure-format guidance text | No |
| `methodology_citation` | `NotRequired[str]` | TCFD version + FSA/IAIS guidance citation | No |
| `kb_source_ref` | `NotRequired[str]` | JSON list of KB provision identifiers used | No |
| `retrieved_tcfd_provisions` | `NotRequired[str]` | Internal handoff — raw TCFD provisions JSON (tcfd_retrieve → insurance_sector_overlay) | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [x] `ctx.secrets.require(...)` — `QueryClassifyNode` resolves `AZURE_OPENAI_API_KEY` /
      `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` per invocation (declared in
      `config/agent.yaml` `requires.secrets`); never `os.environ`, never cached across calls.
- [x] S-2: `_extra_security_gate_input()` — default framework PII scan is sufficient; the
      domain-specific scope-advisory check is implemented as business logic inside
      `InputSanitizeNode.execute()` / `QueryClassifyNode.execute()` (raise-free, ERROR-dict path),
      not as a gate hook.
- [x] S-3: `_extra_security_gate_output()` — implemented on `OutputGateNode`: non-suppressible
      re-check that the disclaimer is present when `advice_blocked`, else that the methodology
      citation is present (own-dict field re-check, per ADR-017 hook contract).
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside each `execute()`
      (`ins_tcfd_query_sanitized`, `ins_tcfd_query_classified`, `tcfd_provisions_retrieved`,
      `ins_sector_overlay_applied`, `output_gate_scope_advisory_blocked`/`output_gate_citation_verified`),
      plus `tcfd_disclosure_workflow_dispatched`/`_completed` inside the `GraphNode` hooks.

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` (`TCFDGraphNode`) → deliberate no-op passthrough (S-2/S-4/S-3 lifecycle is
>   delegated to the inner subgraph's own nodes)

### Composition Pattern

- **Pattern**: Cat 2 — outer `AgentBaseGraph` + `GraphNode` (`main` slot) wrapping inner `BaseGraph`
- **Composition target**: `TCFDDisclosureWorkflowGraph` (`src/graph/domain_workflow_graph.py`)
- **Error propagation strategy**: `propagate` (fail fast — inner `ERROR` status surfaces as the
  outer agent's `error` status via `GraphNode.error_strategy = "propagate"`)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Fixed pipeline (classify → retrieve → overlay → gate); no autonomous think-act loop needed |
| Composition pattern | Flat 3-slot (Cat 1 style) | GraphNode + inner subgraph (Cat 2) | GraphNode + inner subgraph | `gate-composition` requires Cat 2 to wrap multi-step domain logic in a `GraphNode`, not a flat MainNode |
| Scope-advisory gate placement | Inner node only | Outer post_process (non-suppressible, closest to final output) + inner defense-in-depth re-check | Both (defense-in-depth) | GraphNode boundary only forwards a JSON envelope — outer `OutputGateNode` re-derives `advice_blocked` from `state["user_input"]` directly so a dropped/overridden inner flag cannot suppress the disclaimer |
