from typing import TypedDict, Optional, Dict, Any, List
from src.drafting.schemas import ClaimGraph

class AgentState(TypedDict):
    brief_text: str
    document_context: str
    claim_graph: Optional[ClaimGraph]
    messages: List[Any] # LangChain messages
    errors: Optional[List[str]]
