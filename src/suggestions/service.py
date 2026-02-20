import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.briefs.models import BriefVersion
from src.artifacts.claims.models import ClaimGraphVersion
from src.chat.service import CHAT_HISTORY
from src.documents.models import Document
from src.llm.factory import get_suggestions_llm
from src.matter.models import Matter
from src.suggestions.schemas import Suggestion

logger = logging.getLogger(__name__)

VALID_ACTION_IDS = {"approve_brief", "generate_claims", "commit_claims"}


class SuggestionsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_suggestions(self, matter_id: UUID) -> List[Suggestion]:
        context = await self._build_context(matter_id)
        if context is None:
            return []

        try:
            llm = get_suggestions_llm()
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(context)

            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])

            suggestions = self._parse_suggestions(response.content, context)
        except Exception:
            logger.exception("LLM suggestion generation failed, using fallback")
            suggestions = self._fallback_suggestions(context)

        # Filter out workflow actions whose preconditions aren't met
        return [s for s in suggestions if self._validate_action(s, context)]

    async def _build_context(self, matter_id: UUID) -> Optional[Dict[str, Any]]:
        result = await self.db.execute(
            select(Matter).where(Matter.id == matter_id)
        )
        matter = result.scalar_one_or_none()
        if matter is None:
            return None

        # Latest brief version
        brief_result = await self.db.execute(
            select(BriefVersion)
            .where(BriefVersion.matter_id == matter_id)
            .order_by(desc(BriefVersion.version_number))
            .limit(1)
        )
        brief = brief_result.scalar_one_or_none()

        # Latest claim graph version
        claims_result = await self.db.execute(
            select(ClaimGraphVersion)
            .where(ClaimGraphVersion.matter_id == matter_id)
            .order_by(desc(ClaimGraphVersion.version_number))
            .limit(1)
        )
        claims = claims_result.scalar_one_or_none()

        # Document count
        doc_count_result = await self.db.execute(
            select(func.count()).select_from(Document).where(
                Document.matter_id == matter_id
            )
        )
        doc_count = doc_count_result.scalar() or 0

        # Recent chat history
        chat_history = CHAT_HISTORY.get(matter_id, [])
        recent_messages = chat_history[-5:] if chat_history else []

        # Extract brief summary
        brief_summary = None
        if brief and brief.structure_data:
            sd = brief.structure_data
            brief_summary = {
                "core_invention": sd.get("core_invention_statement", ""),
                "component_count": len(sd.get("components", [])),
                "ambiguities": sd.get("ambiguities_or_missing_elements", []),
                "is_authoritative": brief.is_authoritative,
            }

        # Extract claims summary
        claims_summary = None
        if claims and claims.graph_data:
            gd = claims.graph_data
            nodes = gd.get("nodes", [])
            categories = list({n.get("category", "unknown") for n in nodes})
            claims_summary = {
                "node_count": len(nodes),
                "categories": categories,
                "is_authoritative": claims.is_authoritative,
            }

        return {
            "matter_id": str(matter_id),
            "title": matter.title,
            "tech_domain": matter.tech_domain,
            "status": matter.status.value if hasattr(matter.status, "value") else str(matter.status),
            "doc_count": doc_count,
            "brief": brief_summary,
            "claims": claims_summary,
            "recent_chat": [
                {"role": m.role, "content": m.content[:200]}
                for m in recent_messages
            ],
        }

    def _build_system_prompt(self) -> str:
        return """You are a patent drafting assistant. Generate 4-6 contextual suggestions for the attorney based on the current matter state.

Return a JSON object with a single key "suggestions" containing an array. Each suggestion has:
- "label": short display text (max 50 chars)
- "type": either "chat_prompt" or "workflow_action"
- "action_id": required if type is "workflow_action". Valid values: "approve_brief", "generate_claims", "commit_claims"
- "prompt": required if type is "chat_prompt". The text to prefill in the chat input.

Rules:
- Include at most 2 workflow_action suggestions
- Chat prompts should be specific to the invention described, not generic
- Only suggest "approve_brief" if there is an unapproved brief
- Only suggest "generate_claims" if the brief is approved but no claims exist yet
- Only suggest "commit_claims" if there are uncommitted claims
- Make chat prompts actionable and relevant to the current drafting stage
- Keep labels concise and professional"""

    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        parts = [f"Matter: {context['title']}"]

        if context.get("tech_domain"):
            parts.append(f"Tech Domain: {context['tech_domain']}")

        parts.append(f"Status: {context['status']}")
        parts.append(f"Documents uploaded: {context['doc_count']}")

        if context.get("brief"):
            b = context["brief"]
            parts.append(f"\nBrief: {'Approved' if b['is_authoritative'] else 'Pending approval'}")
            if b.get("core_invention"):
                parts.append(f"Core invention: {b['core_invention'][:300]}")
            parts.append(f"Components: {b['component_count']}")
            if b.get("ambiguities"):
                parts.append(f"Flagged issues: {', '.join(b['ambiguities'][:3])}")
        else:
            parts.append("\nNo brief uploaded yet.")

        if context.get("claims"):
            c = context["claims"]
            parts.append(f"\nClaims: {c['node_count']} nodes, categories: {', '.join(c['categories'])}")
            parts.append(f"Committed: {'Yes' if c['is_authoritative'] else 'No'}")
        else:
            parts.append("\nNo claims generated yet.")

        if context.get("recent_chat"):
            topics = [m["content"][:80] for m in context["recent_chat"] if m["role"] == "user"]
            if topics:
                parts.append(f"\nRecent chat topics: {'; '.join(topics[:3])}")

        return "\n".join(parts)

    def _parse_suggestions(
        self, content: Any, context: Dict[str, Any]
    ) -> List[Suggestion]:
        try:
            text = content if isinstance(content, str) else str(content)
            data = json.loads(text)

            raw_suggestions = data.get("suggestions", [])
            if not isinstance(raw_suggestions, list):
                return self._fallback_suggestions(context)

            suggestions = []
            for item in raw_suggestions[:6]:
                try:
                    s = Suggestion(
                        label=item["label"],
                        type=item["type"],
                        action_id=item.get("action_id"),
                        prompt=item.get("prompt"),
                    )
                    # Validate action_id if workflow_action
                    if s.type == "workflow_action" and s.action_id not in VALID_ACTION_IDS:
                        continue
                    # Ensure chat_prompt has a prompt
                    if s.type == "chat_prompt" and not s.prompt:
                        s.prompt = s.label
                    suggestions.append(s)
                except (KeyError, ValueError):
                    continue

            return suggestions if suggestions else self._fallback_suggestions(context)

        except (json.JSONDecodeError, TypeError):
            return self._fallback_suggestions(context)

    def _validate_action(
        self, suggestion: Suggestion, context: Dict[str, Any]
    ) -> bool:
        if suggestion.type != "workflow_action":
            return True

        status = context["status"]
        brief = context.get("brief")
        claims = context.get("claims")

        if suggestion.action_id == "approve_brief":
            return brief is not None and not brief["is_authoritative"]

        if suggestion.action_id == "generate_claims":
            return (
                brief is not None
                and brief["is_authoritative"]
                and status in ("BRIEF_ANALYZED", "CLAIMS_PROPOSED")
            )

        if suggestion.action_id == "commit_claims":
            return claims is not None and not claims["is_authoritative"]

        return False

    def _fallback_suggestions(self, context: Dict[str, Any]) -> List[Suggestion]:
        status = context["status"]
        brief = context.get("brief")
        claims = context.get("claims")
        suggestions: List[Suggestion] = []

        if brief is None:
            suggestions.extend([
                Suggestion(
                    label="Summarize the invention disclosure",
                    type="chat_prompt",
                    prompt="Summarize the invention disclosure",
                ),
                Suggestion(
                    label="What documents should I upload?",
                    type="chat_prompt",
                    prompt="What documents should I upload for this patent matter?",
                ),
                Suggestion(
                    label="Identify key novel features",
                    type="chat_prompt",
                    prompt="Identify key novel features of this invention",
                ),
            ])
        elif not brief["is_authoritative"]:
            suggestions.append(
                Suggestion(
                    label="Approve brief",
                    type="workflow_action",
                    action_id="approve_brief",
                )
            )
            suggestions.extend([
                Suggestion(
                    label="Review brief structure",
                    type="chat_prompt",
                    prompt="Review the structured invention breakdown and flag any issues",
                ),
                Suggestion(
                    label="Identify missing elements",
                    type="chat_prompt",
                    prompt="What elements are missing from the invention brief?",
                ),
            ])
        elif claims is None or status == "BRIEF_ANALYZED":
            suggestions.append(
                Suggestion(
                    label="Generate claims",
                    type="workflow_action",
                    action_id="generate_claims",
                )
            )
            suggestions.extend([
                Suggestion(
                    label="Draft a problem-solution statement",
                    type="chat_prompt",
                    prompt="Draft a problem-solution statement based on the brief",
                ),
                Suggestion(
                    label="Suggest claim categories",
                    type="chat_prompt",
                    prompt="What claim categories (method, system, apparatus) should we target?",
                ),
            ])
        elif claims and not claims["is_authoritative"]:
            suggestions.append(
                Suggestion(
                    label="Commit claims",
                    type="workflow_action",
                    action_id="commit_claims",
                )
            )
            suggestions.extend([
                Suggestion(
                    label="Check antecedent basis",
                    type="chat_prompt",
                    prompt="Check for antecedent basis issues in the current claims",
                ),
                Suggestion(
                    label="Suggest dependent claims",
                    type="chat_prompt",
                    prompt="Suggest additional dependent claims to strengthen the claim tree",
                ),
            ])
        else:
            suggestions.extend([
                Suggestion(
                    label="Analyze litigation risks",
                    type="chat_prompt",
                    prompt="Analyze potential litigation risks in the current claims",
                ),
                Suggestion(
                    label="Review claim breadth",
                    type="chat_prompt",
                    prompt="Review the breadth of independent claims and suggest improvements",
                ),
                Suggestion(
                    label="Check prior art exposure",
                    type="chat_prompt",
                    prompt="Identify areas of potential prior art exposure",
                ),
            ])

        return suggestions
