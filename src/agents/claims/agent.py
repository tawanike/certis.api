"""Claims Architect — multi-stage mirroring pipeline.

Graph topology::

    START → extract_ccm → generate_system_claims → fan_out_mirrors
                                                    ├─→ mirror_method ──┐
                                                    └─→ mirror_medium ──┤
                                                                        ▼
                                                      assemble_claims → validate_scope → END
"""

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from src.agents.state import ClaimsAgentState
from src.agents.claims.nodes import (
    canonical_claim_node,
    system_claim_node,
    method_claim_mirror_node,
    medium_claim_mirror_node,
    assemble_claims_node,
    scope_consistency_node,
    check_errors,
)


def _fan_out_mirrors(state):
    """Route from generate_system_claims to both mirror nodes in parallel, or END on error."""
    if state.get("errors"):
        return END
    return [
        Send("mirror_method", state),
        Send("mirror_medium", state),
    ]


def _check_after_ccm(state):
    return END if state.get("errors") else "generate_system_claims"


def _check_after_assemble(state):
    return END if state.get("errors") else "validate_scope"


def create_claims_agent():
    workflow = StateGraph(ClaimsAgentState)

    # Nodes
    workflow.add_node("extract_ccm", canonical_claim_node)
    workflow.add_node("generate_system_claims", system_claim_node)
    workflow.add_node("mirror_method", method_claim_mirror_node)
    workflow.add_node("mirror_medium", medium_claim_mirror_node)
    workflow.add_node("assemble_claims", assemble_claims_node)
    workflow.add_node("validate_scope", scope_consistency_node)

    # Edges
    workflow.set_entry_point("extract_ccm")
    workflow.add_conditional_edges("extract_ccm", _check_after_ccm, {
        "generate_system_claims": "generate_system_claims",
        END: END,
    })
    workflow.add_conditional_edges(
        "generate_system_claims",
        _fan_out_mirrors,
        ["mirror_method", "mirror_medium"],
    )
    workflow.add_edge("mirror_method", "assemble_claims")
    workflow.add_edge("mirror_medium", "assemble_claims")
    workflow.add_conditional_edges("assemble_claims", _check_after_assemble, {
        "validate_scope": "validate_scope",
        END: END,
    })
    workflow.add_edge("validate_scope", END)

    return workflow.compile()


# Singleton instance accessor
claims_agent = create_claims_agent()
