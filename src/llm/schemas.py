from pydantic import BaseModel


class LLMRoleConfig(BaseModel):
    provider: str
    model: str


class LLMSettingsResponse(BaseModel):
    primary: LLMRoleConfig
    secondary: LLMRoleConfig
    chat: LLMRoleConfig
    vision: LLMRoleConfig
    suggestions: LLMRoleConfig
    embedding: LLMRoleConfig
    openai_api_key_set: bool
    azure_openai_api_key_set: bool
    azure_openai_endpoint: str | None
    anthropic_api_key_set: bool
    azure_foundry_api_key_set: bool
    azure_foundry_endpoint: str | None


class LLMSettingsUpdate(BaseModel):
    provider_primary: str | None = None
    provider_secondary: str | None = None
    provider_chat: str | None = None
    provider_vision: str | None = None
    provider_suggestions: str | None = None
    provider_embedding: str | None = None

    model_primary: str | None = None
    model_secondary: str | None = None
    model_chat: str | None = None
    model_vision: str | None = None
    model_suggestions: str | None = None
    model_embedding: str | None = None

    openai_api_key: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    anthropic_api_key: str | None = None
    azure_foundry_api_key: str | None = None
    azure_foundry_endpoint: str | None = None
