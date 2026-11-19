from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

def check_iso(value):
    if value is not None:
        try:
            if len(value) == 10: date.fromisoformat(value)
            else:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if parsed.tzinfo is None: raise ValueError('timezone required')
        except (TypeError, ValueError) as exc:
            raise ValueError('expected ISO 8601 date or timezone-aware datetime') from exc
    return value

class Provenance(Strict):
    url: HttpUrl
    source_type: Literal['official_api', 'official_docs', 'models_dev', 'litellm']
    observed_at: datetime
    published_at: str | None = None

    _published_date = field_validator('published_at')(check_iso)

class Identity(Strict):
    provider: Literal['openai', 'anthropic']
    api_id: str = Field(min_length=1)
    canonical_id: str | None = None
    aliases: list[str] | None = None
    dated_versions: list[str] | None = None
    display_name: str | None = None
    family: str | None = None
    status: Literal['active', 'deprecated', 'retired', 'unknown'] = 'unknown'
    deprecation_date: str | None = None
    retirement_date: str | None = None

    _lifecycle_dates = field_validator('deprecation_date', 'retirement_date')(check_iso)

class Limits(Strict):
    context_window_tokens: int | None = Field(default=None, ge=0)
    max_output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens_included_in_output: bool | None = None
    long_context_threshold_tokens: int | None = Field(default=None, ge=0)
    long_context_effect: str | None = None

class Reasoning(Strict):
    supported: bool | None = None
    effort_levels: list[str] | None = None
    default_effort: str | None = None
    minimum_effort: str | None = None
    can_disable: bool | None = None
    compatible_with_tools: bool | None = None
    api: str | None = None
    adaptive: bool | None = None
    fixed_budget: bool | None = None
    interleaved_tool_thinking: bool | None = None
    by_api: dict[str, dict[str, bool | str | list[str] | None]] = Field(default_factory=dict)

class Tools(Strict):
    function_calling: bool | None = None
    parallel_tool_calls: bool | None = None
    forced_tool_choice: bool | None = None
    json_schema_output: bool | None = None
    unsupported_parameters: list[str] | None = None
    streaming: bool | None = None
    by_api: dict[str, dict[str, bool | str | list[str] | None]] = Field(default_factory=dict)

class Rate(Strict):
    currency: Literal['USD'] = 'USD'
    unit: Literal['per_million_tokens'] = 'per_million_tokens'
    input: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cache_read: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cache_write: float | None = Field(default=None, ge=0, allow_inf_nan=False)

class Variant(Strict):
    name: str
    service_tier: str | None = None
    threshold_tokens: int | None = Field(default=None, ge=0)
    cache_ttl_seconds: int | None = Field(default=None, ge=0)
    rates: Rate

class Pricing(Strict):
    standard: Rate = Field(default_factory=Rate)
    variants: list[Variant] = Field(default_factory=list)

class Cache(Strict):
    supported: bool | None = None
    mode: Literal['automatic', 'explicit'] | None = None
    minimum_tokens: int | None = Field(default=None, ge=0)
    ttl_seconds: int | None = Field(default=None, ge=0)
    available_ttl_seconds: list[int] | None = None

class Modalities(Strict):
    images: bool | None = None
    pdf: bool | None = None

class Model(Strict):
    identity: Identity
    limits: Limits = Field(default_factory=Limits)
    reasoning: Reasoning = Field(default_factory=Reasoning)
    tools: Tools = Field(default_factory=Tools)
    pricing: Pricing = Field(default_factory=Pricing)
    cache: Cache = Field(default_factory=Cache)
    input_modalities: Modalities = Field(default_factory=Modalities)
    provenance: dict[str, Provenance] = Field(default_factory=dict)

    def properties_have_provenance(self):
        data = self.model_dump(mode='json')
        provenance = data['provenance']
        def check(value, path):
            if path in provenance: return
            if isinstance(value, dict):
                for key, child in value.items(): check(child, f'{path}.{key}' if path else key)
            elif isinstance(value, list):
                for index, child in enumerate(value): check(child, f'{path}.{index}')
            elif value is not None and not (path == 'identity.status' and value == 'unknown') and path not in ('pricing.standard.currency', 'pricing.standard.unit'):
                raise ValueError(f'missing provenance for {path}')
        for section in ('identity','limits','reasoning','tools','pricing','cache','input_modalities'):
            check(data[section], section)
        return self

class Catalog(Strict):
    schema_version: Literal['1.0'] = '1.0'
    generated_at: datetime
    catalog_version: str
    checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    models: dict[str, Model]
    sources: dict[str, dict]
    sync_status: dict

    @model_validator(mode='after')
    def valid_keys(self):
        for key, model in self.models.items():
            model.properties_have_provenance()
            if key != f'{model.identity.provider}:{model.identity.api_id}':
                raise ValueError('model key does not match identity')
        return self

class IdentityV2(Identity):
    provider: str = Field(min_length=1)
    # `canonical_id` in V2 is the source's complete provider/model reference.

class ModelV2(Model):
    identity: IdentityV2

class PublicCatalogV2(Strict):
    schema_version: Literal['2.0'] = '2.0'
    generated_at: datetime
    catalog_version: str
    checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    models: dict[str, ModelV2]
    sources: dict[str, dict]
    sync_status: dict

    @model_validator(mode='after')
    def valid_keys(self):
        for key, model in self.models.items():
            model.properties_have_provenance()
            if key != f'{model.identity.provider}:{model.identity.api_id}':
                raise ValueError('model key does not match identity')
        return self
