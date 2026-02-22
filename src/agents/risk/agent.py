from typing import TypedDict, Optional, List, Any

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from src.llm.factory import get_primary_llm
from src.risk.schemas import RiskAnalysis
from src.agents.risk.prompts import RISK_ANALYST_SYSTEM_PROMPT, RISK_ANALYSIS_USER_PROMPT


class RiskAgentState(TypedDict):
    claim_text: str
    risk_analysis: Optional[RiskAnalysis]
    messages: List[Any]
    errors: Optional[List[str]]


def create_risk_agent():
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(RiskAnalysis)

    async def analyze_risk_node(state: RiskAgentState):
        claim_text = state["claim_text"]

        prompt = ChatPromptTemplate.from_messages([
            ("system", RISK_ANALYST_SYSTEM_PROMPT),
            ("user", RISK_ANALYSIS_USER_PROMPT),
        ])

        chain = prompt | structured_llm

        try:
            result: RiskAnalysis = await chain.ainvoke({"claim_text": claim_text})
            return {"risk_analysis": result, "errors": []}
        except Exception as e:
            return {"errors": [str(e)]}

    workflow = StateGraph(RiskAgentState)
    workflow.add_node("analyze_risk", analyze_risk_node)
    workflow.set_entry_point("analyze_risk")
    workflow.add_edge("analyze_risk", END)

    return workflow.compile()


# Singleton instance accessor
risk_agent = create_risk_agent()
