import operator
from typing import TypedDict, Annotated, Optional, Dict, Any, List
from src.drafting.schemas import ClaimGraph


class AgentState(TypedDict):
    brief_text: str
    document_context: str
    claim_graph: Optional[ClaimGraph]
    messages: List[Any] # LangChain messages
    errors: Optional[List[str]]


class ClaimsAgentState(TypedDict):
    brief_text: str
    document_context: str
    claim_graph: Optional[ClaimGraph]
    messages: Annotated[List[Any], operator.add]
    errors: Annotated[List[str], operator.add]
    # Pipeline intermediates
    canonical_model: Optional[Dict[str, Any]]
    system_claim_nodes: Optional[List[Dict[str, Any]]]
    method_claim_nodes: Optional[List[Dict[str, Any]]]
    medium_claim_nodes: Optional[List[Dict[str, Any]]]
    all_independent_nodes: Optional[List[Dict[str, Any]]]
    scope_validation: Optional[Dict[str, Any]]
