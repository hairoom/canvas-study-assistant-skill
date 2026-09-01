"""Shared indexing and search core for the Canvas study assistant."""

from .index import ResourceIndex
from .registry import REGISTRY, ResourceRegistry

__all__ = ["REGISTRY", "ResourceIndex", "ResourceRegistry"]
