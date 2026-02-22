"""Internal Pydantic models for the claim mirroring pipeline.

These models are used within the pipeline only — they are never persisted
directly. The CanonicalClaimModel (CCM) is serialized to dict and stored
in ClaimGraph.canonical_model for audit purposes.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from src.drafting.schemas import ClaimNode


class Actor(BaseModel):
    id: str = Field(..., description="Unique actor identifier (e.g., 'a1')")
    name: str = Field(..., description="Short noun phrase (e.g., 'processor', 'sensor module')")
    actor_type: Literal[
        "processor", "controller", "transmitter", "receiver",
        "storage", "sensor", "interface", "module", "other",
    ] = Field(..., description="Functional role category")
    description: str = Field("", description="What this actor does in the invention")


class Action(BaseModel):
    id: str = Field(..., description="Unique action identifier (e.g., 'act1')")
    verb: str = Field(..., description="Gerund or infinitive (e.g., 'receiving', 'compute')")
    object: str = Field(..., description="What the action operates on")
    order: int = Field(..., description="Sequence position (1-based)")
    actor_id: str = Field(..., description="Actor performing this action")


class DataFlow(BaseModel):
    source_actor_id: str
    target_actor_id: str
    data_description: str = Field(..., description="What data moves between actors")


class CanonicalClaimModel(BaseModel):
    core_function: str = Field(..., description="One-sentence functional summary of the invention")
    actors: List[Actor] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)
    data_flows: List[DataFlow] = Field(default_factory=list)
    is_software_based: bool = Field(
        ..., description="True if the invention is primarily software/CRM-eligible"
    )
    technical_field: str = Field(..., description="Technical domain of the invention")


class ScopeValidationResult(BaseModel):
    scope_equivalent: bool = Field(
        ..., description="True only when missing_elements and extra_limitations are both empty"
    )
    missing_elements: List[str] = Field(
        default_factory=list,
        description="CCM actors/actions not present in any independent claim",
    )
    extra_limitations: List[str] = Field(
        default_factory=list,
        description="Claim limitations not traceable to the CCM",
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Explanatory notes for the attorney",
    )


class PartialClaimSet(BaseModel):
    """Structured output wrapper for a set of claims from a single generation step."""
    nodes: List[ClaimNode] = Field(
        default_factory=list, description="Generated claim nodes"
    )
