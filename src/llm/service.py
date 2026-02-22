from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm.models import TenantLLMConfig
from src.llm.schemas import LLMRoleConfig, LLMSettingsResponse, LLMSettingsUpdate
from src.llm.factory import load_config_overrides


def _effective_provider(db_value: str | None, env_fallback: str) -> str:
    return db_value or env_fallback


def _effective_model(db_model: str | None, db_provider: str | None, env_fallback_provider: str, role: str) -> str:
    """Return the effective model name for a role.

    Priority: DB model override > default model for effective provider from env.
    """
    if db_model:
        return db_model
    provider = db_provider or env_fallback_provider
    return _default_model_for_provider(provider, role)


def _default_model_for_provider(provider: str, role: str) -> str:
    """Return the env-configured default model for a given provider and role."""
    attr = f"{provider.upper()}_MODEL_{role.upper()}"
    # Anthropic and azure_foundry share the same ANTHROPIC_MODEL_* defaults
    if provider == "azure_foundry":
        attr = f"AZURE_FOUNDRY_MODEL_{role.upper()}"
    if provider == "azure_openai":
        attr = f"AZURE_OPENAI_MODEL_{role.upper()}"
    return getattr(settings, attr, "unknown")


class LLMSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_config(self, tenant_id: UUID) -> TenantLLMConfig | None:
        result = await self.db.execute(
            select(TenantLLMConfig).where(TenantLLMConfig.tenant_id == tenant_id)
        )
        return result.scalars().first()

    async def get_effective_settings(self, tenant_id: UUID) -> LLMSettingsResponse:
        cfg = await self._get_config(tenant_id)

        roles = ("primary", "secondary", "chat", "vision", "suggestions", "embedding")
        role_configs = {}
        for role in roles:
            db_provider = getattr(cfg, f"provider_{role}", None) if cfg else None
            db_model = getattr(cfg, f"model_{role}", None) if cfg else None
            env_provider = getattr(settings, f"LLM_PROVIDER_{role.upper()}")
            provider = _effective_provider(db_provider, env_provider)
            model = _effective_model(db_model, db_provider, env_provider, role)
            role_configs[role] = LLMRoleConfig(provider=provider, model=model)

        return LLMSettingsResponse(
            **role_configs,
            openai_api_key_set=bool(
                (cfg and cfg.openai_api_key) or settings.OPENAI_API_KEY
            ),
            azure_openai_api_key_set=bool(
                (cfg and cfg.azure_openai_api_key) or settings.AZURE_OPENAI_API_KEY
            ),
            azure_openai_endpoint=(
                (cfg and cfg.azure_openai_endpoint) or settings.AZURE_OPENAI_ENDPOINT
            ),
            anthropic_api_key_set=bool(
                (cfg and cfg.anthropic_api_key) or settings.ANTHROPIC_API_KEY
            ),
            azure_foundry_api_key_set=bool(
                (cfg and cfg.azure_foundry_api_key) or settings.AZURE_FOUNDRY_API_KEY
            ),
            azure_foundry_endpoint=(
                (cfg and cfg.azure_foundry_endpoint) or settings.AZURE_FOUNDRY_ENDPOINT
            ),
        )

    async def update_settings(
        self, tenant_id: UUID, update: LLMSettingsUpdate
    ) -> LLMSettingsResponse:
        cfg = await self._get_config(tenant_id)

        if cfg is None:
            cfg = TenantLLMConfig(tenant_id=tenant_id)
            self.db.add(cfg)

        update_data = update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(cfg, field, value)

        await self.db.commit()
        await self.db.refresh(cfg)

        # Rebuild in-memory overrides from the saved config
        self._apply_overrides(cfg)

        return await self.get_effective_settings(tenant_id)

    def _apply_overrides(self, cfg: TenantLLMConfig) -> None:
        """Push DB overrides into the factory's in-memory config."""
        overrides: dict[str, str] = {}
        for field in (
            "provider_primary", "provider_secondary", "provider_chat",
            "provider_vision", "provider_suggestions", "provider_embedding",
            "model_primary", "model_secondary", "model_chat",
            "model_vision", "model_suggestions", "model_embedding",
            "openai_api_key", "azure_openai_api_key", "azure_openai_endpoint",
            "anthropic_api_key", "azure_foundry_api_key", "azure_foundry_endpoint",
        ):
            val = getattr(cfg, field, None)
            if val:
                overrides[field] = val
        load_config_overrides(overrides)
