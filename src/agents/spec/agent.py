from typing import TypedDict, Optional, List, Any

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from src.llm.factory import get_primary_llm
from src.specs.schemas import SpecDocument
from src.agents.spec.prompts import SPEC_DRAFTER_SYSTEM_PROMPT, SPEC_DRAFTING_USER_PROMPT


class SpecAgentState(TypedDict):
    brief_text: str
    claim_text: str
    risk_findings: str
    document_context: str
    spec_document: Optional[SpecDocument]
    messages: List[Any]
    errors: Optional[List[str]]


def create_spec_agent():
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(SpecDocument)

    async def generate_spec_node(state: SpecAgentState):
        brief_text = state["brief_text"]
        claim_text = state["claim_text"]
        risk_findings = state["risk_findings"]

        prompt = ChatPromptTemplate.from_messages([
            ("system", SPEC_DRAFTER_SYSTEM_PROMPT),
            ("user", SPEC_DRAFTING_USER_PROMPT),
        ])

        chain = prompt | structured_llm

        try:
            result: SpecDocument = await chain.ainvoke({
                "brief_text": brief_text,
                "claim_text": claim_text,
                "risk_findings": risk_findings,
                "document_context": state.get("document_context", ""),
            })
            return {"spec_document": result, "errors": []}
        except Exception as e:
            return {"errors": [str(e)]}

    workflow = StateGraph(SpecAgentState)
    workflow.add_node("generate_spec", generate_spec_node)
    workflow.set_entry_point("generate_spec")
    workflow.add_edge("generate_spec", END)

    return workflow.compile()


# Singleton instance accessor
spec_agent = create_spec_agent()
