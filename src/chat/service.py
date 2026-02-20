import json
import logging
import re
from typing import Dict, List, Any, Optional
from uuid import UUID
from collections import defaultdict
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.config import settings
from src.chat.schemas import ChatMessage
from src.llm.factory import get_chat_llm
from src.documents.service import DocumentService

logger = logging.getLogger(__name__)

# In-memory storage for chat history
# Format: {matter_id: [ChatMessage, ...]}
CHAT_HISTORY: Dict[UUID, List[ChatMessage]] = defaultdict(list)

# Max history messages to send to LLM (prevents context overflow)
MAX_HISTORY_MESSAGES = 20

# Regex to strip DeepSeek R1 thinking tokens
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks from DeepSeek R1 output."""
    return THINK_RE.sub("", text).strip()


class ChatService:
    def __init__(self, db=None):
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

    async def _retrieve_context(self, matter_id: UUID, user_message: str):
        """Retrieve relevant document chunks for RAG context."""
        context_text = ""
        references = []
        if not self.db:
            return context_text, references

        doc_service = DocumentService(self.db)
        page_filter = self._extract_page_number(user_message)
        chunks = await doc_service.search_chunks(
            matter_id, user_message, top_k=8, page_filter=page_filter
        )
        if chunks:
            context_parts = []
            page_chunk_counter: Dict[str, int] = defaultdict(int)
            for chunk in chunks:
                context_parts.append(
                    f"[{chunk['filename']}, Page {chunk['page_number']}]: {chunk['content']}"
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
        return context_text, references

    def _build_messages(
        self, matter_id: UUID, user_message: str, context_text: str
    ) -> List:
        """Build LangChain message list with system prompt, context, and trimmed history."""
        system_content = self.system_prompt
        if context_text:
            system_content += (
                "\n\n## Relevant Document Context\n"
                "The following excerpts were retrieved from the matter's uploaded documents. "
                "Use this context to inform your response:\n\n"
                f"{context_text}"
            )

        messages = [SystemMessage(content=system_content)]

        # Trim history to last N messages to prevent context overflow
        history = list(CHAT_HISTORY[matter_id])
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]

        # Exclude the current user message (last in history) — we add it explicitly
        for msg in history[:-1]:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
        messages.append(HumanMessage(content=user_message))
        return messages

    async def chat(self, matter_id: UUID, user_message: str) -> Dict[str, Any]:
        # 1. Update History with User Message
        CHAT_HISTORY[matter_id].append(ChatMessage(role="user", content=user_message))

        # 2. Retrieve relevant document context (RAG)
        try:
            context_text, references = await self._retrieve_context(matter_id, user_message)
        except Exception as e:
            logger.error(f"RAG retrieval failed for matter {matter_id}: {e}", exc_info=True)
            context_text, references = "", []

        # 3. Build messages
        messages = self._build_messages(matter_id, user_message, context_text)

        # 4. Call LLM
        response = await self.llm.ainvoke(messages)
        ai_content = _strip_thinking(str(response.content))

        # 5. Update History with AI Response
        ai_message = ChatMessage(
            role="assistant", content=ai_content,
            references=references if references else None,
        )
        CHAT_HISTORY[matter_id].append(ai_message)

        return {
            "response": ai_content,
            "history": CHAT_HISTORY[matter_id],
            "references": references if references else None,
        }

    async def get_history(self, matter_id: UUID) -> List[ChatMessage]:
        return CHAT_HISTORY[matter_id]

    async def stream_chat(self, matter_id: UUID, user_message: str):
        # 1. Update History with User Message
        CHAT_HISTORY[matter_id].append(ChatMessage(role="user", content=user_message))

        # 2. Retrieve relevant document context (RAG)
        try:
            context_text, references = await self._retrieve_context(matter_id, user_message)
        except Exception as e:
            logger.error(f"RAG retrieval failed for matter {matter_id}: {e}", exc_info=True)
            context_text, references = "", []
            yield {"event": "error", "data": json.dumps({"detail": "Document retrieval failed"})}

        if references:
            yield {"event": "references", "data": json.dumps(references)}

        # 3. Build messages
        messages = self._build_messages(matter_id, user_message, context_text)

        # 4. Stream LLM tokens — filter out <think> blocks
        full_response = ""
        in_thinking = False
        think_buffer = ""

        async for chunk in self.llm.astream(messages):
            if not chunk.content:
                continue
            token = str(chunk.content)

            # Handle <think>...</think> filtering for DeepSeek R1
            if in_thinking:
                think_buffer += token
                if "</think>" in think_buffer:
                    # End of thinking block — discard everything and resume
                    after = think_buffer.split("</think>", 1)[1]
                    in_thinking = False
                    think_buffer = ""
                    if after:
                        full_response += after
                        yield {"event": "message", "data": json.dumps({"content": after})}
                continue

            if "<think>" in token:
                # Start of thinking block
                before, _, remainder = token.partition("<think>")
                if before:
                    full_response += before
                    yield {"event": "message", "data": json.dumps({"content": before})}
                in_thinking = True
                think_buffer = remainder
                # Check if thinking ended in the same token
                if "</think>" in think_buffer:
                    after = think_buffer.split("</think>", 1)[1]
                    in_thinking = False
                    think_buffer = ""
                    if after:
                        full_response += after
                        yield {"event": "message", "data": json.dumps({"content": after})}
                continue

            full_response += token
            yield {"event": "message", "data": json.dumps({"content": token})}

        # 5. Update History
        ai_message = ChatMessage(
            role="assistant", content=full_response,
            references=references if references else None,
        )
        CHAT_HISTORY[matter_id].append(ai_message)

        yield {"event": "done", "data": json.dumps({"status": "completed"})}
