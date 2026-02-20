from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Suggestion(BaseModel):
    label: str = Field(..., description="Display text for the suggestion pill")
    type: Literal["chat_prompt", "workflow_action"] = Field(
        ..., description="Whether this is a chat prefill or a triggerable action"
    )
    action_id: Optional[str] = Field(
        default=None,
        description="Action identifier for workflow_action type (e.g. approve_brief, generate_claims, commit_claims)",
    )
    prompt: Optional[str] = Field(
        default=None,
        description="Chat input text to prefill for chat_prompt type",
    )


class SuggestionsResponse(BaseModel):
    suggestions: List[Suggestion]
    matter_status: str
