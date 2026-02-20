from uuid import UUID
from typing import Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from src.ingestion.service import IngestionService
from src.briefing.agent import sbd_agent
from src.artifacts.briefs.models import BriefVersion
from src.matter.models import Matter, MatterState
from src.workstreams.models import Workstream, WorkstreamTypeEnum

class BriefingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ingestion = IngestionService()

    async def approve_brief(self, matter_id: UUID, version_id: UUID) -> BriefVersion:
        """
        Attorney approves a brief version, making it authoritative.
        This confirms the structured breakdown is correct before claims generation.
        """
        result = await self.db.execute(
            select(BriefVersion).where(
                BriefVersion.id == version_id,
                BriefVersion.matter_id == matter_id,
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            raise ValueError(f"Brief version {version_id} not found for matter {matter_id}")

        version.is_authoritative = True

        # Update workstream pointer to the approved version
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_brief_version_id = version.id

        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def get_brief_version(self, matter_id: UUID, version_id: UUID) -> Optional[BriefVersion]:
        """Get a specific brief version."""
        result = await self.db.execute(
            select(BriefVersion).where(
                BriefVersion.id == version_id,
                BriefVersion.matter_id == matter_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_brief_versions(self, matter_id: UUID):
        """List all brief versions for a matter."""
        result = await self.db.execute(
            select(BriefVersion).where(
                BriefVersion.matter_id == matter_id,
            ).order_by(desc(BriefVersion.version_number))
        )
        return list(result.scalars().all())

    async def process_brief_upload(self, matter_id: UUID, file: UploadFile, workstream_id: UUID | None = None):
        """
        1. Ingests file (PDF/Text)
        2. Runs SBD Analysis
        3. Saves BriefVersion
        4. Updates Matter/Workstream
        """
        # A. Read File
        content = await file.read()
        file_hash = self.ingestion.calculate_hash(content)
        
        # B. Check for existing processing (Optional Optimization - user didn't ask for dedupe yet)
        
        # C. Extract Text
        text = self.ingestion.extract_text(content, file.filename)
        
        # D. Run SBD Agent
        initial_state = {
            "text": text,
            "brief_data": None,
            "errors": []
        }
        final_state = await sbd_agent.ainvoke(initial_state)
        
        if final_state.get("errors"):
            raise ValueError(f"SBD Analysis Failed: {final_state['errors']}")
            
        brief_data = final_state["brief_data"]
        
        # E. Determine Version Number
        # (This logic is repeated, could be a shared mixin later)
        stmt = select(BriefVersion).where(
            BriefVersion.matter_id == matter_id
        ).order_by(desc(BriefVersion.version_number)).limit(1)
        
        result = await self.db.execute(stmt)
        latest_version = result.scalar_one_or_none()
        next_version = (latest_version.version_number + 1) if latest_version else 1
        
        # F. Save BriefVersion
        new_version = BriefVersion(
            matter_id=matter_id,
            version_number=next_version,
            source_material_hash=file_hash,
            structure_data=brief_data,
            is_authoritative=False # Needs user confirmation
        )
        self.db.add(new_version)
        await self.db.flush() # Get ID
        
        # G. Update Pointers
        
        # 1. Update Workstream (if provided, or find default Drafting workstream)
        if not workstream_id:
             # Find or create default Drafting Workstream
             stmt_ws = select(Workstream).where(
                 Workstream.matter_id == matter_id,
                 Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION
             ).limit(1)
             res_ws = await self.db.execute(stmt_ws)
             workstream = res_ws.scalar_one_or_none()
             
             if not workstream:
                 workstream = Workstream(
                     matter_id=matter_id,
                     name="Initial Draft",
                     workstream_type=WorkstreamTypeEnum.DRAFTING_APPLICATION
                 )
                 self.db.add(workstream)
        else:
             workstream = await self.db.get(Workstream, workstream_id)
             
        # Update Pointer
        workstream.active_brief_version_id = new_version.id
        
        # 2. Update Matter Status
        matter = await self.db.get(Matter, matter_id)
        if matter.status == MatterState.CREATED:
            matter.status = MatterState.BRIEF_ANALYZED
            
        await self.db.commit()
        await self.db.refresh(new_version)
        
        return new_version
