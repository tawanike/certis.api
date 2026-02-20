from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from src.llm.factory import get_primary_llm
from src.drafting.schemas import ClaimGraph
from src.agents.state import AgentState
from src.agents.claims.prompts import CLAIMS_ARCHITECT_SYSTEM_PROMPT, CLAIMS_GENERATION_USER_PROMPT

def create_claims_agent():
    # 1. Initialize LLM with Strict Structure
    llm = get_primary_llm()
    structured_llm = llm.with_structured_output(ClaimGraph)

    # 2. Define the Node Logic
    async def generate_claims_node(state: AgentState):
        brief = state["brief_text"]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", CLAIMS_ARCHITECT_SYSTEM_PROMPT),
            ("user", CLAIMS_GENERATION_USER_PROMPT)
        ])
        
        chain = prompt | structured_llm
        
        try:
            result: ClaimGraph = await chain.ainvoke({"brief_text": brief})
            return {"claim_graph": result, "errors": []}
        except Exception as e:
            return {"errors": [str(e)]}

    # 3. Build the Graph
    workflow = StateGraph(AgentState)
    workflow.add_node("generate_claims", generate_claims_node)
    workflow.set_entry_point("generate_claims")
    workflow.add_edge("generate_claims", END)

    return workflow.compile()

# Singleton instance accessor
claims_agent = create_claims_agent()
