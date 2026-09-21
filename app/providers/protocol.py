"""The minimal provider protocol (contract §19). Deliberately small: no
health orchestration, no routing, no fallback, no ToolAdapter execution, no
credential retrieval, no agent delegation. Streaming is represented as
`ProviderCapability.STREAMING` metadata (contract §11), not a second
method, since nothing in v0.2.1 needs a streaming call path yet."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.providers.contracts import ProviderDefinition, ProviderRequest, ProviderResponse


@runtime_checkable
class AIProvider(Protocol):
    @property
    def definition(self) -> ProviderDefinition: ...

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...
