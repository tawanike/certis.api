from typing import List
from langchain_core.messages import HumanMessage

from src.llm.factory import get_vision_llm

FIGURE_ANALYSIS_PROMPT = """Analyze this page from a patent inventor brief document.

1. Does this page contain a diagram, figure, flowchart, block diagram, schematic, or other technical drawing? If it is only text with no visual diagram, respond with: {"has_figure": false}

2. If it contains a figure, respond with JSON:
{
  "has_figure": true,
  "type": "<flowchart|block_diagram|schematic|circuit_diagram|data_flow|architecture|sequence_diagram|other>",
  "description": "<1-2 sentence description of what the figure shows>",
  "extracted_components": ["<component1>", "<component2>", ...]
}

Respond ONLY with valid JSON, no other text."""


async def analyze_figures(images: list[dict]) -> list[dict]:
    """
    Analyze extracted page images using the vision LLM to identify and
    describe diagrams/figures.

    Args:
        images: List of dicts with keys "page_number", "image_bytes", "image_base64".

    Returns:
        List of dicts with keys: page_number, figure_id, type, description,
        extracted_components. Only includes pages where a figure was detected.
    """
    if not images:
        return []

    llm = get_vision_llm()
    results = []
    figure_count = 0

    for img in images:
        message = HumanMessage(
            content=[
                {"type": "text", "text": FIGURE_ANALYSIS_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img['image_base64']}",
                    },
                },
            ]
        )

        try:
            response = await llm.ainvoke([message])
            # Parse JSON from the response
            import json
            content = response.content.strip()
            # Handle markdown code fences if the LLM wraps its output
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(content)

            if data.get("has_figure"):
                figure_count += 1
                results.append({
                    "page_number": img["page_number"],
                    "figure_id": f"FIG-{figure_count:02d}",
                    "type": data.get("type", "other"),
                    "description": data.get("description", ""),
                    "extracted_components": data.get("extracted_components", []),
                })
        except Exception as e:
            # Skip pages where vision analysis fails — don't block the pipeline
            print(f"Vision analysis failed for page {img['page_number']}: {e}")
            continue

    return results
