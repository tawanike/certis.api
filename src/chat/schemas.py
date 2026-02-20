from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

class DocumentReference(BaseModel):
    filename: str
    page_number: int
    content: str
    
class ChatMessage(BaseModel):
    role: str # "user" or "assistant"
    content: str
    references: Optional[List[DocumentReference]] = None
    
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    history: List[ChatMessage]
    references: Optional[List[DocumentReference]] = None
