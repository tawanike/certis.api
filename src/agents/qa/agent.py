from typing import TypedDict, Optional, List, Any

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from src.llm.factory import get_primary_llm
from src.qa.schemas import QAReport
from src.agents.qa.prompts import QA_ANALYST_SYSTEM_PROMPT, QA_VALIDATION_USER_PROMPT


class QAAgentState(TypedDict):
    claim_text: str
    spec_text: str
    brief_text: str
    document_context: str
    qa_report: Optional[QAReport]
    messages: List[Any]
    errors: Optional[List[str]]


def create_qa_agent():
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(QAReport)

    async def validate_qa_node(state: QAAgentState):
        claim_text = state["claim_text"]
        spec_text = state["spec_text"]
        brief_text = state["brief_text"]

        prompt = ChatPromptTemplate.from_messages([
            ("system", QA_ANALYST_SYSTEM_PROMPT),
            ("user", QA_VALIDATION_USER_PROMPT),
        ])

        chain = prompt | structured_llm

        try:
            result: QAReport = await chain.ainvoke({
                "claim_text": claim_text,
                "spec_text": spec_text,
                "brief_text": brief_text,
                "document_context": state.get("document_context", ""),
            })
            return {"qa_report": result, "errors": []}
        except Exception as e:
            return {"errors": [str(e)]}

    workflow = StateGraph(QAAgentState)
    workflow.add_node("validate_qa", validate_qa_node)
    workflow.set_entry_point("validate_qa")
    workflow.add_edge("validate_qa", END)

    return workflow.compile()


# Singleton instance accessor
qa_agent = create_qa_agent()
