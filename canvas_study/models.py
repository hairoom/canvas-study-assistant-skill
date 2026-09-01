from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EndpointSpec:
    path: str
    paginated: bool = False
    params: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ResourceSpec:
    kind: str
    aliases: tuple[str, ...]
    candidate_sources: tuple[str, ...]
    list_endpoint: EndpointSpec | None = None
    detail_endpoint: EndpointSpec | None = None
    initialize_by_default: bool = True
    detail_on_demand: bool = True
    contains_personal_data: bool = False
    cache_ttl: int = 900

    def validate(self) -> None:
        for endpoint in (self.list_endpoint, self.detail_endpoint):
            if endpoint and not endpoint.path.startswith("/api/"):
                raise ValueError(f"Unsafe endpoint for {self.kind}: {endpoint.path}")
