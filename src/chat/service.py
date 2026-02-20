import re
from typing import Dict, List, Any, Optional
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
            "You are Certis, a patent document analysis assistant. Your role is to answer "
            "questions STRICTLY based on the uploaded documents for this matter.\n\n"
            "Rules:\n"
            "- ONLY use information found in the provided document context below.\n"
            "- If the answer is not in the provided context, say \"I could not find that "
            "information in the uploaded documents.\"\n"
            "- NEVER fabricate, guess, or provide general knowledge not grounded in the documents.\n"
            "- Always cite the document filename and page number for every factual claim.\n"
            "- Quote relevant passages when appropriate.\n"
            "- If the user references a specific page, focus your answer on content from that page."
        )

    def _extract_page_number(self, message: str) -> Optional[int]:
        """Extract page number from user message if referenced."""
        match = re.search(r'page\s+(\d+)', message, re.IGNORECASE)
        return int(match.group(1)) if match else None

    async def chat(self, matter_id: UUID, user_message: str) -> Dict[str, Any]:
        # 1. Update History with User Message
        CHAT_HISTORY[matter_id].append(ChatMessage(role="user", content=user_message))

        # 2. Retrieve relevant document context (RAG)
        context_text = ""
        references = []
        if self.db:
            try:
                doc_service = DocumentService(self.db)
                page_filter = self._extract_page_number(user_message)
                chunks = await doc_service.search_chunks(matter_id, user_message, top_k=8, page_filter=page_filter)
                if chunks:
                    context_parts = []
                    page_chunk_counter: Dict[str, int] = defaultdict(int)
                    for chunk in chunks:
                        context_parts.append(
                            f"[Page {chunk['page_number']}]: {chunk['content']}"
                        )
                        page_key = f"{chunk.get('document_id', '')}:{chunk['page_number']}"
                        idx = page_chunk_counter[page_key]
                        page_chunk_counter[page_key] += 1
                        references.append({
                            "filename": chunk["filename"],
                            "page_number": chunk["page_number"],
                            "content": chunk["content"],
                            "document_id": str(chunk["document_id"]) if chunk.get("document_id") else None,
                            "chunk_index": idx,
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
                page_filter = self._extract_page_number(user_message)
                chunks = await doc_service.search_chunks(matter_id, user_message, top_k=8, page_filter=page_filter)
                if chunks:
                    context_parts = []
                    page_chunk_counter: Dict[str, int] = defaultdict(int)
                    for chunk in chunks:
                        context_parts.append(
                            f"[Page {chunk['page_number']}]: {chunk['content']}"
                        )
                        page_key = f"{chunk.get('document_id', '')}:{chunk['page_number']}"
                        idx = page_chunk_counter[page_key]
                        page_chunk_counter[page_key] += 1
                        references.append({
                            "filename": chunk["filename"],
                            "page_number": chunk["page_number"],
                            "content": chunk["content"],
                            "document_id": str(chunk["document_id"]) if chunk.get("document_id") else None,
                            "chunk_index": idx,
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
