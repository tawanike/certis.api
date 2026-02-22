from typing import TypedDict, Optional, List, Any

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from src.llm.factory import get_primary_llm
from src.risk.schemas import RiskAnalysis
from src.agents.risk.re_evaluation_prompts import (
    RISK_RE_EVALUATION_SYSTEM_PROMPT,
    RISK_RE_EVALUATION_USER_PROMPT,
)


class ReEvalAgentState(TypedDict):
    claim_text: str
    spec_text: str
    previous_risk_findings: str
    document_context: str
    risk_analysis: Optional[RiskAnalysis]
    messages: List[Any]
    errors: Optional[List[str]]


def create_re_evaluation_agent():
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(RiskAnalysis)

    async def re_evaluate_risk_node(state: ReEvalAgentState):
        claim_text = state["claim_text"]
        spec_text = state["spec_text"]
        previous_risk_findings = state["previous_risk_findings"]

        prompt = ChatPromptTemplate.from_messages([
            ("system", RISK_RE_EVALUATION_SYSTEM_PROMPT),
            ("user", RISK_RE_EVALUATION_USER_PROMPT),
        ])

        chain = prompt | structured_llm

        try:
            result: RiskAnalysis = await chain.ainvoke({
                "claim_text": claim_text,
                "spec_text": spec_text,
                "previous_risk_findings": previous_risk_findings,
                "document_context": state.get("document_context", ""),
            })
            return {"risk_analysis": result, "errors": []}
        except Exception as e:
            return {"errors": [str(e)]}

    workflow = StateGraph(ReEvalAgentState)
    workflow.add_node("re_evaluate_risk", re_evaluate_risk_node)
    workflow.set_entry_point("re_evaluate_risk")
    workflow.add_edge("re_evaluate_risk", END)

    return workflow.compile()


# Singleton instance accessor
risk_re_evaluation_agent = create_re_evaluation_agent()
