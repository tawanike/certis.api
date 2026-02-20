from typing import Dict, List, Any
from uuid import UUID
from collections import defaultdict
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.config import settings
from src.chat.schemas import ChatMessage
from src.llm.factory import get_chat_llm
from src.documents.service import DocumentService

# In-memory storage for chat history
# Format: {matter_id: [ChatMessage, ...]}
CHAT_HISTORY: Dict[UUID, List[ChatMessage]] = defaultdict(list)


class ChatService:
    def __init__(self, db=None):
        # Use the centralized factory
        self.llm = get_chat_llm()
        self.db = db
        self.system_prompt = (
            "You are Certis, an AI patent drafting assistant. "
            "Help the user with their patent matter. "
            "When answering questions, use the provided document context to give accurate, specific answers. "
            "Always cite the page number when referencing document content."
        )

    async def chat(self, matter_id: UUID, user_message: str) -> Dict[str, Any]:
        # 1. Update History with User Message
        CHAT_HISTORY[matter_id].append(ChatMessage(role="user", content=user_message))

        # 2. Retrieve relevant document context (RAG)
        context_text = ""
        references = []
        if self.db:
            try:
                doc_service = DocumentService(self.db)
                chunks = await doc_service.search_chunks(matter_id, user_message, top_k=5)
                if chunks:
                    context_parts = []
                    for chunk in chunks:
                        context_parts.append(
                            f"[Page {chunk['page_number']}]: {chunk['content']}"
                        )
                        references.append({
                            "filename": chunk["filename"],
                            "page_number": chunk["page_number"],
                            "content": chunk["content"]
                        })
                    context_text = "\n\n---\n\n".join(context_parts)
            except Exception:
                # If retrieval fails, proceed without context
                pass

        # 3. Prepare LangChain Messages
        system_content = self.system_prompt
        if context_text:
            system_content += (
                "\n\n## Relevant Document Context\n"
                "The following excerpts were retrieved from the matter's uploaded documents. "
                "Use this context to inform your response:\n\n"
                f"{context_text}"
            )

        messages = [SystemMessage(content=system_content)]
        for msg in CHAT_HISTORY[matter_id]:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

        # 4. Call LLM
        response = await self.llm.ainvoke(messages)
        ai_content = response.content

        # 5. Update History with AI Response
        ai_message = ChatMessage(role="assistant", content=str(ai_content), references=references if references else None)
        CHAT_HISTORY[matter_id].append(ai_message)

        return {
            "response": str(ai_content),
            "history": CHAT_HISTORY[matter_id],
            "references": references if references else None,
        }

    async def get_history(self, matter_id: UUID) -> List[ChatMessage]:
        return CHAT_HISTORY[matter_id]

    async def stream_chat(self, matter_id: UUID, user_message: str):
        # 1. Update History with User Message
        CHAT_HISTORY[matter_id].append(ChatMessage(role="user", content=user_message))

        # 2. Retrieve relevant document context (RAG)
        context_text = ""
        references = []
        if self.db:
            try:
                doc_service = DocumentService(self.db)
                chunks = await doc_service.search_chunks(matter_id, user_message, top_k=5)
                if chunks:
                    context_parts = []
                    for chunk in chunks:
                        context_parts.append(
                            f"[Page {chunk['page_number']}]: {chunk['content']}"
                        )
                        references.append({
                            "filename": chunk["filename"],
                            "page_number": chunk["page_number"],
                            "content": chunk["content"]
                        })
                    context_text = "\n\n---\n\n".join(context_parts)
            except Exception:
                pass

        if references:
            import json
            yield {"event": "references", "data": json.dumps(references)}

        # 3. Prepare LangChain Messages
        system_content = self.system_prompt
        if context_text:
            system_content += (
                "\n\n## Relevant Document Context\n"
                "The following excerpts were retrieved from the matter's uploaded documents. "
                "Use this context to inform your response:\n\n"
                f"{context_text}"
            )

        messages = [SystemMessage(content=system_content)]
        for msg in list(CHAT_HISTORY[matter_id])[:-1]: # exclude the current user msg
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
        messages.append(HumanMessage(content=user_message))

        # 4. Stream LLM tokens
        full_response = ""
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                full_response += str(chunk.content)
                import json
                yield {"event": "message", "data": json.dumps({"content": str(chunk.content)})}

        # 5. Update History
        ai_message = ChatMessage(role="assistant", content=full_response, references=references if references else None)
        CHAT_HISTORY[matter_id].append(ai_message)

        import json
        yield {"event": "done", "data": json.dumps({"status": "completed"})}
