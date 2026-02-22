from typing import TypedDict, List
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from src.llm import get_primary_llm

# --- 1. State Definition ---
class SBDState(TypedDict):
    text: str
    figure_analyses: List[dict]
    brief_data: dict | None
    errors: List[str]

# --- 2. Structured Output Schema (Matches BriefVersion) ---
# We define Pydantic models to guide the LLM's JSON output
class SystemComponent(BaseModel):
    component_id: str
    name: str
    description: str
    optional: bool

class MethodStep(BaseModel):
    step_id: str
    description: str
    order_required: bool

class DataElement(BaseModel):
    name: str
    description: str

class Variant(BaseModel):
    variant_id: str
    description: str
    affected_components: List[str]

class FigureDetected(BaseModel):
    figure_id: str
    type: str # e.g. "flowchart", "block_diagram"
    extracted_components: List[str]

class BriefStructure(BaseModel):
    core_invention_statement: str
    technical_field: str
    problem_statement: str
    technical_solution_summary: str
    system_components: List[SystemComponent]
    method_steps: List[MethodStep]
    data_elements: List[DataElement]
    variants: List[Variant]
    technical_effects: List[str]
    figures_detected: List[FigureDetected]
    ambiguities_or_missing_information: List[str]

# --- 3. Node Logic ---

def analyze_brief_node(state: SBDState):
    """
    Analyzes the raw text and extracts the structured brief.
    """
    print("--- SBD: Analyzing Brief ---")
    text = state["text"]
    
    # Initialize LLM with structured output
    llm = get_primary_llm()
    
    # Simple Prompt
    system_prompt = """You are an expert Patent Engineer. Your task is to perform a Structured Brief Decomposition (SBD) on the provided invention disclosure text.
    
    Analyze the text and extract the following structured information in strict JSON format:
    1. Core Invention Statement: A single sentence summarizing the "point of novelty".
    2. Technical Field: The specific technical domain.
    3. Problem Statement: The technical problem the invention solves.
    4. Technical Solution: How the invention solves the problem.
    5. System Components: Physical or logical parts. Assign a unique ID (e.g., COMP-01).
    6. Method Steps: Functional steps. Assign a unique ID (e.g., STEP-01).
    7. Data Elements: Primary data objects processed.
    8. Variants: Alternative embodiments described.
    9. Technical Effects: Positive outcomes (e.g., "reduced latency").
    10. Figures: Mentions of drawings or diagrams.
    11. Ambiguities: What is unclear or missing?
    
    Return ONLY VALID JSON matching this structure.
    """
    
    # Build the human message with text and any detected figures
    human_content = f"Invention Disclosure Text:\n{text}"

    figure_analyses = state.get("figure_analyses") or []
    if figure_analyses:
        figure_descriptions = []
        for fig in figure_analyses:
            components = ", ".join(fig.get("extracted_components", []))
            figure_descriptions.append(
                f"- Page {fig['page_number']} ({fig.get('figure_id', 'unknown')}): "
                f"{fig.get('type', 'diagram')} — {fig.get('description', 'No description')}. "
                f"Components: {components}"
            )
        human_content += (
            "\n\nDiagrams/Figures detected in the document:\n"
            + "\n".join(figure_descriptions)
            + "\n\nUse these diagram analyses to populate the figures_detected field accurately."
        )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_content)
    ]
    
    try:
        # We use .with_structured_output if supported, or just strict JSON mode + Pydantic validation
        # For Ollama JSON mode, it returns a string we need to parse, or we can use the experimental wrapper.
        # Let's try standard invoke with json format first using Pydantic to validate.
        
        structured_llm = llm.with_structured_output(BriefStructure)
        result = structured_llm.invoke(messages)
        
        # Result should be a BriefStructure object
        return {"brief_data": result.model_dump()}
        
    except Exception as e:
        print(f"SBD Error: {e}")
        return {"errors": [str(e)]}

# --- 4. Graph Construction ---

workflow = StateGraph(SBDState)

workflow.add_node("analyze_brief", analyze_brief_node)

workflow.set_entry_point("analyze_brief")
workflow.add_edge("analyze_brief", END)

sbd_agent = workflow.compile()
