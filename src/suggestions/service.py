import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.briefs.models import BriefVersion
from src.artifacts.claims.models import ClaimGraphVersion
from src.artifacts.specs.models import SpecVersion
from src.chat.service import CHAT_HISTORY
from src.documents.models import Document
from src.llm.factory import get_suggestions_llm
from src.matter.models import Matter
from src.qa.models import QAReportVersion
from src.risk.models import RiskAnalysisVersion
from src.suggestions.schemas import Suggestion

logger = logging.getLogger(__name__)

VALID_ACTION_IDS = {
    "approve_brief",
    "generate_claims",
    "commit_claims",
    "run_risk",
    "commit_risk",
    "generate_spec",
    "commit_spec",
    "re_evaluate_risk",
    "commit_risk_reeval",
    "run_qa",
    "commit_qa",
    "lock_for_export",
}


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

        # Latest risk analysis version
        risk_result = await self.db.execute(
            select(RiskAnalysisVersion)
            .where(RiskAnalysisVersion.matter_id == matter_id)
            .order_by(desc(RiskAnalysisVersion.version_number))
            .limit(1)
        )
        risk = risk_result.scalar_one_or_none()

        # Latest spec version
        spec_result = await self.db.execute(
            select(SpecVersion)
            .where(SpecVersion.matter_id == matter_id)
            .order_by(desc(SpecVersion.version_number))
            .limit(1)
        )
        spec = spec_result.scalar_one_or_none()

        # Latest QA version
        qa_result = await self.db.execute(
            select(QAReportVersion)
            .where(QAReportVersion.matter_id == matter_id)
            .order_by(desc(QAReportVersion.version_number))
            .limit(1)
        )
        qa = qa_result.scalar_one_or_none()

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

        # Extract risk summary
        risk_summary = None
        if risk and risk.analysis_data:
            ad = risk.analysis_data
            risk_summary = {
                "defensibility_score": ad.get("defensibility_score"),
                "finding_count": len(ad.get("findings", [])),
                "is_authoritative": risk.is_authoritative,
                "has_spec_version": risk.spec_version_id is not None,
            }

        # Extract spec summary
        spec_summary = None
        if spec and spec.content_data:
            cd = spec.content_data
            spec_summary = {
                "has_background": bool(cd.get("background")),
                "has_detailed_description": bool(cd.get("detailed_description")),
                "has_abstract": bool(cd.get("abstract")),
                "is_authoritative": spec.is_authoritative,
            }

        # Extract QA summary
        qa_summary = None
        if qa and qa.report_data:
            rd = qa.report_data
            qa_summary = {
                "support_coverage_score": rd.get("support_coverage_score"),
                "total_errors": rd.get("total_errors", 0),
                "total_warnings": rd.get("total_warnings", 0),
                "can_export": rd.get("can_export", False),
                "is_authoritative": qa.is_authoritative,
            }

        return {
            "matter_id": str(matter_id),
            "title": matter.title,
            "tech_domain": matter.tech_domain,
            "status": matter.status.value if hasattr(matter.status, "value") else str(matter.status),
            "defensibility_score": matter.defensibility_score,
            "doc_count": doc_count,
            "brief": brief_summary,
            "claims": claims_summary,
            "risk": risk_summary,
            "spec": spec_summary,
            "qa": qa_summary,
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
- "action_id": required if type is "workflow_action". Valid values: "approve_brief", "generate_claims", "commit_claims", "run_risk", "commit_risk", "generate_spec", "commit_spec", "re_evaluate_risk", "commit_risk_reeval", "run_qa", "commit_qa", "lock_for_export"
- "prompt": required if type is "chat_prompt". The text to prefill in the chat input.

Rules:
- Include at most 2 workflow_action suggestions
- Chat prompts should be specific to the invention described, not generic
- Only suggest "approve_brief" if there is an unapproved brief
- Only suggest "generate_claims" if the brief is approved but no claims exist yet
- Only suggest "commit_claims" if there are uncommitted claims
- Only suggest "run_risk" if claims are committed
- Only suggest "commit_risk" if risk analysis exists and is uncommitted
- Only suggest "generate_spec" if risk is committed or claims are approved
- Only suggest "commit_spec" if spec exists and is uncommitted
- Only suggest "re_evaluate_risk" if spec is committed
- Only suggest "commit_risk_reeval" if re-evaluated risk exists and is uncommitted
- Only suggest "run_qa" if spec is committed
- Only suggest "commit_qa" if QA exists, is uncommitted, and can_export is true
- Only suggest "lock_for_export" if QA is committed and matter is QA_COMPLETE
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

        if context.get("risk"):
            r = context["risk"]
            parts.append(f"\nRisk: defensibility score {r['defensibility_score']}, {r['finding_count']} findings")
            parts.append(f"Committed: {'Yes' if r['is_authoritative'] else 'No'}")
            if r["has_spec_version"]:
                parts.append("(Re-evaluation post-spec)")
        else:
            parts.append("\nNo risk analysis yet.")

        if context.get("spec"):
            s = context["spec"]
            parts.append(f"\nSpec: background={'Yes' if s['has_background'] else 'No'}, detailed={'Yes' if s['has_detailed_description'] else 'No'}, abstract={'Yes' if s['has_abstract'] else 'No'}")
            parts.append(f"Committed: {'Yes' if s['is_authoritative'] else 'No'}")
        else:
            parts.append("\nNo specification generated yet.")

        if context.get("qa"):
            q = context["qa"]
            parts.append(f"\nQA: coverage {q['support_coverage_score']}%, {q['total_errors']} errors, {q['total_warnings']} warnings, can_export={'Yes' if q['can_export'] else 'No'}")
            parts.append(f"Committed: {'Yes' if q['is_authoritative'] else 'No'}")
        else:
            parts.append("\nNo QA validation yet.")

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
        risk = context.get("risk")
        spec = context.get("spec")
        qa = context.get("qa")

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

        if suggestion.action_id == "run_risk":
            return (
                claims is not None
                and claims["is_authoritative"]
                and status in ("CLAIMS_APPROVED", "RISK_REVIEWED")
            )

        if suggestion.action_id == "commit_risk":
            return (
                risk is not None
                and not risk["is_authoritative"]
                and not risk.get("has_spec_version", False)
            )

        if suggestion.action_id == "generate_spec":
            return status in ("CLAIMS_APPROVED", "RISK_REVIEWED")

        if suggestion.action_id == "commit_spec":
            return spec is not None and not spec["is_authoritative"]

        if suggestion.action_id == "re_evaluate_risk":
            return status in ("SPEC_GENERATED",)

        if suggestion.action_id == "commit_risk_reeval":
            return (
                risk is not None
                and not risk["is_authoritative"]
                and risk.get("has_spec_version", False)
            )

        if suggestion.action_id == "run_qa":
            return status in ("SPEC_GENERATED", "RISK_RE_REVIEWED")

        if suggestion.action_id == "commit_qa":
            return (
                qa is not None
                and not qa["is_authoritative"]
                and qa.get("can_export", False)
            )

        if suggestion.action_id == "lock_for_export":
            return status == "QA_COMPLETE"

        return False

    def _fallback_suggestions(self, context: Dict[str, Any]) -> List[Suggestion]:
        status = context["status"]
        brief = context.get("brief")
        claims = context.get("claims")
        risk = context.get("risk")
        spec = context.get("spec")
        qa = context.get("qa")
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
        elif status == "CLAIMS_APPROVED":
            suggestions.append(
                Suggestion(
                    label="Run risk analysis",
                    type="workflow_action",
                    action_id="run_risk",
                )
            )
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
        elif status == "RISK_REVIEWED":
            if risk and not risk["is_authoritative"]:
                suggestions.append(
                    Suggestion(
                        label="Commit risk analysis",
                        type="workflow_action",
                        action_id="commit_risk",
                    )
                )
            suggestions.append(
                Suggestion(
                    label="Generate specification",
                    type="workflow_action",
                    action_id="generate_spec",
                )
            )
            suggestions.extend([
                Suggestion(
                    label="Review risk findings",
                    type="chat_prompt",
                    prompt="Summarize the key risk findings and recommended mitigations",
                ),
                Suggestion(
                    label="Suggest claim amendments",
                    type="chat_prompt",
                    prompt="Suggest claim amendments to address the identified risks",
                ),
            ])
        elif status == "SPEC_GENERATED":
            if spec and not spec["is_authoritative"]:
                suggestions.append(
                    Suggestion(
                        label="Commit specification",
                        type="workflow_action",
                        action_id="commit_spec",
                    )
                )
            suggestions.append(
                Suggestion(
                    label="Re-evaluate risk",
                    type="workflow_action",
                    action_id="re_evaluate_risk",
                )
            )
            suggestions.extend([
                Suggestion(
                    label="Review specification coverage",
                    type="chat_prompt",
                    prompt="Check that the specification adequately supports all claim elements",
                ),
                Suggestion(
                    label="Suggest additional embodiments",
                    type="chat_prompt",
                    prompt="Suggest additional embodiments to broaden specification support",
                ),
            ])
        elif status == "RISK_RE_REVIEWED":
            if risk and not risk["is_authoritative"]:
                suggestions.append(
                    Suggestion(
                        label="Commit risk re-evaluation",
                        type="workflow_action",
                        action_id="commit_risk_reeval",
                    )
                )
            suggestions.append(
                Suggestion(
                    label="Run QA validation",
                    type="workflow_action",
                    action_id="run_qa",
                )
            )
            suggestions.extend([
                Suggestion(
                    label="Compare risk scores",
                    type="chat_prompt",
                    prompt="Compare the pre- and post-specification risk scores and highlight improvements",
                ),
                Suggestion(
                    label="Address remaining risks",
                    type="chat_prompt",
                    prompt="What remaining risks should be addressed before QA validation?",
                ),
            ])
        elif status == "QA_COMPLETE":
            if qa and not qa["is_authoritative"]:
                suggestions.append(
                    Suggestion(
                        label="Commit QA results",
                        type="workflow_action",
                        action_id="commit_qa",
                    )
                )
            suggestions.append(
                Suggestion(
                    label="Lock for export",
                    type="workflow_action",
                    action_id="lock_for_export",
                )
            )
            suggestions.extend([
                Suggestion(
                    label="Review QA findings",
                    type="chat_prompt",
                    prompt="Summarize the QA validation results and remaining issues",
                ),
                Suggestion(
                    label="Final review checklist",
                    type="chat_prompt",
                    prompt="Provide a final review checklist before locking for export",
                ),
            ])
        elif status == "LOCKED_FOR_EXPORT":
            suggestions.extend([
                Suggestion(
                    label="Review final application",
                    type="chat_prompt",
                    prompt="Provide a summary of the final patent application ready for filing",
                ),
                Suggestion(
                    label="Check filing requirements",
                    type="chat_prompt",
                    prompt="What are the filing requirements for the selected jurisdictions?",
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
