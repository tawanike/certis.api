"""Node functions for the claim mirroring pipeline.

Each node is an async function that receives ``ClaimsAgentState`` and returns
a partial state dict.  LLM-backed nodes use ``with_structured_output`` for
reliable JSON parsing.
"""

import json
import logging
from typing import Dict, Any, List

from langchain_core.prompts import ChatPromptTemplate

from src.llm.factory import get_primary_llm
from src.drafting.schemas import ClaimNode, ClaimGraph
from src.agents.claims.schemas import (
    CanonicalClaimModel,
    PartialClaimSet,
    ScopeValidationResult,
)
from src.agents.claims.prompts import (
    CCM_SYSTEM_PROMPT,
    CCM_USER_PROMPT,
    SYSTEM_CLAIM_SYSTEM_PROMPT,
    SYSTEM_CLAIM_USER_PROMPT,
    METHOD_MIRROR_SYSTEM_PROMPT,
    METHOD_MIRROR_USER_PROMPT,
    MEDIUM_MIRROR_SYSTEM_PROMPT,
    MEDIUM_MIRROR_USER_PROMPT,
    SCOPE_VALIDATOR_SYSTEM_PROMPT,
    SCOPE_VALIDATOR_USER_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing helper
# ---------------------------------------------------------------------------

def check_errors(state: Dict[str, Any]) -> str:
    """Return ``'end'`` if errors exist, ``'continue'`` otherwise."""
    if state.get("errors"):
        return "end"
    return "continue"


# ---------------------------------------------------------------------------
# Stage 1 — Extract Canonical Claim Model
# ---------------------------------------------------------------------------

async def canonical_claim_node(state: Dict[str, Any]) -> Dict[str, Any]:
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(CanonicalClaimModel)

    prompt = ChatPromptTemplate.from_messages([
        ("system", CCM_SYSTEM_PROMPT),
        ("user", CCM_USER_PROMPT),
    ])

    chain = prompt | structured_llm

    try:
        result: CanonicalClaimModel = await chain.ainvoke({
            "brief_text": state["brief_text"],
            "document_context": state.get("document_context", ""),
        })
        return {
            "canonical_model": result.model_dump(),
            "errors": [],
        }
    except Exception as e:
        logger.error("CCM extraction failed: %s", e)
        return {"errors": [f"CCM extraction failed: {e}"]}


# ---------------------------------------------------------------------------
# Stage 2 — Generate system claims
# ---------------------------------------------------------------------------

async def system_claim_node(state: Dict[str, Any]) -> Dict[str, Any]:
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(PartialClaimSet)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_CLAIM_SYSTEM_PROMPT),
        ("user", SYSTEM_CLAIM_USER_PROMPT),
    ])

    chain = prompt | structured_llm

    try:
        result: PartialClaimSet = await chain.ainvoke({
            "canonical_model": json.dumps(state["canonical_model"], indent=2),
            "brief_text": state["brief_text"],
        })
        nodes_dicts = [n.model_dump() for n in result.nodes]
        return {
            "system_claim_nodes": nodes_dicts,
            "errors": [],
        }
    except Exception as e:
        logger.error("System claim generation failed: %s", e)
        return {"errors": [f"System claim generation failed: {e}"]}


# ---------------------------------------------------------------------------
# Stage 3a — Mirror method claims
# ---------------------------------------------------------------------------

async def method_claim_mirror_node(state: Dict[str, Any]) -> Dict[str, Any]:
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(PartialClaimSet)

    prompt = ChatPromptTemplate.from_messages([
        ("system", METHOD_MIRROR_SYSTEM_PROMPT),
        ("user", METHOD_MIRROR_USER_PROMPT),
    ])

    chain = prompt | structured_llm

    try:
        result: PartialClaimSet = await chain.ainvoke({
            "canonical_model": json.dumps(state["canonical_model"], indent=2),
            "system_claims": json.dumps(state["system_claim_nodes"], indent=2),
        })
        nodes_dicts = [n.model_dump() for n in result.nodes]
        return {
            "method_claim_nodes": nodes_dicts,
            "errors": [],
        }
    except Exception as e:
        logger.error("Method mirror failed: %s", e)
        return {"errors": [f"Method mirror failed: {e}"]}


# ---------------------------------------------------------------------------
# Stage 3b — Mirror CRM claims
# ---------------------------------------------------------------------------

async def medium_claim_mirror_node(state: Dict[str, Any]) -> Dict[str, Any]:
    # Fast-exit when the invention is not software-based
    ccm = state.get("canonical_model", {})
    if not ccm.get("is_software_based", False):
        return {
            "medium_claim_nodes": [],
            "errors": [],
        }

    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(PartialClaimSet)

    prompt = ChatPromptTemplate.from_messages([
        ("system", MEDIUM_MIRROR_SYSTEM_PROMPT),
        ("user", MEDIUM_MIRROR_USER_PROMPT),
    ])

    chain = prompt | structured_llm

    try:
        result: PartialClaimSet = await chain.ainvoke({
            "canonical_model": json.dumps(state["canonical_model"], indent=2),
            "system_claims": json.dumps(state["system_claim_nodes"], indent=2),
        })
        nodes_dicts = [n.model_dump() for n in result.nodes]
        return {
            "medium_claim_nodes": nodes_dicts,
            "errors": [],
        }
    except Exception as e:
        logger.error("CRM mirror failed: %s", e)
        return {"errors": [f"CRM mirror failed: {e}"]}


# ---------------------------------------------------------------------------
# Stage 4 — Assemble and renumber all claims (pure logic, no LLM)
# ---------------------------------------------------------------------------

async def assemble_claims_node(state: Dict[str, Any]) -> Dict[str, Any]:
    system_nodes: List[Dict[str, Any]] = state.get("system_claim_nodes") or []
    method_nodes: List[Dict[str, Any]] = state.get("method_claim_nodes") or []
    medium_nodes: List[Dict[str, Any]] = state.get("medium_claim_nodes") or []

    all_nodes = system_nodes + method_nodes + medium_nodes

    if not all_nodes:
        return {"errors": ["No claims were generated across any category"]}

    # Build old-id → new-id mapping (sequential 1-based)
    id_map: Dict[str, str] = {}
    for idx, node in enumerate(all_nodes, start=1):
        id_map[node["id"]] = str(idx)

    # Renumber
    renumbered: List[Dict[str, Any]] = []
    for node in all_nodes:
        new_node = dict(node)
        new_node["id"] = id_map[node["id"]]
        new_node["dependencies"] = [
            id_map[dep] for dep in node.get("dependencies", []) if dep in id_map
        ]
        if node.get("mirror_source") and node["mirror_source"] in id_map:
            new_node["mirror_source"] = id_map[node["mirror_source"]]
        renumbered.append(new_node)

    # Collect independent nodes for scope validation
    independents = [n for n in renumbered if n.get("type") == "independent"]

    # Build ClaimGraph
    claim_nodes = [ClaimNode(**n) for n in renumbered]
    claim_graph = ClaimGraph(
        nodes=claim_nodes,
        risk_score=None,
        canonical_model=state.get("canonical_model"),
    )

    return {
        "claim_graph": claim_graph,
        "all_independent_nodes": independents,
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Stage 5 — Scope consistency validation
# ---------------------------------------------------------------------------

async def scope_consistency_node(state: Dict[str, Any]) -> Dict[str, Any]:
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(ScopeValidationResult)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SCOPE_VALIDATOR_SYSTEM_PROMPT),
        ("user", SCOPE_VALIDATOR_USER_PROMPT),
    ])

    chain = prompt | structured_llm

    try:
        result: ScopeValidationResult = await chain.ainvoke({
            "canonical_model": json.dumps(state["canonical_model"], indent=2),
            "independent_claims": json.dumps(
                state.get("all_independent_nodes", []), indent=2
            ),
        })

        validation_dict = result.model_dump()

        # Update the claim graph with validation results
        claim_graph: ClaimGraph = state["claim_graph"]
        claim_graph.scope_validation = validation_dict

        return {
            "claim_graph": claim_graph,
            "scope_validation": validation_dict,
            "errors": [],
        }
    except Exception as e:
        logger.error("Scope validation failed: %s", e)
        return {"errors": [f"Scope validation failed: {e}"]}
